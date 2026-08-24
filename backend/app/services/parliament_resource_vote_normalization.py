"""Normalização privada de votações a partir de iniciativas parlamentares arquivadas."""

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.models.api import VoteActorType
from app.models.parliamentary import ParliamentActivityDataset
from app.repositories.parliament_resource_normalization import (
    PARLIAMENT_HISTORICAL_VOTES_PARSER_VERSION,
    ParliamentResourceNormalizationRepository,
    PrivateParliamentArchivedResourceProof,
)
from app.services.parlamento import ParlamentoCollector
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_resource_normalization import strict_parliament_json
from app.services.parliament_source_catalogue import ParliamentCatalogueKind

PARLIAMENT_HISTORICAL_COMPLETENESS: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"
MAX_HISTORICAL_VOTES_PER_RESOURCE = 50_000
MAX_HISTORICAL_VOTE_RECORDS_PER_RESOURCE = 250_000


@dataclass(frozen=True, slots=True)
class CollectedParliamentResourceVoteNormalization:
    parent_catalogue_snapshot_id: str
    parent_manifest_snapshot_id: str
    parent_archive_snapshot_id: str
    archive_source_document_id: str
    proof_content_sha256: str
    dataset: ParliamentActivityDataset
    historical_completeness: Literal["NOT_ASSERTED"] = PARLIAMENT_HISTORICAL_COMPLETENESS
    publishable: bool = False
    editorial_cases_created: int = 0


class ParliamentResourceVoteNormalizer:
    """Extrai apenas votações com identificador oficial, sem inferir atores."""

    def normalise(
        self,
        proof: PrivateParliamentArchivedResourceProof,
    ) -> CollectedParliamentResourceVoteNormalization:
        if (
            proof.catalogue_kind is not ParliamentCatalogueKind.INITIATIVES
            or proof.resource_format is not ParliamentResourceFormat.JSON
        ):
            raise ValueError("A V5.26 aceita apenas o recurso JSON de iniciativas com votações")
        if proof.publishable or not proof.archive_attested:
            raise ValueError("O recurso parlamentar não possui prova privada válida")
        if (
            proof.content_sha256 != proof.raw_document.content_sha256
            or proof.byte_size != len(proof.raw_document.content)
            or proof.resource_url != str(proof.raw_document.source_url)
        ):
            raise ValueError("Os bytes privados divergem da prova do recurso arquivado")

        payload = strict_parliament_json(proof.raw_document.content)
        votes = ParlamentoCollector.normalise_votes(
            payload,
            source_url=proof.resource_url,
            document_sha256=proof.content_sha256,
            retrieved_at=proof.raw_document.retrieved_at,
            reject_conflicting_duplicates=True,
        )
        if not votes:
            raise ValueError("O recurso arquivado não contém votações normalizáveis")
        if len(votes) > MAX_HISTORICAL_VOTES_PER_RESOURCE:
            raise ValueError("O recurso excede o limite de votações por fotografia privada")

        vote_record_count = sum(len(event.records) for event in votes)
        if vote_record_count > MAX_HISTORICAL_VOTE_RECORDS_PER_RESOURCE:
            raise ValueError("O recurso excede o limite de posições por fotografia privada")
        if any(
            record.actor_type is VoteActorType.PERSON and not record.actor_source_id
            for event in votes
            for record in event.records
        ):
            raise ValueError("Uma posição individual não contém identificador oficial inequívoco")

        warnings = [
            "Cobertura histórica não afirmada: esta fotografia contém apenas votações "
            "observadas num único recurso oficial arquivado."
        ]
        votes_without_positions = sum(not event.records for event in votes)
        if votes_without_positions:
            warnings.append(
                f"{votes_without_positions} votações não incluem posições normalizáveis; "
                "o resultado oficial é preservado sem inventar atores."
            )
        unknown_positions = sum(
            record.actor_type is VoteActorType.UNKNOWN
            for event in votes
            for record in event.records
        )
        if unknown_positions:
            warnings.append(
                f"{unknown_positions} posições conservam ator UNKNOWN e não foram "
                "atribuídas a pessoas ou partidos."
            )

        dataset = ParliamentActivityDataset(
            legislature=proof.legislature,
            dataset_url=proof.resource_url,
            document_sha256=proof.content_sha256,
            parser_version=PARLIAMENT_HISTORICAL_VOTES_PARSER_VERSION,
            votes=votes,
            warnings=warnings,
            collected_at=proof.raw_document.retrieved_at,
            raw_document=proof.raw_document,
        )
        return CollectedParliamentResourceVoteNormalization(
            parent_catalogue_snapshot_id=proof.parent_catalogue_snapshot_id,
            parent_manifest_snapshot_id=proof.parent_manifest_snapshot_id,
            parent_archive_snapshot_id=proof.archive_snapshot_id,
            archive_source_document_id=proof.archive_source_document_id,
            proof_content_sha256=proof.content_sha256,
            dataset=dataset,
        )


class ParliamentResourceVoteNormalizationStager:
    """Persiste votações só depois de repetir a prova e a normalização integral."""

    def __init__(
        self,
        settings: Settings,
        repository: ParliamentResourceNormalizationRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def store(
        self,
        collection: CollectedParliamentResourceVoteNormalization,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(
                "A normalização de votações privada só pode persistir em test ou staging"
            )
        dataset = collection.dataset
        if (
            dataset.parser_version != PARLIAMENT_HISTORICAL_VOTES_PARSER_VERSION
            or dataset.sessions
            or dataset.initiatives
            or not dataset.votes
            or collection.historical_completeness != PARLIAMENT_HISTORICAL_COMPLETENESS
            or collection.publishable
            or collection.editorial_cases_created
        ):
            raise ValueError("A fotografia histórica diverge do contrato privado de votações")

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
            raise ValueError("A prova repetida diverge da fotografia histórica de votações")
        recomputed = ParliamentResourceVoteNormalizer().normalise(proof)
        if recomputed != collection:
            raise ValueError(
                "A fotografia histórica de votações não coincide com os bytes revalidados"
            )

        result = await self.repository.persist_private_votes(dataset)
        vote_record_count = sum(len(event.records) for event in dataset.votes)
        return {
            **result,
            "parent_catalogue_snapshot_id": proof.parent_catalogue_snapshot_id,
            "parent_manifest_snapshot_id": proof.parent_manifest_snapshot_id,
            "parent_archive_snapshot_id": proof.archive_snapshot_id,
            "historical_completeness": PARLIAMENT_HISTORICAL_COMPLETENESS,
            "records_normalised": len(dataset.votes) + vote_record_count,
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
