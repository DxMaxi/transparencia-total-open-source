"""Normalização privada da atividade biográfica oficial dos deputados."""

import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar, cast

from dateutil.parser import isoparse
from dateutil.parser import parse as parse_datetime
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.api import OfficialSource, SourcePublisher
from app.models.parliamentary_people import (
    ParliamentaryDeputyObservation,
    ParliamentaryGroupObservation,
    ParliamentaryOfficeObservation,
    ParliamentarySituationObservation,
    ParliamentDeputyObservationDataset,
)
from app.repositories.parliament_resource_deputy_normalization import (
    PARLIAMENT_HISTORICAL_DEPUTIES_PARSER_VERSION,
    ParliamentResourceDeputyNormalizationRepository,
)
from app.repositories.parliament_resource_normalization import (
    PrivateParliamentArchivedResourceProof,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_resource_normalization import strict_parliament_json
from app.services.parliament_source_catalogue import ParliamentCatalogueKind

PARLIAMENT_HISTORICAL_COMPLETENESS: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
MIN_DEPUTIES_PER_LEGISLATURE = 100
MAX_DEPUTIES_PER_LEGISLATURE = 500
MIN_EXACT_METADATA_COVERAGE = 0.70

_MANDATE_HOLDER_SITUATIONS = frozenset(
    {
        "efetivo",
        "efetivodefinitivo",
        "efetivotemporario",
        "impedido",
        "renunciou",
        "suspensoeleito",
    }
)
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class CollectedParliamentResourceDeputyNormalization:
    parent_catalogue_snapshot_id: str
    parent_manifest_snapshot_id: str
    parent_archive_snapshot_id: str
    archive_source_document_id: str
    proof_content_sha256: str
    dataset: ParliamentDeputyObservationDataset
    historical_completeness: Literal["NOT_ASSERTED"] = PARLIAMENT_HISTORICAL_COMPLETENESS
    publishable: bool = False
    editorial_cases_created: int = 0


def _normalise_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]", "", ascii_value.casefold())


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _field(record: dict[str, Any], *aliases: str) -> Any | None:
    index = {_normalise_key(str(key)): value for key, value in record.items()}
    for alias in aliases:
        candidate = index.get(_normalise_key(alias))
        if candidate not in (None, "", []):
            return candidate
    return None


def _as_text(value: Any | None) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = _normalise_space(str(value))
        return text or None
    return None


def _walk_records(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_records(child)


def _strict_date(value: Any | None, *, context: str) -> datetime | None:
    text = _as_text(value)
    if text is None:
        return None
    try:
        parsed = cast(
            datetime,
            isoparse(text)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", text)
            else parse_datetime(text, dayfirst=True),
        )
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"Data oficial inválida em {context}") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _sorted_unique(
    items: list[_T],
    *,
    key: Callable[[_T], tuple[Any, ...]],
) -> tuple[_T, ...]:
    unique: dict[str, _T] = {}
    for item in items:
        unique.setdefault(repr(item), item)
    return tuple(sorted(unique.values(), key=key))


def _groups(value: Any, *, deputy_id: str) -> tuple[ParliamentaryGroupObservation, ...]:
    direct = _as_text(value)
    if direct is not None:
        return (ParliamentaryGroupObservation(short_name=direct),)

    groups: list[ParliamentaryGroupObservation] = []
    labels_by_exact_period: dict[tuple[str, datetime | None, datetime | None], str] = {}
    for record in _walk_records(value):
        short_name = _as_text(_field(record, "GpSigla", "gpSigla", "partyShort"))
        if short_name is None:
            continue
        source_id = _as_text(_field(record, "GpId", "gpId", "partyId"))
        starts_at = _strict_date(
            _field(record, "GpDtInicio", "gpDtInicio", "startDate"),
            context=f"grupo parlamentar do deputado {deputy_id}",
        )
        ends_at = _strict_date(
            _field(record, "GpDtFim", "gpDtFim", "endDate"),
            context=f"grupo parlamentar do deputado {deputy_id}",
        )
        if source_id is not None:
            period_key = (source_id, starts_at, ends_at)
            previous_label = labels_by_exact_period.setdefault(period_key, short_name)
            if previous_label.casefold() != short_name.casefold():
                raise ValueError(
                    "O mesmo identificador oficial de grupo parlamentar tem siglas divergentes"
                )
        groups.append(
            ParliamentaryGroupObservation(
                source_id=source_id,
                short_name=short_name,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )

    return _sorted_unique(
        groups,
        key=lambda item: (
            item.starts_at or datetime.min.replace(tzinfo=UTC),
            item.ends_at or datetime.max.replace(tzinfo=UTC),
            item.source_id or "",
            item.short_name.casefold(),
        ),
    )


def _situations(value: Any, *, deputy_id: str) -> tuple[ParliamentarySituationObservation, ...]:
    situations: list[ParliamentarySituationObservation] = []
    for record in _walk_records(value):
        description = _as_text(_field(record, "SioDes", "sioDes", "description"))
        if description is None:
            continue
        situations.append(
            ParliamentarySituationObservation(
                description=description,
                starts_at=_strict_date(
                    _field(record, "SioDtInicio", "sioDtInicio", "startDate"),
                    context=f"situação parlamentar do deputado {deputy_id}",
                ),
                ends_at=_strict_date(
                    _field(record, "SioDtFim", "sioDtFim", "endDate"),
                    context=f"situação parlamentar do deputado {deputy_id}",
                ),
            )
        )
    return _sorted_unique(
        situations,
        key=lambda item: (
            item.starts_at or datetime.min.replace(tzinfo=UTC),
            item.ends_at or datetime.max.replace(tzinfo=UTC),
            item.description.casefold(),
        ),
    )


def _offices(value: Any, *, deputy_id: str) -> tuple[ParliamentaryOfficeObservation, ...]:
    offices: list[ParliamentaryOfficeObservation] = []
    titles_by_exact_period: dict[tuple[str, datetime | None, datetime | None], str] = {}
    for record in _walk_records(value):
        title = _as_text(_field(record, "CarDes", "carDes", "title"))
        if title is None:
            continue
        source_id = _as_text(_field(record, "CarId", "carId", "officeId"))
        starts_at = _strict_date(
            _field(record, "CarDtInicio", "carDtInicio", "startDate"),
            context=f"cargo parlamentar do deputado {deputy_id}",
        )
        ends_at = _strict_date(
            _field(record, "CarDtFim", "carDtFim", "endDate"),
            context=f"cargo parlamentar do deputado {deputy_id}",
        )
        if source_id is not None:
            period_key = (source_id, starts_at, ends_at)
            previous_title = titles_by_exact_period.setdefault(period_key, title)
            if previous_title.casefold() != title.casefold():
                raise ValueError("O mesmo identificador oficial de cargo tem títulos divergentes")
        offices.append(
            ParliamentaryOfficeObservation(
                source_id=source_id,
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )
    return _sorted_unique(
        offices,
        key=lambda item: (
            item.starts_at or datetime.min.replace(tzinfo=UTC),
            item.ends_at or datetime.max.replace(tzinfo=UTC),
            item.source_id or "",
            item.title.casefold(),
        ),
    )


def _has_mandate_evidence(
    situations: tuple[ParliamentarySituationObservation, ...],
) -> bool:
    return any(
        _normalise_key(item.description) in _MANDATE_HOLDER_SITUATIONS for item in situations
    )


def _has_inverted_interval(item: Any) -> bool:
    return item.starts_at is not None and item.ends_at is not None and item.ends_at < item.starts_at


class ParliamentResourceDeputyNormalizer:
    """Extrai deputados apenas do bloco principal e preserva intervalos oficiais."""

    def normalise(
        self,
        proof: PrivateParliamentArchivedResourceProof,
    ) -> CollectedParliamentResourceDeputyNormalization:
        if (
            proof.catalogue_kind is not ParliamentCatalogueKind.DEPUTY_ACTIVITY
            or proof.resource_format is not ParliamentResourceFormat.JSON
        ):
            raise ValueError("A V5.27 aceita apenas o recurso JSON de atividade dos deputados")
        if proof.publishable or not proof.archive_attested:
            raise ValueError("O recurso parlamentar não possui prova privada válida")
        if (
            proof.content_sha256 != proof.raw_document.content_sha256
            or proof.byte_size != len(proof.raw_document.content)
            or proof.resource_url != str(proof.raw_document.source_url)
        ):
            raise ValueError("Os bytes privados divergem da prova do recurso arquivado")

        payload = strict_parliament_json(proof.raw_document.content)
        if not isinstance(payload, list):
            raise ValueError("O recurso de atividade dos deputados não contém uma lista oficial")

        source = OfficialSource(
            publisher=SourcePublisher.PARLIAMENT,
            label="Assembleia da República — atividade dos deputados",
            url=HttpUrl(proof.resource_url),
            retrieved_at=proof.raw_document.retrieved_at,
            content_sha256=proof.content_sha256,
        )
        observations: dict[str, ParliamentaryDeputyObservation] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            deputy = _field(item, "Deputado")
            if not isinstance(deputy, dict):
                continue

            source_id = _as_text(_field(deputy, "DepId"))
            parliamentary_name = _as_text(_field(deputy, "DepNomeParlamentar"))
            if source_id is None or parliamentary_name is None:
                continue
            situations = _situations(_field(deputy, "DepSituacao"), deputy_id=source_id)
            if not _has_mandate_evidence(situations):
                continue

            observation = ParliamentaryDeputyObservation(
                source_id=source_id,
                candidate_source_id=_as_text(_field(deputy, "DepCadId")),
                legislature=proof.legislature,
                parliamentary_name=parliamentary_name,
                full_name=_as_text(_field(deputy, "DepNomeCompleto")),
                constituency_source_id=_as_text(_field(deputy, "DepCPId")),
                constituency_label=_as_text(_field(deputy, "DepCPDes")),
                parliamentary_groups=_groups(_field(deputy, "DepGP"), deputy_id=source_id),
                mandate_situations=situations,
                offices=_offices(_field(deputy, "DepCargo"), deputy_id=source_id),
                source=source,
            )
            previous = observations.get(source_id)
            if previous is not None and previous != observation:
                raise ValueError(
                    "O mesmo identificador oficial de deputado contém observações divergentes"
                )
            observations[source_id] = observation

        ordered = tuple(
            sorted(
                observations.values(),
                key=lambda item: (item.parliamentary_name.casefold(), item.source_id),
            )
        )
        count = len(ordered)
        if not MIN_DEPUTIES_PER_LEGISLATURE <= count <= MAX_DEPUTIES_PER_LEGISLATURE:
            raise ValueError(
                "Fotografia privada rejeitada: "
                f"{count} deputados, fora do intervalo de segurança "
                f"{MIN_DEPUTIES_PER_LEGISLATURE}-{MAX_DEPUTIES_PER_LEGISLATURE}"
            )

        exact_group_count = sum(
            any(group.source_id is not None for group in item.parliamentary_groups)
            for item in ordered
        )
        exact_constituency_count = sum(
            item.constituency_source_id is not None and item.constituency_label is not None
            for item in ordered
        )
        if (
            exact_group_count / count < MIN_EXACT_METADATA_COVERAGE
            or exact_constituency_count / count < MIN_EXACT_METADATA_COVERAGE
        ):
            raise ValueError(
                "Fotografia privada rejeitada: cobertura insuficiente de IDs oficiais de "
                "grupo parlamentar ou círculo eleitoral"
            )

        warnings = [
            "Cobertura histórica não afirmada: esta fotografia contém apenas deputados "
            "observados num único recurso oficial arquivado.",
            "As datas de situação, grupo e cargo conservam o significado da fonte; não são "
            "convertidas automaticamente em início ou fim de mandato.",
        ]
        missing_group_ids = count - exact_group_count
        if missing_group_ids:
            warnings.append(
                f"{missing_group_ids} deputados não têm grupo parlamentar com ID oficial; "
                "nenhuma relação partidária será inferida pela sigla."
            )
        missing_constituency_ids = count - exact_constituency_count
        if missing_constituency_ids:
            warnings.append(
                f"{missing_constituency_ids} deputados não têm círculo com ID e designação; "
                "o campo permanece indisponível para associação."
            )
        inverted_intervals = sum(
            _has_inverted_interval(period)
            for item in ordered
            for period in (
                *item.parliamentary_groups,
                *item.mandate_situations,
                *item.offices,
            )
        )
        if inverted_intervals:
            warnings.append(
                f"{inverted_intervals} intervalos oficiais têm data final anterior à inicial; "
                "foram preservados como anomalia da fonte e não podem originar mandatos."
            )

        dataset = ParliamentDeputyObservationDataset(
            legislature=proof.legislature,
            dataset_url=proof.resource_url,
            document_sha256=proof.content_sha256,
            parser_version=PARLIAMENT_HISTORICAL_DEPUTIES_PARSER_VERSION,
            observations=ordered,
            warnings=tuple(warnings),
            collected_at=proof.raw_document.retrieved_at,
            raw_document=proof.raw_document,
        )
        return CollectedParliamentResourceDeputyNormalization(
            parent_catalogue_snapshot_id=proof.parent_catalogue_snapshot_id,
            parent_manifest_snapshot_id=proof.parent_manifest_snapshot_id,
            parent_archive_snapshot_id=proof.archive_snapshot_id,
            archive_source_document_id=proof.archive_source_document_id,
            proof_content_sha256=proof.content_sha256,
            dataset=dataset,
        )


class ParliamentResourceDeputyNormalizationStager:
    """Persiste a fotografia só depois de repetir prova e normalização integral."""

    def __init__(
        self,
        settings: Settings,
        repository: ParliamentResourceDeputyNormalizationRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def store(
        self,
        collection: CollectedParliamentResourceDeputyNormalization,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(
                "A normalização privada de deputados só pode persistir em test ou staging"
            )
        dataset = collection.dataset
        if (
            dataset.parser_version != PARLIAMENT_HISTORICAL_DEPUTIES_PARSER_VERSION
            or not dataset.observations
            or collection.historical_completeness != PARLIAMENT_HISTORICAL_COMPLETENESS
            or collection.publishable
            or collection.editorial_cases_created
        ):
            raise ValueError("A fotografia histórica diverge do contrato privado de deputados")

        proof = await self.repository.require_archived_resource(
            catalogue_snapshot_id=collection.parent_catalogue_snapshot_id,
            manifest_snapshot_id=collection.parent_manifest_snapshot_id,
            archive_snapshot_id=collection.parent_archive_snapshot_id,
            catalogue_kind=ParliamentCatalogueKind.DEPUTY_ACTIVITY,
            legislature=dataset.legislature,
            resource_format=ParliamentResourceFormat.JSON,
            resource_url=str(dataset.dataset_url),
        )
        if (
            proof.archive_source_document_id != collection.archive_source_document_id
            or proof.content_sha256 != collection.proof_content_sha256
            or proof.raw_document.content_sha256 != dataset.document_sha256
        ):
            raise ValueError("A prova repetida diverge da fotografia histórica de deputados")
        recomputed = ParliamentResourceDeputyNormalizer().normalise(proof)
        if recomputed != collection:
            raise ValueError(
                "A fotografia histórica de deputados não coincide com os bytes revalidados"
            )

        result = await self.repository.persist_private_deputy_observations(
            dataset,
            expected_source_document_id=proof.archive_source_document_id,
        )
        nested_count = sum(
            len(item.parliamentary_groups) + len(item.mandate_situations) + len(item.offices)
            for item in dataset.observations
        )
        return {
            **result,
            "parent_catalogue_snapshot_id": proof.parent_catalogue_snapshot_id,
            "parent_manifest_snapshot_id": proof.parent_manifest_snapshot_id,
            "parent_archive_snapshot_id": proof.archive_snapshot_id,
            "historical_completeness": PARLIAMENT_HISTORICAL_COMPLETENESS,
            "records_normalised": len(dataset.observations) + nested_count,
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
