import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.repositories.parliament_resource_deputy_normalization import (
    PARLIAMENT_HISTORICAL_DEPUTIES_PARSER_VERSION,
)
from app.repositories.parliament_resource_normalization import (
    PrivateParliamentArchivedResourceProof,
)
from app.services.parliament_resource_deputy_normalization import (
    ParliamentResourceDeputyNormalizationStager,
    ParliamentResourceDeputyNormalizer,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_source_catalogue import ParliamentCatalogueKind
from scripts.sync_parliament_resource_deputy_normalization import (
    validate_private_deputy_normalization_operation,
)

CATALOGUE_SNAPSHOT_ID = f"official_index_{'a' * 32}"
MANIFEST_SNAPSHOT_ID = f"official_index_{'b' * 32}"
ARCHIVE_SNAPSHOT_ID = f"official_index_{'c' * 32}"
RESOURCE_URL = (
    "https://app.parlamento.pt/webutils/docs/doc.txt"
    "?fich=AtividadeDeputadoXVII_json.txt&Inline=true"
)


def _deputy(index: int) -> dict[str, object]:
    return {
        "Deputado": {
            "DepId": f"deputy-{index}",
            "DepCadId": f"candidate-{index}",
            "DepNomeParlamentar": f"Pessoa Deputada {index:03d}",
            "DepNomeCompleto": f"Pessoa Deputada de Teste {index:03d}",
            "DepCPId": f"constituency-{index % 20}",
            "DepCPDes": f"Círculo {index % 20}",
            "DepGP": [
                {
                    "GpId": f"group-{index % 5}",
                    "GpSigla": f"G{index % 5}",
                    "GpDtInicio": "2025-06-03",
                }
            ],
            "DepSituacao": [
                {
                    "SioDes": "Efetivo",
                    "SioDtInicio": "2025-06-03",
                }
            ],
            "DepCargo": [
                {
                    "CarId": f"office-{index}",
                    "CarDes": "Membro de comissão",
                    "CarDtInicio": "2025-06-10",
                }
            ],
            "DepEmail": f"pessoa-{index}@example.invalid",
        },
        "AtividadeDeputadoList": [
            {
                "Ini": [
                    {
                        "DepId": f"reference-{index}",
                        "DepNomeParlamentar": "Referência interna ignorada",
                    }
                ]
            }
        ],
    }


def _payload(*, count: int = 100) -> bytes:
    return json.dumps([_deputy(index) for index in range(count)], ensure_ascii=False).encode()


def _proof(
    *,
    content: bytes | None = None,
    catalogue_kind: ParliamentCatalogueKind = ParliamentCatalogueKind.DEPUTY_ACTIVITY,
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
        catalogue_kind=catalogue_kind,
        legislature="XVII",
        resource_format=resource_format,
        official_label="AtividadeDeputadoXVII_json.txt",
        resource_url=RESOURCE_URL,
        content_sha256=content_sha256,
        byte_size=len(exact_content),
        raw_document=raw_document,
        manifest_content_sha256="d" * 64,
        catalogue_content_sha256="e" * 64,
        archive_attested=True,
    )


def test_deputy_normalizer_preserves_exact_ids_and_omits_email() -> None:
    result = ParliamentResourceDeputyNormalizer().normalise(_proof())

    assert result.dataset.parser_version == PARLIAMENT_HISTORICAL_DEPUTIES_PARSER_VERSION
    assert len(result.dataset.observations) == 100
    observation = result.dataset.observations[0]
    assert observation.source_id == "deputy-0"
    assert observation.candidate_source_id == "candidate-0"
    assert observation.constituency_source_id == "constituency-0"
    assert observation.parliamentary_groups[0].source_id == "group-0"
    assert observation.parliamentary_groups[0].short_name == "G0"
    assert observation.mandate_situations[0].description == "Efetivo"
    assert observation.offices[0].source_id == "office-0"
    assert observation.offices[0].title == "Membro de comissão"
    assert "email" not in type(observation).model_fields
    assert "DepEmail" not in observation.model_dump_json()
    assert result.historical_completeness == "NOT_ASSERTED"
    assert result.editorial_cases_created == 0
    assert result.publishable is False
    assert "não são convertidas automaticamente" in result.dataset.warnings[1]


def test_deputy_normalizer_ignores_people_without_explicit_mandate_evidence() -> None:
    payload = [_deputy(index) for index in range(101)]
    payload[100]["Deputado"]["DepSituacao"] = [{"SioDes": "Suplente"}]  # type: ignore[index]

    result = ParliamentResourceDeputyNormalizer().normalise(
        _proof(content=json.dumps(payload, ensure_ascii=False).encode())
    )

    assert len(result.dataset.observations) == 100
    assert all(item.source_id != "deputy-100" for item in result.dataset.observations)


def test_deputy_normalizer_rejects_conflicting_duplicate_official_id() -> None:
    payload = [_deputy(index) for index in range(100)]
    duplicate = _deputy(0)
    duplicate["Deputado"]["DepNomeParlamentar"] = "Outra pessoa"  # type: ignore[index]
    payload.append(duplicate)

    with pytest.raises(ValueError, match="identificador oficial.*observações divergentes"):
        ParliamentResourceDeputyNormalizer().normalise(
            _proof(content=json.dumps(payload, ensure_ascii=False).encode())
        )


def test_deputy_normalizer_rejects_invalid_dates_and_implausible_counts() -> None:
    payload = [_deputy(index) for index in range(100)]
    payload[0]["Deputado"]["DepCargo"][0]["CarDtInicio"] = "não é uma data"  # type: ignore[index]
    with pytest.raises(ValueError, match="Data oficial inválida"):
        ParliamentResourceDeputyNormalizer().normalise(
            _proof(content=json.dumps(payload, ensure_ascii=False).encode())
        )

    with pytest.raises(ValueError, match="fora do intervalo de segurança"):
        ParliamentResourceDeputyNormalizer().normalise(_proof(content=_payload(count=99)))


def test_deputy_normalizer_preserves_inverted_official_interval_with_warning() -> None:
    payload = [_deputy(index) for index in range(100)]
    situation = payload[0]["Deputado"]["DepSituacao"][0]  # type: ignore[index]
    situation["SioDtFim"] = "2025-01-01"  # type: ignore[index]

    result = ParliamentResourceDeputyNormalizer().normalise(
        _proof(content=json.dumps(payload, ensure_ascii=False).encode())
    )

    preserved = result.dataset.observations[0].mandate_situations[0]
    assert preserved.ends_at is not None
    assert preserved.starts_at is not None
    assert preserved.ends_at < preserved.starts_at
    assert "1 intervalos oficiais" in result.dataset.warnings[-1]
    assert "não podem originar mandatos" in result.dataset.warnings[-1]


def test_deputy_normalizer_rejects_insufficient_exact_metadata_coverage() -> None:
    payload = [_deputy(index) for index in range(100)]
    for item in payload[:31]:
        deputy = item["Deputado"]  # type: ignore[index]
        deputy.pop("DepCPId")  # type: ignore[union-attr]
        deputy["DepGP"][0].pop("GpId")  # type: ignore[index,union-attr]

    with pytest.raises(ValueError, match="cobertura insuficiente de IDs oficiais"):
        ParliamentResourceDeputyNormalizer().normalise(
            _proof(content=json.dumps(payload, ensure_ascii=False).encode())
        )


@pytest.mark.parametrize(
    ("proof", "message"),
    (
        (_proof(content="{inválido".encode()), "não contém JSON válido"),
        (
            _proof(catalogue_kind=ParliamentCatalogueKind.ACTIVITIES),
            "apenas o recurso JSON de atividade dos deputados",
        ),
        (
            _proof(resource_format=ParliamentResourceFormat.XML),
            "apenas o recurso JSON de atividade dos deputados",
        ),
    ),
)
def test_deputy_normalizer_fails_closed_on_wrong_resource(
    proof: PrivateParliamentArchivedResourceProof,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ParliamentResourceDeputyNormalizer().normalise(proof)


@pytest.mark.asyncio
async def test_deputy_stager_revalidates_archive_and_does_not_create_case() -> None:
    proof = _proof()
    collection = ParliamentResourceDeputyNormalizer().normalise(proof)
    repository = AsyncMock()
    repository.require_archived_resource.return_value = proof
    repository.persist_private_deputy_observations.return_value = {
        "sync_run_id": "sync_fixture",
        "source_document_id": proof.archive_source_document_id,
        "normalised_snapshot_id": "parliament_deputy_snapshot_fixture",
        "snapshot_created": True,
        "deputy_count": 100,
        "group_period_count": 100,
        "situation_period_count": 100,
        "office_period_count": 100,
        "observations_written": 100,
        "sync_status": "PARTIAL",
        "publishable": False,
    }

    result = await ParliamentResourceDeputyNormalizationStager(
        Settings(environment="test"),
        repository,
    ).store(collection)

    assert result["parent_archive_snapshot_id"] == ARCHIVE_SNAPSHOT_ID
    assert result["records_normalised"] == 400
    assert result["historical_completeness"] == "NOT_ASSERTED"
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    repository.persist_private_deputy_observations.assert_awaited_once_with(
        collection.dataset,
        expected_source_document_id=proof.archive_source_document_id,
    )


@pytest.mark.asyncio
async def test_deputy_stager_rejects_content_not_derived_from_archived_bytes() -> None:
    proof = _proof()
    collection = ParliamentResourceDeputyNormalizer().normalise(proof)
    altered = collection.dataset.observations[0].model_copy(
        update={"parliamentary_name": "Nome alterado"}
    )
    altered_dataset = collection.dataset.model_copy(
        update={"observations": (altered, *collection.dataset.observations[1:])}
    )
    repository = AsyncMock()
    repository.require_archived_resource.return_value = proof

    with pytest.raises(ValueError, match="não coincide com os bytes revalidados"):
        await ParliamentResourceDeputyNormalizationStager(
            Settings(environment="test"),
            repository,
        ).store(replace(collection, dataset=altered_dataset))

    repository.persist_private_deputy_observations.assert_not_awaited()


@pytest.mark.asyncio
async def test_deputy_stager_rejects_production_and_publication_claim() -> None:
    collection = ParliamentResourceDeputyNormalizer().normalise(_proof())
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentResourceDeputyNormalizationStager(
            Settings(environment="production"),
            repository,
        ).store(collection)

    with pytest.raises(ValueError, match="contrato privado"):
        await ParliamentResourceDeputyNormalizationStager(
            Settings(environment="test"),
            repository,
        ).store(replace(collection, publishable=True))

    repository.require_archived_resource.assert_not_awaited()
    repository.persist_private_deputy_observations.assert_not_awaited()


def test_deputy_normalization_script_requires_explicit_staging_and_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_deputy_normalization_operation(
            Settings(environment="staging"),
            confirmed=False,
        )
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_deputy_normalization_operation(
            Settings(environment="test"),
            confirmed=True,
        )
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_deputy_normalization_operation(
            Settings(environment="staging", database_url=None),
            confirmed=True,
        )

    validate_private_deputy_normalization_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
