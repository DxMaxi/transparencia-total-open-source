"""Derivação privada de autorias individuais do JSON oficial de iniciativas."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings
from app.models.parliamentary_initiative_authorship import (
    PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION,
    ParliamentInitiativeAuthorObservation,
    ParliamentInitiativeAuthorRelation,
    ParliamentInitiativeAuthorshipDataset,
)
from app.repositories.parliament_initiative_authorship import (
    ParliamentInitiativeAuthorshipRepository,
)
from app.repositories.parliament_resource_normalization import (
    PrivateParliamentArchivedResourceProof,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_resource_normalization import (
    _has_initiative_identity,
    _walk_json,
    strict_parliament_json,
)
from app.services.parliament_source_catalogue import ParliamentCatalogueKind

PARLIAMENT_AUTHORSHIP_COMPLETENESS: Literal["NOT_ASSERTED"] = "NOT_ASSERTED"


@dataclass(frozen=True, slots=True)
class CollectedParliamentInitiativeAuthorship:
    parent_catalogue_snapshot_id: str
    parent_manifest_snapshot_id: str
    parent_archive_snapshot_id: str
    archive_source_document_id: str
    proof_content_sha256: str
    dataset: ParliamentInitiativeAuthorshipDataset
    historical_completeness: Literal["NOT_ASSERTED"] = PARLIAMENT_AUTHORSHIP_COMPLETENESS
    publishable: bool = False
    editorial_cases_created: int = 0


def _normalise_key(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _field(record: dict[str, Any], *names: str) -> Any:
    by_key = {_normalise_key(key): value for key, value in record.items()}
    for name in names:
        if _normalise_key(name) in by_key:
            return by_key[_normalise_key(name)]
    return None


def _text(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int)):
        stripped = str(value).strip()
        return stripped or None
    return None


def _author_entries(value: Any) -> Iterator[ParliamentInitiativeAuthorObservation]:
    """Lê apenas a subestrutura oficial iniAutorDeputados/idCadastro."""

    if isinstance(value, list):
        for child in value:
            yield from _author_entries(child)
        return
    if not isinstance(value, dict):
        return

    keys = {_normalise_key(key) for key in value}
    author_keys = {"idcadastro", "nome", "gp"}
    if keys & author_keys:
        official_deputy_id = _text(_field(value, "idCadastro"))
        parliamentary_name = _text(_field(value, "nome"))
        if official_deputy_id is None or parliamentary_name is None:
            raise ValueError(
                "Um autor deputado não contém simultaneamente idCadastro e nome oficiais"
            )
        yield ParliamentInitiativeAuthorObservation(
            initiative_source_id="pending",
            official_deputy_id=official_deputy_id,
            parliamentary_name=parliamentary_name,
            parliamentary_group_label=_text(_field(value, "GP")),
            relation=ParliamentInitiativeAuthorRelation.AUTHOR,
        )
        return
    for child in value.values():
        yield from _author_entries(child)


def normalise_initiative_authorships(
    payload: Any,
) -> tuple[ParliamentInitiativeAuthorObservation, ...]:
    by_key: dict[tuple[str, str], ParliamentInitiativeAuthorObservation] = {}
    for initiative in _walk_json(payload):
        if not _has_initiative_identity(initiative):
            continue
        initiative_source_id = _text(_field(initiative, "IniId"))
        if initiative_source_id is None:
            continue
        authors = _field(initiative, "iniAutorDeputados")
        if authors is None:
            continue
        for raw_author in _author_entries(authors):
            author = raw_author.model_copy(update={"initiative_source_id": initiative_source_id})
            key = (author.initiative_source_id, author.official_deputy_id)
            existing = by_key.get(key)
            if existing is not None and existing != author:
                raise ValueError("A mesma iniciativa e idCadastro contêm autorias divergentes")
            by_key[key] = author
    return tuple(
        sorted(
            by_key.values(),
            key=lambda item: (item.initiative_source_id, item.official_deputy_id),
        )
    )


class ParliamentInitiativeAuthorshipNormalizer:
    """Produz uma fotografia privada; não liga pessoas nem publica iniciativas."""

    def normalise(
        self,
        proof: PrivateParliamentArchivedResourceProof,
    ) -> CollectedParliamentInitiativeAuthorship:
        if (
            proof.catalogue_kind is not ParliamentCatalogueKind.INITIATIVES
            or proof.resource_format is not ParliamentResourceFormat.JSON
        ):
            raise ValueError("A V5.42 aceita apenas o JSON oficial de iniciativas")
        if proof.publishable or not proof.archive_attested:
            raise ValueError("O recurso parlamentar não possui prova privada válida")
        if (
            proof.content_sha256 != proof.raw_document.content_sha256
            or proof.byte_size != len(proof.raw_document.content)
            or proof.resource_url != str(proof.raw_document.source_url)
        ):
            raise ValueError("Os bytes privados divergem da prova arquivada")

        observations = normalise_initiative_authorships(
            strict_parliament_json(proof.raw_document.content)
        )
        dataset = ParliamentInitiativeAuthorshipDataset(
            legislature=proof.legislature,
            dataset_url=proof.resource_url,
            document_sha256=proof.content_sha256,
            parser_version=PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION,
            observations=observations,
            warnings=(
                "Cobertura histórica não afirmada: são conservadas apenas relações individuais "
                "com iniAutorDeputados/idCadastro no recurso oficial arquivado.",
                "Nome e grupo parlamentar são texto da fonte e nunca servem para ligar pessoas.",
            ),
            collected_at=proof.raw_document.retrieved_at,
            raw_document=proof.raw_document,
        )
        return CollectedParliamentInitiativeAuthorship(
            parent_catalogue_snapshot_id=proof.parent_catalogue_snapshot_id,
            parent_manifest_snapshot_id=proof.parent_manifest_snapshot_id,
            parent_archive_snapshot_id=proof.archive_snapshot_id,
            archive_source_document_id=proof.archive_source_document_id,
            proof_content_sha256=proof.content_sha256,
            dataset=dataset,
        )


class ParliamentInitiativeAuthorshipStager:
    """Repete a cadeia oficial antes da única escrita privada append-only."""

    def __init__(
        self,
        settings: Settings,
        repository: ParliamentInitiativeAuthorshipRepository,
    ) -> None:
        self.settings = settings
        self.repository = repository

    async def store(
        self,
        collection: CollectedParliamentInitiativeAuthorship,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError("As autorias privadas só podem persistir em test ou staging")
        dataset = collection.dataset
        if (
            dataset.parser_version != PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION
            or collection.historical_completeness != PARLIAMENT_AUTHORSHIP_COMPLETENESS
            or collection.publishable
            or collection.editorial_cases_created
        ):
            raise ValueError("A fotografia de autorias diverge do contrato privado")

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
        ):
            raise ValueError("A prova repetida diverge da fotografia de autorias")
        recomputed = ParliamentInitiativeAuthorshipNormalizer().normalise(proof)
        if recomputed != collection:
            raise ValueError("As autorias não coincidem com os bytes oficiais revalidados")

        result = await self.repository.persist_private_authorships(
            dataset,
            source_document_id=proof.archive_source_document_id,
        )
        return {
            **result,
            "parent_catalogue_snapshot_id": proof.parent_catalogue_snapshot_id,
            "parent_manifest_snapshot_id": proof.parent_manifest_snapshot_id,
            "parent_archive_snapshot_id": proof.archive_snapshot_id,
            "historical_completeness": PARLIAMENT_AUTHORSHIP_COMPLETENESS,
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
