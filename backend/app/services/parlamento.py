import json
import re
import unicodedata
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_datetime
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import sha256_text
from app.models.api import (
    Deputy,
    OfficialSource,
    ParliamentDataset,
    SourcePublisher,
    VoteActorType,
    VoteChoice,
    VoteEvent,
    VoteRecord,
)
from app.services.http import OfficialHttpClient

MIN_DEPUTIES_PER_LEGISLATURE = 100
MAX_DEPUTIES_PER_LEGISLATURE = 500
MIN_DEPUTY_METADATA_COVERAGE = 0.70


def _normalise_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _field(record: dict[str, Any], *aliases: str) -> Any | None:
    index = {_normalise_key(str(key)): value for key, value in record.items()}
    for alias in aliases:
        candidate = index.get(_normalise_key(alias))
        if candidate not in (None, "", []):
            return candidate
    return None


def _as_text(value: Any | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = _normalise_space(str(value))
        return text or None
    return None


def _parse_date(value: Any | None) -> datetime | None:
    text = _as_text(value)
    if not text:
        return None
    try:
        parsed = cast(datetime, parse_datetime(text, dayfirst=True))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, OverflowError):
        return None


def _party_short(value: Any | None) -> str | None:
    direct = _as_text(value)
    if direct:
        return direct

    candidates: list[tuple[bool, datetime, int, str]] = []
    for position, record in enumerate(_walk(value)):
        short_name = _as_text(_field(record, "gpSigla", "partyShort"))
        if not short_name:
            continue
        started_at = _parse_date(_field(record, "gpDtInicio", "startDate"))
        ended_at = _parse_date(_field(record, "gpDtFim", "endDate"))
        candidates.append(
            (
                ended_at is None,
                started_at or datetime.min.replace(tzinfo=UTC),
                -position,
                short_name,
            )
        )

    return max(candidates)[-1] if candidates else None


class ParlamentoCollector:
    """Descobre e normaliza ficheiros publicados pela Assembleia da República.

    O portal usa páginas de catálogo e URLs opacas. O coletor segue essas páginas
    oficiais em vez de assumir que um caminho de ficheiro será estável.
    """

    def __init__(self, settings: Settings, http: OfficialHttpClient) -> None:
        self.settings = settings
        self.http = http
        parsed = urlparse(str(settings.parlamento_base_url))
        self.base_host = parsed.hostname or "www.parlamento.pt"

    async def discover_dataset_url(self, catalogue_path: str, legislature: str) -> str:
        catalogue_url = urljoin(str(self.settings.parlamento_base_url), catalogue_path)
        page = await self.http.get(catalogue_url)
        soup = BeautifulSoup(page.text, "html.parser")
        legislature_norm = _normalise_space(legislature).casefold()

        candidates = []
        for anchor in soup.find_all("a", href=True):
            label = _normalise_space(anchor.get_text(" ", strip=True)).casefold()
            href = urljoin(str(page.url), str(anchor["href"]))
            if legislature_norm in label:
                candidates.append(href)

        if not candidates:
            raise LookupError(f"Legislatura {legislature!r} não encontrada em {catalogue_url}")

        for candidate in candidates:
            if re.search(r"\.json(?:\.txt)?(?:$|\?)", candidate, re.IGNORECASE):
                return candidate
            folder = await self.http.get(candidate)
            folder_soup = BeautifulSoup(folder.text, "html.parser")
            for anchor in folder_soup.find_all("a", href=True):
                label = _normalise_space(anchor.get_text(" ", strip=True))
                href = urljoin(str(folder.url), str(anchor["href"]))
                if re.search(r"\.json(?:\.txt)?$", label, re.IGNORECASE) or re.search(
                    r"\.json(?:\.txt)?(?:$|\?)", href, re.IGNORECASE
                ):
                    return href

        raise LookupError(f"Ficheiro JSON não encontrado para {legislature!r} em {catalogue_url}")

    async def fetch_json(self, url: str) -> tuple[Any, str, str]:
        response = await self.http.get(url)
        text = response.content.decode("utf-8-sig", errors="replace")
        try:
            return json.loads(text), sha256_text(text), str(response.url)
        except json.JSONDecodeError as exc:
            raise ValueError(f"A fonte oficial não devolveu JSON válido: {response.url}") from exc

    def normalise_deputies(
        self,
        payload: Any,
        *,
        legislature: str,
        source_url: str,
        document_sha256: str,
    ) -> list[Deputy]:
        source = OfficialSource(
            publisher=SourcePublisher.PARLIAMENT,
            label="Assembleia da República — Dados Abertos",
            url=HttpUrl(source_url),
            content_sha256=document_sha256,
        )
        deputies: dict[str, Deputy] = {}

        for record in _walk(payload):
            # A fonte "Informação Base" também contém cadId e nomes de candidatos.
            # Só um par explícito DepId/DepNomeParlamentar identifica um deputado.
            source_id = _as_text(_field(record, "DepId"))
            name = _as_text(_field(record, "DepNomeParlamentar"))
            if not source_id or not name:
                continue

            full_name = _as_text(_field(record, "DepNomeCompleto", "NomeCompleto", "fullName"))
            party = _party_short(_field(record, "DepGP", "GrupoParlamentar", "party"))
            constituency = _as_text(
                _field(
                    record,
                    "DepCPDes",
                    "DepCirculo",
                    "CirculoEleitoral",
                    "Circulo",
                    "constituency",
                )
            )
            email = _as_text(_field(record, "DepEmail", "Email", "email"))

            deputies[source_id] = Deputy(
                source_id=source_id,
                parliamentary_name=name,
                full_name=full_name,
                party_short=party,
                constituency=constituency,
                legislature=legislature,
                email=email,
                source=source,
            )

        return sorted(deputies.values(), key=lambda item: item.parliamentary_name.casefold())

    @staticmethod
    def _validate_deputy_snapshot(deputies: list[Deputy]) -> list[str]:
        count = len(deputies)
        if not MIN_DEPUTIES_PER_LEGISLATURE <= count <= MAX_DEPUTIES_PER_LEGISLATURE:
            raise ValueError(
                "Snapshot parlamentar rejeitado: "
                f"{count} deputados, fora do intervalo de segurança "
                f"{MIN_DEPUTIES_PER_LEGISLATURE}-{MAX_DEPUTIES_PER_LEGISLATURE}."
            )

        party_count = sum(item.party_short is not None for item in deputies)
        constituency_count = sum(item.constituency is not None for item in deputies)
        party_coverage = party_count / count
        constituency_coverage = constituency_count / count
        if (
            party_coverage < MIN_DEPUTY_METADATA_COVERAGE
            or constituency_coverage < MIN_DEPUTY_METADATA_COVERAGE
        ):
            raise ValueError(
                "Snapshot parlamentar rejeitado: cobertura insuficiente de partido/círculo "
                f"({party_count}/{count} e {constituency_count}/{count})."
            )

        warnings = []
        if party_count < count or constituency_count < count:
            warnings.append(
                "Existem deputados sem partido ou círculo na fonte; os campos foram "
                "mantidos vazios e exigem revisão antes da publicação."
            )
        return warnings

    def normalise_votes(
        self,
        payload: Any,
        *,
        source_url: str,
        document_sha256: str,
    ) -> list[VoteEvent]:
        source = OfficialSource(
            publisher=SourcePublisher.PARLIAMENT,
            label="Assembleia da República — votação oficial",
            url=HttpUrl(source_url),
            content_sha256=document_sha256,
        )
        events: dict[str, VoteEvent] = {}

        for record in _walk(payload):
            vote_id = _as_text(_field(record, "VotacaoId", "idVotacao", "voteId", "VotId", "evtId"))
            result = _as_text(_field(record, "VotacaoResultado", "Resultado", "result"))
            details = _field(record, "VotacaoDetalhe", "Detalhe", "details", "Votacoes")
            date_value = _field(record, "VotacaoData", "Data", "date", "evtData")
            title = _as_text(
                _field(record, "VotacaoDescricao", "Descricao", "Objeto", "title", "IniTitulo")
            )

            if not vote_id or not (result or details or date_value):
                continue

            records = self._normalise_vote_records(details)
            is_nominal = bool(records) and all(
                item.actor_type is VoteActorType.PERSON for item in records
            )
            initiative = _as_text(
                _field(record, "IniNr", "IniciativaNumero", "initiativeNumber", "IniDescTipo")
            )
            events[vote_id] = VoteEvent(
                source_id=vote_id,
                title=title or initiative or f"Votação {vote_id}",
                voted_at=_parse_date(date_value),
                result=result,
                initiative_number=initiative,
                is_nominal=is_nominal,
                records=records,
                source=source,
            )

        return sorted(
            events.values(),
            key=lambda item: item.voted_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

    def _normalise_vote_records(self, details: Any) -> list[VoteRecord]:
        if isinstance(details, list):
            records: list[VoteRecord] = []
            for item in details:
                if not isinstance(item, dict):
                    continue
                actor = _as_text(_field(item, "DeputadoNome", "Nome", "GP", "actor"))
                choice = _as_text(_field(item, "Voto", "vote", "Sentido"))
                actor_id = _as_text(_field(item, "DeputadoId", "DepId", "actorId"))
                if not actor or not choice:
                    continue
                records.append(
                    VoteRecord(
                        actor_label=actor,
                        actor_source_id=actor_id,
                        actor_type=VoteActorType.PERSON if actor_id else VoteActorType.UNKNOWN,
                        choice=self._choice(choice),
                    )
                )
            return records

        if not isinstance(details, str):
            return []

        text = BeautifulSoup(details.replace("<BR>", "<br>"), "html.parser").get_text("\n")
        records = []
        for line in filter(None, (_normalise_space(part) for part in text.splitlines())):
            match = re.match(r"(A Favor|Contra|Absten(?:ção|cao)|Ausente)s?\s*:\s*(.+)", line, re.I)
            if not match:
                continue
            choice = self._choice(match.group(1))
            for actor in re.split(r"\s*[,;]\s*", match.group(2)):
                actor = _normalise_space(actor)
                if actor:
                    # Texto livre não permite afirmar se é pessoa ou grupo parlamentar.
                    records.append(
                        VoteRecord(
                            actor_label=actor,
                            actor_type=VoteActorType.UNKNOWN,
                            choice=choice,
                        )
                    )
        return records

    @staticmethod
    def _choice(value: str) -> VoteChoice:
        normalised = _normalise_key(value)
        if normalised in {"afavor", "favor", "sim"}:
            return VoteChoice.FAVOR
        if normalised in {"contra", "nao"}:
            return VoteChoice.AGAINST
        if normalised in {"abstencao", "abstem", "abstencoes"}:
            return VoteChoice.ABSTENTION
        if normalised in {"ausente", "faltou", "naopresente"}:
            return VoteChoice.ABSENT
        return VoteChoice.UNKNOWN

    async def collect_deputies(self, legislature: str) -> ParliamentDataset:
        url = str(self.settings.parlamento_deputies_url or "")
        if not url:
            url = await self.discover_dataset_url(
                self.settings.parlamento_deputies_catalogue_path,
                legislature,
            )
        payload, digest, final_url = await self.fetch_json(url)
        deputies = self.normalise_deputies(
            payload,
            legislature=legislature,
            source_url=final_url,
            document_sha256=digest,
        )
        warnings = self._validate_deputy_snapshot(deputies)
        return ParliamentDataset(
            legislature=legislature,
            dataset_url=HttpUrl(final_url),
            document_sha256=digest,
            deputies=deputies,
            warnings=warnings,
        )

    async def collect_votes(self, legislature: str) -> ParliamentDataset:
        url = str(self.settings.parlamento_votes_url or "")
        if not url:
            url = await self.discover_dataset_url(
                self.settings.parlamento_initiatives_catalogue_path,
                legislature,
            )
        payload, digest, final_url = await self.fetch_json(url)
        votes = self.normalise_votes(payload, source_url=final_url, document_sha256=digest)
        warnings = []
        if not votes:
            warnings.append(
                "Nenhuma votação normalizada; conservar o documento para revisão do mapeamento."
            )
        if any(event.records and not event.is_nominal for event in votes):
            warnings.append(
                "Existem posições cujo ator não é inequivocamente individual; "
                "não foram atribuídas a deputados."
            )
        return ParliamentDataset(
            legislature=legislature,
            dataset_url=HttpUrl(final_url),
            document_sha256=digest,
            votes=votes,
            warnings=warnings,
        )
