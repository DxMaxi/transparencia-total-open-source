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
    PARLIAMENT_HISTORICAL_INITIATIVES_PARSER_VERSION,
    PrivateParliamentArchivedResourceProof,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_resource_normalization import (
    ParliamentResourceNormalizationStager,
    ParliamentResourceNormalizer,
)
from app.services.parliament_source_catalogue import ParliamentCatalogueKind
from scripts.sync_parliament_resource_normalization import (
    validate_private_normalization_operation,
)

CATALOGUE_SNAPSHOT_ID = f"official_index_{'a' * 32}"
MANIFEST_SNAPSHOT_ID = f"official_index_{'b' * 32}"
ARCHIVE_SNAPSHOT_ID = f"official_index_{'c' * 32}"
RESOURCE_URL = (
    "https://app.parlamento.pt/webutils/docs/doc.txt?fich=IniciativasXVII_json.txt&Inline=true"
)


def _payload(*, duplicate_title: str | None = None) -> bytes:
    records = [
        {
            "IniId": "12345",
            "IniNr": "1/XVII/1",
            "IniDescTipo": "Projeto de Lei",
            "IniTitulo": "Medida oficial de teste",
            "IniLinkTexto": "/ActividadeParlamentar/Paginas/DetalheIniciativa.aspx?BID=12345",
            "IniEventos": [
                {"DataFase": "2026-08-01", "Fase": "Entrada"},
                {"DataFase": "2026-08-12", "Fase": "Discussão"},
            ],
        }
    ]
    if duplicate_title is not None:
        records.append({**records[0], "IniTitulo": duplicate_title})
    return json.dumps({"Iniciativas": records}, ensure_ascii=False).encode()


def _proof(
    *,
    content: bytes | None = None,
    resource_format: ParliamentResourceFormat = ParliamentResourceFormat.JSON,
) -> PrivateParliamentArchivedResourceProof:
    exact_content = content if content is not None else _payload()
    content_sha256 = hashlib.sha256(exact_content).hexdigest()
    raw_document = PrivateRawDocument(
        source_url=HttpUrl(RESOURCE_URL),
        retrieved_at=datetime(2026, 8, 24, tzinfo=UTC),
        content_sha256=content_sha256,
        mime_type="application/json",
        content=exact_content,
    )
    return PrivateParliamentArchivedResourceProof(
        archive_snapshot_id=ARCHIVE_SNAPSHOT_ID,
        archive_source_document_id="source_archive",
        parent_manifest_snapshot_id=MANIFEST_SNAPSHOT_ID,
        parent_catalogue_snapshot_id=CATALOGUE_SNAPSHOT_ID,
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        resource_format=resource_format,
        official_label="IniciativasXVII_json.txt",
        resource_url=RESOURCE_URL,
        content_sha256=content_sha256,
        byte_size=len(exact_content),
        raw_document=raw_document,
        manifest_content_sha256="d" * 64,
        catalogue_content_sha256="e" * 64,
        archive_attested=True,
    )


def test_normalizer_uses_only_exact_official_initiative_identifiers() -> None:
    result = ParliamentResourceNormalizer().normalise(_proof())

    assert result.dataset.parser_version == PARLIAMENT_HISTORICAL_INITIATIVES_PARSER_VERSION
    assert result.dataset.sessions == []
    assert result.dataset.votes == []
    assert len(result.dataset.initiatives) == 1
    initiative = result.dataset.initiatives[0]
    assert initiative.source_id == "12345"
    assert initiative.number == "1/XVII/1"
    assert initiative.status == "Discussão"
    assert str(initiative.official_url).startswith("https://www.parlamento.pt/")
    assert result.historical_completeness == "NOT_ASSERTED"
    assert result.editorial_cases_created == 0
    assert result.publishable is False


@pytest.mark.parametrize(
    ("proof", "message"),
    (
        (_proof(content=b"{invalido"), "não contém JSON válido"),
        (_proof(resource_format=ParliamentResourceFormat.XML), "apenas o recurso JSON"),
        (
            _proof(content=_payload(duplicate_title="Título divergente")),
            "identificador oficial.*divergentes",
        ),
    ),
)
def test_normalizer_fails_closed_on_invalid_or_ambiguous_input(
    proof: PrivateParliamentArchivedResourceProof,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ParliamentResourceNormalizer().normalise(proof)


def test_normalizer_rejects_external_initiative_url() -> None:
    payload = json.loads(_payload().decode())
    payload["Iniciativas"][0]["IniLinkTexto"] = "https://example.org/falso"

    with pytest.raises(ValueError, match="URL parlamentar não autorizada"):
        ParliamentResourceNormalizer().normalise(_proof(content=json.dumps(payload).encode()))


@pytest.mark.asyncio
async def test_normalization_stager_revalidates_archive_and_does_not_create_case() -> None:
    proof = _proof()
    collection = ParliamentResourceNormalizer().normalise(proof)
    repository = AsyncMock()
    repository.require_archived_resource.return_value = proof
    repository.persist_private_initiatives.return_value = {
        "sync_run_id": "sync_fixture",
        "source_document_id": proof.archive_source_document_id,
        "normalised_snapshot_id": "parliament_snapshot_fixture",
        "snapshot_created": True,
        "initiative_count": 1,
        "initiatives_written": 1,
        "sync_status": "PARTIAL",
        "publishable": False,
    }

    result = await ParliamentResourceNormalizationStager(
        Settings(environment="test"),
        repository,
    ).store(collection)

    assert result["parent_archive_snapshot_id"] == ARCHIVE_SNAPSHOT_ID
    assert result["records_normalised"] == 1
    assert result["historical_completeness"] == "NOT_ASSERTED"
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    repository.persist_private_initiatives.assert_awaited_once_with(collection.dataset)


@pytest.mark.asyncio
async def test_normalization_stager_rejects_content_not_derived_from_archived_bytes() -> None:
    proof = _proof()
    collection = ParliamentResourceNormalizer().normalise(proof)
    altered_initiative = collection.dataset.initiatives[0].model_copy(
        update={"title": "Título não existente nos bytes oficiais"}
    )
    altered_dataset = collection.dataset.model_copy(update={"initiatives": [altered_initiative]})
    repository = AsyncMock()
    repository.require_archived_resource.return_value = proof

    with pytest.raises(ValueError, match="não coincide com os bytes oficiais"):
        await ParliamentResourceNormalizationStager(
            Settings(environment="test"),
            repository,
        ).store(replace(collection, dataset=altered_dataset))

    repository.persist_private_initiatives.assert_not_awaited()


@pytest.mark.asyncio
async def test_normalization_stager_rejects_production_and_publication_claim() -> None:
    collection = ParliamentResourceNormalizer().normalise(_proof())
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentResourceNormalizationStager(
            Settings(environment="production"),
            repository,
        ).store(collection)

    with pytest.raises(ValueError, match="contrato privado"):
        await ParliamentResourceNormalizationStager(
            Settings(environment="test"),
            repository,
        ).store(replace(collection, publishable=True))

    repository.require_archived_resource.assert_not_awaited()
    repository.persist_private_initiatives.assert_not_awaited()


def test_normalization_script_requires_explicit_staging_and_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_normalization_operation(Settings(environment="staging"), confirmed=False)
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_normalization_operation(Settings(environment="test"), confirmed=True)
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_normalization_operation(
            Settings(environment="staging", database_url=None),
            confirmed=True,
        )

    validate_private_normalization_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
