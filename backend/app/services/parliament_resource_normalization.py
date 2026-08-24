"""Normalização privada de iniciativas a partir de bytes parlamentares arquivados."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.config import Settings
from app.models.parliamentary import ParliamentActivityDataset, ParliamentaryInitiativeRecord
from app.repositories.parliament_resource_normalization import (
    PARLIAMENT_HISTORICAL_INITIATIVES_PARSER_VERSION,
    ParliamentResourceNormalizationRepository,
    PrivateParliamentArchivedResourceProof,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_source_catalogue import ParliamentCatalogueKind
from app.services.parliamentary_activity import normalise_initiatives

PARLIAMENT_HISTORICAL_COMPLETENESS: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
MAX_HISTORICAL_INITIATIVES_PER_RESOURCE = 50_000


@dataclass(frozen=True, slots=True)
class CollectedParliamentResourceNormalization:
    parent_catalogue_snapshot_id: str
    parent_manifest_snapshot_id: str
    parent_archive_snapshot_id: str
    archive_source_document_id: str
    proof_content_sha256: str
    dataset: ParliamentActivityDataset
    historical_completeness: Literal["NOT_ASSERTED"] = PARLIAMENT_HISTORICAL_COMPLETENESS
    publishable: bool = False
    editorial_cases_created: int = 0


def _strict_json(content: bytes) -> Any:
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("O recurso parlamentar arquivado não usa UTF-8 válido") from exc
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("O recurso parlamentar arquivado não contém JSON válido") from exc
    if not isinstance(payload, (dict, list)):
        raise ValueError("O JSON parlamentar tem de conter um objeto ou uma lista")
    return payload


def _normalise_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _walk_json(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _has_initiative_identity(record: dict[str, Any]) -> bool:
    keys = {_normalise_key(str(key)) for key in record}
    required_aliases = (
        ("IniId", "initiativeId", "idIniciativa"),
        ("IniNr", "initiativeNumber", "numeroIniciativa"),
        ("IniDescTipo", "initiativeType", "tipoIniciativa"),
        ("IniTitulo", "initiativeTitle", "tituloIniciativa"),
    )
    return all(
        any(_normalise_key(alias) in keys for alias in aliases) for aliases in required_aliases
    )


def _normalise_initiatives_strict(
    payload: Any,
    *,
    legislature: str,
    source_url: str,
    document_sha256: str,
    retrieved_at: datetime,
) -> list[ParliamentaryInitiativeRecord]:
    by_source_id: dict[str, ParliamentaryInitiativeRecord] = {}
    for record in _walk_json(payload):
        if not _has_initiative_identity(record):
            continue
        candidates = normalise_initiatives(
            record,
            legislature=legislature,
            source_url=source_url,
            document_sha256=document_sha256,
            retrieved_at=retrieved_at,
            parliament_base_url="https://www.parlamento.pt",
        )
        if len(candidates) != 1:
            raise ValueError("Uma observação de iniciativa não produziu um registo inequívoco")
        candidate = candidates[0]
        existing = by_source_id.get(candidate.source_id)
        if existing is not None and existing != candidate:
            raise ValueError(
                "O mesmo identificador oficial de iniciativa contém registos divergentes"
            )
        by_source_id[candidate.source_id] = candidate
    return sorted(
        by_source_id.values(),
        key=lambda item: (
            item.introduced_at or datetime.min.replace(tzinfo=UTC),
            item.number,
        ),
    )


class ParliamentResourceNormalizer:
    """Produz apenas uma fotografia privada de iniciativas com IDs oficiais."""

    def normalise(
        self,
        proof: PrivateParliamentArchivedResourceProof,
    ) -> CollectedParliamentResourceNormalization:
        if (
            proof.catalogue_kind is not ParliamentCatalogueKind.INITIATIVES
            or proof.resource_format is not ParliamentResourceFormat.JSON
        ):
            raise ValueError("A V5.25 aceita apenas o recurso JSON de iniciativas")
        if proof.publishable or not proof.archive_attested:
            raise ValueError("O recurso parlamentar não possui prova privada válida")
        if (
            proof.content_sha256 != proof.raw_document.content_sha256
            or proof.byte_size != len(proof.raw_document.content)
            or proof.resource_url != str(proof.raw_document.source_url)
        ):
            raise ValueError("Os bytes privados divergem da prova do recurso arquivado")

        payload = _strict_json(proof.raw_document.content)
        initiatives = _normalise_initiatives_strict(
            payload,
            legislature=proof.legislature,
            source_url=proof.resource_url,
            document_sha256=proof.content_sha256,
            retrieved_at=proof.raw_document.retrieved_at,
        )
        if not initiatives:
            raise ValueError("O recurso arquivado não contém iniciativas normalizáveis")
        if len(initiatives) > MAX_HISTORICAL_INITIATIVES_PER_RESOURCE:
            raise ValueError("O recurso excede o limite de iniciativas por fotografia privada")

        warning = (
            "Cobertura histórica não afirmada: esta fotografia contém apenas iniciativas "
            "observadas num único recurso oficial arquivado."
        )
        dataset = ParliamentActivityDataset(
            legislature=proof.legislature,
            dataset_url=proof.resource_url,
            document_sha256=proof.content_sha256,
            parser_version=PARLIAMENT_HISTORICAL_INITIATIVES_PARSER_VERSION,
            initiatives=initiatives,
            warnings=[warning],
            collected_at=proof.raw_document.retrieved_at,
            raw_document=proof.raw_document,
        )
        return CollectedParliamentResourceNormalization(
            parent_catalogue_snapshot_id=proof.parent_catalogue_snapshot_id,
            parent_manifest_snapshot_id=proof.parent_manifest_snapshot_id,
            parent_archive_snapshot_id=proof.archive_snapshot_id,
            archive_source_document_id=proof.archive_source_document_id,
            proof_content_sha256=proof.content_sha256,
            dataset=dataset,
        )


class ParliamentResourceNormalizationStager:
    """Persiste a normalização só depois de repetir a cadeia dos bytes arquivados."""

    def __init__(
        self,
        settings: Settings,
        repository: ParliamentResourceNormalizationRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def store(
        self,
        collection: CollectedParliamentResourceNormalization,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(
                "A normalização parlamentar privada só pode persistir em test ou staging"
            )
        dataset = collection.dataset
        if (
            dataset.parser_version != PARLIAMENT_HISTORICAL_INITIATIVES_PARSER_VERSION
            or dataset.sessions
            or dataset.votes
            or not dataset.initiatives
            or collection.historical_completeness != PARLIAMENT_HISTORICAL_COMPLETENESS
            or collection.publishable
            or collection.editorial_cases_created
        ):
            raise ValueError("A fotografia histórica diverge do contrato privado de iniciativas")

        proof = await self.repository.require_archived_resource(
            catalogue_snapshot_id=collection.parent_catalogue_snapshot_id,
            manifest_snapshot_id=collection.parent_manifest_snapshot_id,
            archive_snapshot_id=collection.parent_archive_snapshot_id,
            catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
            legislature=dataset.legislature,
            resource_format=ParliamentResourceFormat.JSON,
            resource_url=str(dataset.dataset_url),
        )
        if (
            proof.archive_source_document_id != collection.archive_source_document_id
            or proof.content_sha256 != collection.proof_content_sha256
            or proof.raw_document.content_sha256 != dataset.document_sha256
        ):
            raise ValueError("A prova repetida diverge da fotografia histórica normalizada")
        recomputed = ParliamentResourceNormalizer().normalise(proof)
        if recomputed != collection:
            raise ValueError(
                "A fotografia histórica não coincide com os bytes oficiais revalidados"
            )

        result = await self.repository.persist_private_initiatives(dataset)
        return {
            **result,
            "parent_catalogue_snapshot_id": proof.parent_catalogue_snapshot_id,
            "parent_manifest_snapshot_id": proof.parent_manifest_snapshot_id,
            "parent_archive_snapshot_id": proof.archive_snapshot_id,
            "historical_completeness": PARLIAMENT_HISTORICAL_COMPLETENESS,
            "records_normalised": len(dataset.initiatives),
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
