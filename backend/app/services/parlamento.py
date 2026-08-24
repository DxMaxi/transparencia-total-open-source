import hashlib
import json
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from dateutil.parser import isoparse
from dateutil.parser import parse as parse_datetime
from pydantic import HttpUrl

from app.core.config import Settings
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
from app.models.archive import PrivateRawDocument
from app.services.http import OfficialHttpClient

MIN_DEPUTIES_PER_LEGISLATURE = 100
MAX_DEPUTIES_PER_LEGISLATURE = 500
MIN_DEPUTY_METADATA_COVERAGE = 0.70
JSON_RESOURCE_NAME = re.compile(r"(?:\.json(?:\.txt)?|_json\.txt)$", re.IGNORECASE)
VOTE_DETAIL_SECTION = re.compile(
    r"(?P<choice>A\s+Favor|Contra|Absten(?:ção|cao)|Aus(?:ência|encia)(?:s)?|Ausentes?)"
    r"\s*:\s*",
    re.IGNORECASE,
)
MANDATE_HOLDER_SITUATIONS = frozenset(
    {
        "efetivo",
        "efetivodefinitivo",
        "efetivotemporario",
        "impedido",
        "renunciou",
        "suspensoeleito",
    }
)


@dataclass(frozen=True)
class _InitiativeContext:
    """Identidade e designação oficiais da iniciativa ascendente."""

    source_id: str | None = None
    number: str | None = None
    initiative_type: str | None = None
    title: str | None = None


def _normalise_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _vote_candidates_conflict(previous: VoteEvent, candidate: VoteEvent) -> bool:
    """Deteta apenas contradições factuais, sem confundir detalhe adicional com conflito."""

    if (
        previous.voted_at is not None
        and candidate.voted_at is not None
        and previous.voted_at != candidate.voted_at
    ):
        return True
    if (
        previous.result is not None
        and candidate.result is not None
        and _normalise_space(previous.result).casefold()
        != _normalise_space(candidate.result).casefold()
    ):
        return True

    previous_positions = {
        _normalise_space(record.actor_label).casefold(): record.choice
        for record in previous.records
    }
    candidate_positions = {
        _normalise_space(record.actor_label).casefold(): record.choice
        for record in candidate.records
    }
    return any(
        previous_positions[label] is not candidate_positions[label]
        for label in previous_positions.keys() & candidate_positions.keys()
    )


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _walk_with_initiative(
    value: Any,
    initiative: _InitiativeContext | None = None,
) -> Iterator[tuple[dict[str, Any], _InitiativeContext | None]]:
    """Percorre o JSON mantendo a iniciativa oficial ascendente exata."""

    if isinstance(value, dict):
        source_id = _as_text(_field(value, "IniId", "IniciativaId", "initiativeId"))
        number = _as_text(_field(value, "IniNr", "IniciativaNumero", "initiativeNumber"))
        initiative_type = _as_text(_field(value, "IniDescTipo", "IniciativaTipo", "initiativeType"))
        title = _as_text(_field(value, "IniTitulo", "IniciativaTitulo", "initiativeTitle"))

        has_context_fields = any((source_id, number, initiative_type, title))
        same_initiative = initiative is not None and (
            (source_id is None or source_id == initiative.source_id)
            and (number is None or number == initiative.number)
        )
        inherited = initiative if same_initiative else None
        current: _InitiativeContext | None
        if has_context_fields:
            current = _InitiativeContext(
                source_id=source_id or (inherited.source_id if inherited else None),
                number=number or (inherited.number if inherited else None),
                initiative_type=initiative_type
                or (inherited.initiative_type if inherited else None),
                title=title or (inherited.title if inherited else None),
            )
        else:
            current = initiative

        yield value, current
        for child in value.values():
            yield from _walk_with_initiative(child, current)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_with_initiative(child, initiative)


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


def _is_bare_vote_identifier(value: str | None) -> bool:
    """Deteta descrições que a fonte publicou apenas como um número interno."""

    return value is None or re.fullmatch(r"\d+", value) is not None


def _initiative_display_title(initiative: _InitiativeContext | None) -> str | None:
    if initiative is None or not initiative.title:
        return None
    if initiative.number:
        prefix = (
            f"{initiative.initiative_type} n.º {initiative.number}"
            if initiative.initiative_type
            else f"Iniciativa n.º {initiative.number}"
        )
        return f"{prefix} — {initiative.title}"
    return initiative.title


def _parse_date(value: Any | None) -> datetime | None:
    text = _as_text(value)
    if not text:
        return None
    try:
        parsed = cast(
            datetime,
            isoparse(text)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", text)
            else parse_datetime(text, dayfirst=True),
        )
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, OverflowError):
        return None


def _is_json_resource(label: str, href: str) -> bool:
    """Reconhece os nomes JSON usados nos catálogos oficiais do Parlamento."""

    parsed = urlparse(href)
    names = [_normalise_space(label), unquote(parsed.path.rsplit("/", 1)[-1])]
    for key, values in parse_qs(parsed.query).items():
        if key.casefold() in {"fich", "file", "filename"}:
            names.extend(unquote(value) for value in values)
    return any(JSON_RESOURCE_NAME.search(name) for name in names)


def _primary_deputy_records(payload: Any) -> Iterator[dict[str, Any]]:
    """Extrai apenas o bloco biográfico principal do ficheiro de atividade."""

    if not isinstance(payload, list):
        return
    for item in payload:
        if not isinstance(item, dict):
            continue
        deputy = _field(item, "Deputado")
        if isinstance(deputy, dict):
            yield deputy


def _held_parliamentary_mandate(record: dict[str, Any]) -> bool:
    """Confirma pela situação oficial que a pessoa exerceu ou recebeu mandato."""

    situation = _field(record, "DepSituacao", "Situacao")
    for item in _walk(situation):
        description = _as_text(_field(item, "sioDes", "description"))
        if description and _normalise_key(description) in MANDATE_HOLDER_SITUATIONS:
            return True
    return False


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
        exact_labels = {legislature_norm, f"{legislature_norm} legislatura"}

        exact_candidates: list[str] = []
        fallback_candidates: list[str] = []
        for anchor in soup.find_all("a", href=True):
            label = _normalise_space(anchor.get_text(" ", strip=True)).casefold()
            href = urljoin(str(page.url), str(anchor["href"]))
            if re.search(
                rf"(?<![a-z0-9]){re.escape(legislature_norm)}(?![a-z0-9])",
                label,
            ):
                target = exact_candidates if label in exact_labels else fallback_candidates
                target.append(href)

        # O cabeçalho global também pode conter ligações como "Acolhimento aos
        # Deputados - XVII Legislatura". Se existir a pasta com o nome exato da
        # legislatura, nunca devemos seguir essas ligações de navegação primeiro.
        candidates = exact_candidates or fallback_candidates

        if not candidates:
            raise LookupError(f"Legislatura {legislature!r} não encontrada em {catalogue_url}")

        for candidate in candidates:
            if _is_json_resource("", candidate):
                return candidate
            folder = await self.http.get(candidate)
            folder_soup = BeautifulSoup(folder.text, "html.parser")
            for anchor in folder_soup.find_all("a", href=True):
                label = _normalise_space(anchor.get_text(" ", strip=True))
                href = urljoin(str(folder.url), str(anchor["href"]))
                if _is_json_resource(label, href):
                    return href

        raise LookupError(f"Ficheiro JSON não encontrado para {legislature!r} em {catalogue_url}")

    async def fetch_json(
        self,
        url: str,
        *,
        max_bytes: int | None = None,
    ) -> tuple[Any, PrivateRawDocument]:
        response = (
            await self.http.get(url, max_bytes=max_bytes)
            if max_bytes is not None
            else await self.http.get(url)
        )
        retrieved_at = datetime.now(UTC)
        digest = hashlib.sha256(response.content).hexdigest()
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(str(response.url)),
            retrieved_at=retrieved_at,
            content_sha256=digest,
            mime_type=response.headers.get("content-type"),
            content=response.content,
        )
        text = response.content.decode("utf-8-sig", errors="replace")
        try:
            return json.loads(text), raw_document
        except json.JSONDecodeError as exc:
            raise ValueError(f"A fonte oficial não devolveu JSON válido: {response.url}") from exc

    def normalise_deputies(
        self,
        payload: Any,
        *,
        legislature: str,
        source_url: str,
        document_sha256: str,
        retrieved_at: datetime | None = None,
    ) -> list[Deputy]:
        source = OfficialSource(
            publisher=SourcePublisher.PARLIAMENT,
            label="Assembleia da República — Dados Abertos",
            url=HttpUrl(source_url),
            retrieved_at=retrieved_at or datetime.now(UTC),
            content_sha256=document_sha256,
        )
        deputies: dict[str, Deputy] = {}

        for record in _primary_deputy_records(payload):
            # As referências dentro de AtividadeDeputadoList podem repetir nomes e
            # identificadores. Só o bloco principal "Deputado" constitui uma ficha.
            # A fonte também inclui suplentes e candidatos que nunca exerceram mandato.
            if not _held_parliamentary_mandate(record):
                continue

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

    @staticmethod
    def normalise_votes(
        payload: Any,
        *,
        source_url: str,
        document_sha256: str,
        retrieved_at: datetime | None = None,
        reject_conflicting_duplicates: bool = False,
    ) -> list[VoteEvent]:
        source = OfficialSource(
            publisher=SourcePublisher.PARLIAMENT,
            label="Assembleia da República — votação oficial",
            url=HttpUrl(source_url),
            retrieved_at=retrieved_at or datetime.now(UTC),
            content_sha256=document_sha256,
        )
        events: dict[str, VoteEvent] = {}
        initiative_contexts: dict[str, set[_InitiativeContext]] = {}
        descriptive_titles: dict[str, set[str]] = {}

        for record, initiative_context in _walk_with_initiative(payload):
            result = _as_text(_field(record, "VotacaoResultado", "Resultado", "result"))
            vote_id = _as_text(_field(record, "VotacaoId", "idVotacao", "voteId", "VotId", "evtId"))
            if not vote_id and result and _field(record, "reuniao") is not None:
                # No JSON oficial de iniciativas, a votação usa uma chave genérica
                # ``id``. Exigimos também resultado e reunião para não confundir os
                # muitos outros objetos aninhados que contêm ``id`` e ``data``.
                vote_id = _as_text(_field(record, "id"))
            details = _field(record, "VotacaoDetalhe", "Detalhe", "details", "Votacoes")
            date_value = _field(record, "VotacaoData", "Data", "date", "evtData")
            source_title = _as_text(
                _field(record, "VotacaoDescricao", "Descricao", "Objeto", "title", "IniTitulo")
            )

            if not vote_id or not (result or details or date_value):
                continue

            records = ParlamentoCollector._normalise_vote_records(details)
            is_nominal = bool(records) and all(
                item.actor_type is VoteActorType.PERSON for item in records
            )
            if initiative_context:
                initiative_contexts.setdefault(vote_id, set()).add(initiative_context)
            descriptive_title = source_title if not _is_bare_vote_identifier(source_title) else None
            if descriptive_title:
                descriptive_titles.setdefault(vote_id, set()).add(descriptive_title)
            initiative_title = _initiative_display_title(initiative_context)
            initiative_number = initiative_context.number if initiative_context else None
            candidate = VoteEvent(
                source_id=vote_id,
                title=(
                    descriptive_title
                    or initiative_title
                    or (
                        f"Votação da iniciativa n.º {initiative_number}"
                        if initiative_number
                        else None
                    )
                    or f"Votação {vote_id}"
                ),
                voted_at=_parse_date(date_value),
                result=result,
                initiative_number=initiative_number,
                is_nominal=is_nominal,
                records=records,
                source=source,
            )

            previous = events.get(vote_id)
            if (
                previous is not None
                and reject_conflicting_duplicates
                and _vote_candidates_conflict(previous, candidate)
            ):
                raise ValueError(
                    "O mesmo identificador oficial de votação contém factos divergentes"
                )
            if previous is None or (
                len(candidate.records),
                candidate.voted_at is not None,
                candidate.result is not None,
                candidate.title != f"Votação {vote_id}",
            ) > (
                len(previous.records),
                previous.voted_at is not None,
                previous.result is not None,
                previous.title != f"Votação {vote_id}",
            ):
                events[vote_id] = candidate

        if reject_conflicting_duplicates:
            for titles in descriptive_titles.values():
                if len({title.casefold() for title in titles}) > 1:
                    raise ValueError(
                        "O mesmo identificador oficial de votação contém descrições divergentes"
                    )

        for vote_id, event in list(events.items()):
            observed_contexts = initiative_contexts.get(vote_id, set())
            unique_context = next(iter(observed_contexts)) if len(observed_contexts) == 1 else None
            if descriptive_titles.get(vote_id):
                final_title = event.title
            elif unique_context is not None:
                final_title = (
                    _initiative_display_title(unique_context)
                    or (
                        f"Votação da iniciativa n.º {unique_context.number}"
                        if unique_context.number
                        else None
                    )
                    or f"Votação {vote_id}"
                )
            elif observed_contexts:
                final_title = f"Votação conjunta de {len(observed_contexts)} iniciativas"
            else:
                final_title = f"Votação {vote_id}"

            events[vote_id] = event.model_copy(
                update={
                    "title": final_title,
                    "initiative_number": unique_context.number if unique_context else None,
                }
            )

        return sorted(
            events.values(),
            key=lambda item: item.voted_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

    @staticmethod
    def _normalise_vote_records(details: Any) -> list[VoteRecord]:
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
                        choice=ParlamentoCollector._choice(choice),
                    )
                )
            return records

        if not isinstance(details, str):
            return []

        text = BeautifulSoup(details, "html.parser").get_text(" ")
        sections = list(VOTE_DETAIL_SECTION.finditer(text))
        records_by_actor: dict[str, VoteRecord] = {}
        for position, section in enumerate(sections):
            end = sections[position + 1].start() if position + 1 < len(sections) else len(text)
            choice = ParlamentoCollector._choice(section.group("choice"))
            for actor_value in re.split(r"\s*[,;]\s*", text[section.end() : end]):
                actor = _normalise_space(actor_value)
                if not actor:
                    continue

                # Esta chave só elimina repetições textuais exatas após normalizar
                # espaços e caixa. Não associa nomes a pessoas nem faz fuzzy matching.
                actor_key = actor.casefold()
                previous = records_by_actor.get(actor_key)
                if previous is None:
                    records_by_actor[actor_key] = VoteRecord(
                        actor_label=actor,
                        actor_type=VoteActorType.UNKNOWN,
                        choice=choice,
                    )
                elif previous.choice is not choice:
                    # A fonte atribui por vezes sentidos incompatíveis ao mesmo ator.
                    # Preservamos a incerteza em vez de escolher silenciosamente um deles.
                    records_by_actor[actor_key] = previous.model_copy(
                        update={"choice": VoteChoice.UNKNOWN}
                    )
        return list(records_by_actor.values())

    @staticmethod
    def _choice(value: str) -> VoteChoice:
        normalised = _normalise_key(value)
        if normalised in {"afavor", "favor", "sim"}:
            return VoteChoice.FAVOR
        if normalised in {"contra", "nao"}:
            return VoteChoice.AGAINST
        if normalised in {"abstencao", "abstem", "abstencoes"}:
            return VoteChoice.ABSTENTION
        if normalised in {
            "ausencia",
            "ausencias",
            "ausente",
            "ausentes",
            "faltou",
            "naopresente",
        }:
            return VoteChoice.ABSENT
        return VoteChoice.UNKNOWN

    async def collect_deputies(self, legislature: str) -> ParliamentDataset:
        url = str(self.settings.parlamento_deputies_url or "")
        if not url:
            url = await self.discover_dataset_url(
                self.settings.parlamento_deputies_catalogue_path,
                legislature,
            )
        payload, raw_document = await self.fetch_json(url)
        deputies = self.normalise_deputies(
            payload,
            legislature=legislature,
            source_url=str(raw_document.source_url),
            document_sha256=raw_document.content_sha256,
            retrieved_at=raw_document.retrieved_at,
        )
        warnings = self._validate_deputy_snapshot(deputies)
        return ParliamentDataset(
            legislature=legislature,
            dataset_url=raw_document.source_url,
            document_sha256=raw_document.content_sha256,
            deputies=deputies,
            warnings=warnings,
            collected_at=raw_document.retrieved_at,
            raw_document=raw_document,
        )

    async def collect_votes(self, legislature: str) -> ParliamentDataset:
        url = str(self.settings.parlamento_votes_url or "")
        if not url:
            url = await self.discover_dataset_url(
                self.settings.parlamento_initiatives_catalogue_path,
                legislature,
            )
        payload, raw_document = await self.fetch_json(
            url,
            max_bytes=self.settings.parlamento_votes_max_bytes,
        )
        votes = self.normalise_votes(
            payload,
            source_url=str(raw_document.source_url),
            document_sha256=raw_document.content_sha256,
            retrieved_at=raw_document.retrieved_at,
        )
        warnings = []
        if not votes:
            warnings.append(
                "Nenhuma votação normalizada; conservar o documento para revisão do mapeamento."
            )
        votes_without_positions = sum(not event.records for event in votes)
        if votes_without_positions:
            warnings.append(
                f"{votes_without_positions} votações sem posições normalizadas; "
                "o detalhe deve ser tratado como dados indisponíveis até confirmação na fonte."
            )
        if any(event.records and not event.is_nominal for event in votes):
            warnings.append(
                "Existem posições cujo ator não é inequivocamente individual; "
                "não foram atribuídas a deputados."
            )
        return ParliamentDataset(
            legislature=legislature,
            dataset_url=raw_document.source_url,
            document_sha256=raw_document.content_sha256,
            votes=votes,
            warnings=warnings,
            collected_at=raw_document.retrieved_at,
            raw_document=raw_document,
        )
