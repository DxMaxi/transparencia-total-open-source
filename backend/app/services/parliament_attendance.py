"""Recolha e normalização privada de presenças oficiais em plenário."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, parse_qsl, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.parliamentary_attendance import (
    ParliamentAttendanceDataset,
    ParliamentAttendanceObservation,
    ParliamentAttendanceStatus,
)
from app.repositories.parliament_attendance import ParliamentAttendanceRepository
from app.services.http import OfficialHttpClient
from app.services.parliament_source_catalogue import (
    require_parliament_url,
    require_supported_parliament_legislature,
)

PARLIAMENT_ATTENDANCE_PARSER_VERSION = "parliament-attendance-html-v1"
PARLIAMENT_ATTENDANCE_SOURCE_NAME = "PARLIAMENT_PLENARY_ATTENDANCE"
MIN_ATTENDANCE_RECORDS = 100
MAX_ATTENDANCE_RECORDS = 500
MIN_KNOWN_STATUS_COVERAGE = 0.70

_MEETING_PATH = "/deputadogp/paginas/detalhereuniaoplenaria.aspx"
_BIOGRAPHY_PATH = "/deputadogp/paginas/biografia.aspx"
_MEETING_HEADING = re.compile(
    r"^Reuni[aã]o\s+Plen[aá]ria\s+(?P<meeting_type>.+?)\s+de\s+"
    r"(?P<meeting_date>\d{4}-\d{2}-\d{2})\.?$",
    re.IGNORECASE,
)
_STATUS_PATTERNS: tuple[tuple[re.Pattern[str], ParliamentAttendanceStatus], ...] = (
    (
        re.compile(r"Falta\s+Injustificada\s*\(\s*FI\s*\)", re.IGNORECASE),
        ParliamentAttendanceStatus.UNJUSTIFIED_ABSENCE,
    ),
    (
        re.compile(r"Falta\s+Justificada\s*\(\s*FJ\s*\)", re.IGNORECASE),
        ParliamentAttendanceStatus.JUSTIFIED_ABSENCE,
    ),
    (
        re.compile(r"Presen[cç]a\s*\(\s*P\s*\)", re.IGNORECASE),
        ParliamentAttendanceStatus.PRESENT,
    ),
)
_STATUS_AFTER_LABEL = re.compile(
    r"Presen[cç]a/Falta\s+(?P<label>.+?)"
    r"(?=(?:Motivo|Deputado|Grupo\s+Parlamentar/Partido)\b|$)",
    re.IGNORECASE,
)
_GROUP_LABEL = re.compile(
    r"Grupo\s+Parlamentar/Partido\s+(?P<label>.+?)"
    r"(?=Presen[cç]a/Falta\b|$)",
    re.IGNORECASE,
)
_ABSENCE_REASON = re.compile(
    r"Motivo\s+(?P<label>.+?)"
    r"(?=(?:Deputado|Grupo\s+Parlamentar/Partido|Presen[cç]a/Falta)\b|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AttendanceUrlProof:
    url: str
    official_meeting_id: str


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def require_attendance_url(value: str) -> AttendanceUrlProof:
    """Aceita apenas uma página de detalhe com um único BID numérico."""

    exact_url = require_parliament_url(value)
    parsed = urlparse(exact_url)
    if parsed.path.casefold() != _MEETING_PATH:
        raise ValueError("O URL não identifica o detalhe oficial de uma reunião plenária")
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if len(query_items) != 1 or query_items[0][0].casefold() != "bid":
        raise ValueError("O URL da reunião tem parâmetros inesperados")
    bid_value = query_items[0][1]
    if not re.fullmatch(r"[1-9]\d{0,19}", bid_value):
        raise ValueError("O URL da reunião não contém um BID oficial inequívoco")
    return AttendanceUrlProof(url=exact_url, official_meeting_id=bid_value)


def _biography_id(base_url: str, href: str) -> str | None:
    candidate = urljoin(base_url, href)
    try:
        exact = require_parliament_url(candidate)
    except ValueError:
        return None
    parsed = urlparse(exact)
    if parsed.path.casefold() != _BIOGRAPHY_PATH:
        return None
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if len(query_items) != 1 or query_items[0][0].casefold() != "bid":
        return None
    value = query_items[0][1]
    if not re.fullmatch(r"[1-9]\d{0,19}", value):
        return None
    return value


def _segment_text(anchor: Tag, next_anchor: Tag | None) -> str:
    parts: list[str] = []
    for element in anchor.next_elements:
        if next_anchor is not None and element is next_anchor:
            break
        if isinstance(element, NavigableString):
            text = _normalise_space(str(element))
            if text:
                parts.append(text)
        if len(parts) >= 80:
            break
    return _normalise_space(" ".join(parts))


def _status(segment: str) -> tuple[ParliamentAttendanceStatus, str, str | None]:
    for pattern, status in _STATUS_PATTERNS:
        match = pattern.search(segment)
        if match is not None:
            label = _normalise_space(match.group(0))
            code_match = re.search(r"\(([^)]+)\)", label)
            return status, label, code_match.group(1).strip().upper() if code_match else None
    raw = _STATUS_AFTER_LABEL.search(segment)
    label = _normalise_space(raw.group("label")) if raw is not None else "Dados indisponíveis"
    code_match = re.search(r"\(([^)]+)\)", label)
    return (
        ParliamentAttendanceStatus.UNKNOWN,
        label[:300],
        code_match.group(1).strip().upper()[:30] if code_match else None,
    )


def _optional_match(pattern: re.Pattern[str], segment: str, *, limit: int) -> str | None:
    match = pattern.search(segment)
    if match is None:
        return None
    value = _normalise_space(match.group("label"))
    return value[:limit] if value else None


def _meeting_details(soup: BeautifulSoup) -> tuple[date, str]:
    candidates: set[tuple[date, str]] = set()
    for raw_text in soup.stripped_strings:
        text = _normalise_space(str(raw_text))
        match = _MEETING_HEADING.fullmatch(text)
        if match is None:
            continue
        meeting_type = _normalise_space(match.group("meeting_type"))
        if not meeting_type or len(meeting_type) > 200:
            raise ValueError("O tipo oficial da reunião é inválido")
        candidates.add((date.fromisoformat(match.group("meeting_date")), meeting_type))
    if len(candidates) != 1:
        raise ValueError("A página não identifica inequivocamente a data e o tipo da reunião")
    return next(iter(candidates))


def _session_number(
    soup: BeautifulSoup,
    *,
    legislature: str,
    meeting_date: date,
) -> str | None:
    candidates: set[str] = set()
    expected_date = meeting_date.isoformat()
    pattern = re.compile(
        rf"^{re.escape(legislature)}_(?P<session>\d+)_(?P<number>\d+)_"
        rf"{re.escape(expected_date)}\.pdf$",
        re.IGNORECASE,
    )
    for anchor in soup.find_all("a", href=True):
        href = unquote(str(anchor["href"]))
        parsed = urlparse(urljoin("https://www.parlamento.pt/", href))
        for key, values in parse_qs(parsed.query).items():
            if key.casefold() not in {"fich", "file", "filename"}:
                continue
            for value in values:
                match = pattern.fullmatch(value.rsplit("/", 1)[-1])
                if match is not None:
                    candidates.add(match.group("number"))
    if len(candidates) > 1:
        raise ValueError("A página oficial contém números de reunião contraditórios")
    return next(iter(candidates), None)


class ParliamentAttendanceNormalizer:
    """Converte um HTML arquivado numa fotografia integral e conservadora."""

    def normalise(
        self,
        raw_document: PrivateRawDocument,
        *,
        legislature: str,
    ) -> ParliamentAttendanceDataset:
        exact_legislature = require_supported_parliament_legislature(legislature)
        url_proof = require_attendance_url(str(raw_document.source_url))
        if raw_document.mime_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("A fonte oficial de presenças não devolveu HTML")

        soup = BeautifulSoup(raw_document.content, "html.parser")
        meeting_date, meeting_type = _meeting_details(soup)

        entry_anchors: list[tuple[Tag, str]] = []
        for anchor in soup.find_all("a", href=True):
            official_deputy_id = _biography_id(url_proof.url, str(anchor["href"]))
            if official_deputy_id is not None:
                entry_anchors.append((anchor, official_deputy_id))

        observations: dict[str, ParliamentAttendanceObservation] = {}
        for index, (anchor, official_deputy_id) in enumerate(entry_anchors):
            next_anchor = entry_anchors[index + 1][0] if index + 1 < len(entry_anchors) else None
            parliamentary_name = _normalise_space(anchor.get_text(" ", strip=True))
            if not parliamentary_name:
                continue
            segment = _segment_text(anchor, next_anchor)
            status, source_status_label, source_status_code = _status(segment)
            observation = ParliamentAttendanceObservation(
                official_deputy_id=official_deputy_id,
                parliamentary_name=parliamentary_name,
                parliamentary_group_label=_optional_match(_GROUP_LABEL, segment, limit=200),
                status=status,
                source_status_label=source_status_label,
                source_status_code=source_status_code,
                absence_reason=_optional_match(_ABSENCE_REASON, segment, limit=1000),
            )
            previous = observations.get(official_deputy_id)
            if previous is not None and previous != observation:
                raise ValueError("O mesmo BID oficial contém presenças divergentes na reunião")
            observations[official_deputy_id] = observation

        ordered = tuple(
            sorted(
                observations.values(),
                key=lambda item: (item.parliamentary_name.casefold(), item.official_deputy_id),
            )
        )
        if not MIN_ATTENDANCE_RECORDS <= len(ordered) <= MAX_ATTENDANCE_RECORDS:
            raise ValueError(
                "Fotografia privada rejeitada: "
                f"{len(ordered)} presenças, fora do intervalo de segurança "
                f"{MIN_ATTENDANCE_RECORDS}-{MAX_ATTENDANCE_RECORDS}"
            )
        known_count = sum(item.status is not ParliamentAttendanceStatus.UNKNOWN for item in ordered)
        if known_count / len(ordered) < MIN_KNOWN_STATUS_COVERAGE:
            raise ValueError("Cobertura insuficiente de estados oficiais de presença/falta")

        session_number = _session_number(
            soup,
            legislature=exact_legislature,
            meeting_date=meeting_date,
        )
        warnings = [
            "A fotografia representa uma única reunião oficial; não prova assiduidade fora "
            "deste intervalo nem transforma falta em incumprimento.",
            "Os BID são usados literalmente; nomes e siglas servem apenas para leitura e "
            "nunca criam uma associação de identidade.",
        ]
        unknown_count = len(ordered) - known_count
        if unknown_count:
            warnings.append(
                f"{unknown_count} estados não pertencem ao vocabulário conhecido e permanecem "
                "UNKNOWN, bloqueando a respetiva publicação até revisão da fonte."
            )
        if session_number is None:
            warnings.append(
                "O número da reunião não foi derivável do documento e fica indisponível."
            )

        return ParliamentAttendanceDataset(
            legislature=exact_legislature,
            official_meeting_id=url_proof.official_meeting_id,
            meeting_date=meeting_date,
            meeting_type=meeting_type,
            session_number=session_number,
            source_url=raw_document.source_url,
            document_sha256=raw_document.content_sha256,
            parser_version=PARLIAMENT_ATTENDANCE_PARSER_VERSION,
            observations=ordered,
            warnings=tuple(warnings),
            collected_at=raw_document.retrieved_at,
            raw_document=raw_document,
        )


class ParliamentAttendanceCollector:
    """Recolhe exatamente uma reunião oficial e mantém os bytes privados."""

    def __init__(self, http: OfficialHttpClient) -> None:
        self.http = http

    async def collect(self, *, legislature: str, meeting_url: str) -> ParliamentAttendanceDataset:
        require_supported_parliament_legislature(legislature)
        requested = require_attendance_url(meeting_url)
        response = await self.http.get(requested.url)
        effective = require_attendance_url(str(response.url))
        if effective != requested:
            raise ValueError("O URL efetivo da reunião diverge do URL oficial pedido")
        mime_type = response.headers.get("content-type")
        normalised_mime = mime_type.split(";", 1)[0].strip().casefold() if mime_type else None
        if normalised_mime not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("A fonte oficial de presenças não devolveu HTML")
        content = response.content
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(effective.url),
            retrieved_at=datetime.now(UTC),
            content_sha256=hashlib.sha256(content).hexdigest(),
            mime_type=mime_type,
            content=content,
        )
        return ParliamentAttendanceNormalizer().normalise(
            raw_document,
            legislature=legislature,
        )


class ParliamentAttendanceStager:
    """Repete o parser e persiste apenas em test ou staging, sem revisão."""

    def __init__(self, settings: Settings, repository: ParliamentAttendanceRepository) -> None:
        self.settings = settings
        self.repository = repository

    async def store(self, dataset: ParliamentAttendanceDataset) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError("Presenças privadas só podem ser persistidas em test ou staging")
        if dataset.raw_document is None:
            raise ValueError("A fotografia de presenças não conserva os bytes oficiais")
        recomputed = ParliamentAttendanceNormalizer().normalise(
            dataset.raw_document,
            legislature=dataset.legislature,
        )
        if recomputed != dataset:
            raise ValueError("A fotografia de presenças não coincide com os bytes revalidados")
        result = await self.repository.persist_private_attendance(dataset)
        return {
            **result,
            "records_normalised": len(dataset.observations),
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
