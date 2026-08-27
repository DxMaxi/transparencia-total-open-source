import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.parliament_resource_normalization import (
    PrivateParliamentArchivedResourceProof,
)
from app.services.parliament_initiative_authorship import (
    ParliamentInitiativeAuthorshipNormalizer,
    ParliamentInitiativeAuthorshipStager,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_source_catalogue import ParliamentCatalogueKind
from scripts.sync_parliament_initiative_authorship import (
    validate_private_authorship_operation,
)

CATALOGUE_SNAPSHOT_ID = f"official_index_{'a' * 32}"
MANIFEST_SNAPSHOT_ID = f"official_index_{'b' * 32}"
ARCHIVE_SNAPSHOT_ID = f"official_index_{'c' * 32}"
RESOURCE_URL = (
    "https://app.parlamento.pt/webutils/docs/doc.txt?fich=IniciativasXVII_json.txt&Inline=true"
)


def _initiative(
    initiative_id: str,
    authors: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "IniId": initiative_id,
        "IniNr": f"{initiative_id}/XVII/1",
        "IniDescTipo": "Projeto de Lei",
        "IniTitulo": f"Iniciativa oficial {initiative_id}",
        "IniLinkTexto": (
            f"/ActividadeParlamentar/Paginas/DetalheIniciativa.aspx?BID={initiative_id}"
        ),
        "iniAutorDeputados": {
            "Iniciativas_AutoresDeputadosOut": authors,
        },
    }


def _payload() -> bytes:
    return json.dumps(
        {
            "Iniciativas": [
                _initiative(
                    "12345",
                    [
                        {"idCadastro": 7489, "Nome": " Adriana Rodrigues ", "GP": "PSD"},
                        {"idCadastro": "7339", "Nome": "Joana Cordeiro", "GP": "IL"},
                    ],
                ),
                _initiative(
                    "67890",
                    [{"idCadastro": "7339", "Nome": "Joana Cordeiro", "GP": "IL"}],
                ),
            ]
        },
        ensure_ascii=False,
    ).encode()


def _proof(
    *,
    content: bytes | None = None,
    catalogue_kind: ParliamentCatalogueKind = ParliamentCatalogueKind.INITIATIVES,
    resource_format: ParliamentResourceFormat = ParliamentResourceFormat.JSON,
) -> PrivateParliamentArchivedResourceProof:
    exact_content = content if content is not None else _payload()
    digest = hashlib.sha256(exact_content).hexdigest()
    document = PrivateRawDocument(
        source_url=HttpUrl(RESOURCE_URL),
        retrieved_at=datetime(2026, 8, 27, tzinfo=UTC),
        content_sha256=digest,
        mime_type="application/json",
        content=exact_content,
    )
    return PrivateParliamentArchivedResourceProof(
        archive_snapshot_id=ARCHIVE_SNAPSHOT_ID,
        archive_source_document_id="source_archive",
        parent_manifest_snapshot_id=MANIFEST_SNAPSHOT_ID,
        parent_catalogue_snapshot_id=CATALOGUE_SNAPSHOT_ID,
        catalogue_kind=catalogue_kind,
        legislature="XVII",
        resource_format=resource_format,
        official_label="IniciativasXVII_json.txt",
        resource_url=RESOURCE_URL,
        content_sha256=digest,
        byte_size=len(exact_content),
        raw_document=document,
        manifest_content_sha256="d" * 64,
        catalogue_content_sha256="e" * 64,
        archive_attested=True,
    )


def test_normalizer_preserves_only_exact_idcadastro_authorships() -> None:
    result = ParliamentInitiativeAuthorshipNormalizer().normalise(_proof())

    assert result.historical_completeness == "NOT_ASSERTED"
    assert result.publishable is False
    assert result.editorial_cases_created == 0
    assert len(result.dataset.observations) == 3
    assert [
        (item.initiative_source_id, item.official_deputy_id) for item in result.dataset.observations
    ] == [("12345", "7339"), ("12345", "7489"), ("67890", "7339")]
    first = result.dataset.observations[0]
    assert first.parliamentary_name == "Joana Cordeiro"
    assert first.parliamentary_group_label == "IL"
    assert first.relation.value == "AUTHOR"
    assert "idCadastro" in result.dataset.warnings[0]
    assert "nunca servem para ligar pessoas" in result.dataset.warnings[1]


def test_normalizer_fails_closed_without_exact_id_or_with_divergent_duplicate() -> None:
    missing_id = json.dumps(
        {"Iniciativas": [_initiative("12345", [{"Nome": "Nome apenas", "GP": "PSD"}])]},
        ensure_ascii=False,
    ).encode()
    with pytest.raises(ValueError, match="idCadastro e nome oficiais"):
        ParliamentInitiativeAuthorshipNormalizer().normalise(_proof(content=missing_id))

    divergent = json.dumps(
        {
            "Iniciativas": [
                _initiative(
                    "12345",
                    [
                        {"idCadastro": "7339", "Nome": "Nome A", "GP": "IL"},
                        {"idCadastro": "7339", "Nome": "Nome B", "GP": "IL"},
                    ],
                )
            ]
        },
        ensure_ascii=False,
    ).encode()
    with pytest.raises(ValueError, match="autorias divergentes"):
        ParliamentInitiativeAuthorshipNormalizer().normalise(_proof(content=divergent))


@pytest.mark.parametrize(
    "proof",
    (
        _proof(catalogue_kind=ParliamentCatalogueKind.ACTIVITIES),
        _proof(resource_format=ParliamentResourceFormat.XML),
        replace(_proof(), archive_attested=False),
        replace(_proof(), publishable=True),
    ),
)
def test_normalizer_rejects_wrong_or_unattested_resource(
    proof: PrivateParliamentArchivedResourceProof,
) -> None:
    with pytest.raises(ValueError):
        ParliamentInitiativeAuthorshipNormalizer().normalise(proof)


@pytest.mark.asyncio
async def test_stager_revalidates_archive_and_creates_no_case_or_publication() -> None:
    proof = _proof()
    collection = ParliamentInitiativeAuthorshipNormalizer().normalise(proof)
    repository = AsyncMock()
    repository.require_archived_resource.return_value = proof
    repository.persist_private_authorships.return_value = {
        "sync_run_id": "sync_fixture",
        "source_document_id": proof.archive_source_document_id,
        "normalised_snapshot_id": "authorship_snapshot_fixture",
        "snapshot_created": True,
        "initiative_count": 2,
        "authorship_count": 3,
        "deputy_count": 2,
        "observations_written": 3,
        "sync_status": "PARTIAL",
        "people_created": 0,
        "editorial_cases_created": 0,
        "publication_performed": False,
        "publishable": False,
    }

    result = await ParliamentInitiativeAuthorshipStager(
        Settings(environment="test"), repository
    ).store(collection)

    assert result["parent_archive_snapshot_id"] == ARCHIVE_SNAPSHOT_ID
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    repository.persist_private_authorships.assert_awaited_once_with(
        collection.dataset,
        source_document_id=proof.archive_source_document_id,
    )

    altered = collection.dataset.observations[0].model_copy(
        update={"parliamentary_name": "Nome que não consta da fonte"}
    )
    changed = replace(
        collection,
        dataset=collection.dataset.model_copy(
            update={"observations": (altered, *collection.dataset.observations[1:])}
        ),
    )
    with pytest.raises(ValueError, match="não coincidem com os bytes oficiais"):
        await ParliamentInitiativeAuthorshipStager(Settings(environment="test"), repository).store(
            changed
        )


@pytest.mark.asyncio
async def test_stager_rejects_production() -> None:
    collection = ParliamentInitiativeAuthorshipNormalizer().normalise(_proof())
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentInitiativeAuthorshipStager(
            Settings(environment="production"), repository
        ).store(collection)
    repository.require_archived_resource.assert_not_awaited()


def test_script_requires_explicit_private_staging_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_authorship_operation(Settings(environment="staging"), confirmed=False)
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_authorship_operation(Settings(environment="test"), confirmed=True)
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_authorship_operation(
            Settings(environment="staging", database_url=None), confirmed=True
        )
    validate_private_authorship_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
