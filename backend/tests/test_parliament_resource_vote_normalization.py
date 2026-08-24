import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.api import VoteActorType
from app.models.archive import PrivateRawDocument
from app.repositories.parliament_resource_normalization import (
    PARLIAMENT_HISTORICAL_VOTES_PARSER_VERSION,
    PrivateParliamentArchivedResourceProof,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_resource_vote_normalization import (
    ParliamentResourceVoteNormalizationStager,
    ParliamentResourceVoteNormalizer,
)
from app.services.parliament_source_catalogue import ParliamentCatalogueKind
from scripts.sync_parliament_resource_vote_normalization import (
    validate_private_vote_normalization_operation,
)

CATALOGUE_SNAPSHOT_ID = f"official_index_{'a' * 32}"
MANIFEST_SNAPSHOT_ID = f"official_index_{'b' * 32}"
ARCHIVE_SNAPSHOT_ID = f"official_index_{'c' * 32}"
RESOURCE_URL = (
    "https://app.parlamento.pt/webutils/docs/doc.txt?fich=IniciativasXVII_json.txt&Inline=true"
)


def _payload(
    *,
    result: str = "Aprovado",
    duplicate_result: str | None = None,
    nominal: bool = False,
) -> bytes:
    details: object = (
        [
            {"DeputadoId": "deputy-101", "DeputadoNome": "Pessoa A", "Voto": "A Favor"},
            {"DeputadoId": "deputy-102", "DeputadoNome": "Pessoa B", "Voto": "Contra"},
        ]
        if nominal
        else "A Favor: PSD, PS<BR>Contra: CH"
    )
    votes = [
        {
            "id": "vote-123",
            "data": "2026-08-12",
            "detalhe": details,
            "reuniao": "42",
            "resultado": result,
        }
    ]
    if duplicate_result is not None:
        votes.append({**votes[0], "resultado": duplicate_result})
    return json.dumps(
        {
            "Iniciativas": [
                {
                    "IniId": "initiative-123",
                    "IniNr": "1/XVII/1",
                    "IniDescTipo": "Projeto de Lei",
                    "IniTitulo": "Medida oficial de teste",
                    "IniEventos": [{"Votacao": votes}],
                }
            ]
        },
        ensure_ascii=False,
    ).encode()


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


def test_vote_normalizer_preserves_exact_vote_and_unknown_collective_positions() -> None:
    result = ParliamentResourceVoteNormalizer().normalise(_proof())

    assert result.dataset.parser_version == PARLIAMENT_HISTORICAL_VOTES_PARSER_VERSION
    assert result.dataset.sessions == []
    assert result.dataset.initiatives == []
    assert len(result.dataset.votes) == 1
    vote = result.dataset.votes[0]
    assert vote.source_id == "vote-123"
    assert vote.initiative_number == "1/XVII/1"
    assert vote.result == "Aprovado"
    assert vote.is_nominal is False
    assert {record.actor_label for record in vote.records} == {"PSD", "PS", "CH"}
    assert {record.actor_type for record in vote.records} == {VoteActorType.UNKNOWN}
    assert "3 posições conservam ator UNKNOWN" in result.dataset.warnings[-1]
    assert result.historical_completeness == "NOT_ASSERTED"
    assert result.editorial_cases_created == 0
    assert result.publishable is False


def test_vote_normalizer_preserves_person_only_with_exact_official_identifier() -> None:
    result = ParliamentResourceVoteNormalizer().normalise(_proof(content=_payload(nominal=True)))

    vote = result.dataset.votes[0]
    assert vote.is_nominal is True
    assert {record.actor_source_id for record in vote.records} == {
        "deputy-101",
        "deputy-102",
    }
    assert {record.actor_type for record in vote.records} == {VoteActorType.PERSON}


@pytest.mark.parametrize(
    ("proof", "message"),
    (
        (_proof(content=b"{invalido"), "não contém JSON válido"),
        (_proof(content=b'{"Iniciativas": []}'), "não contém votações normalizáveis"),
        (_proof(resource_format=ParliamentResourceFormat.XML), "apenas o recurso JSON"),
        (
            _proof(content=_payload(duplicate_result="Rejeitado")),
            "identificador oficial.*factos divergentes",
        ),
    ),
)
def test_vote_normalizer_fails_closed_on_invalid_or_ambiguous_input(
    proof: PrivateParliamentArchivedResourceProof,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ParliamentResourceVoteNormalizer().normalise(proof)


@pytest.mark.asyncio
async def test_vote_stager_revalidates_archive_and_does_not_create_case() -> None:
    proof = _proof()
    collection = ParliamentResourceVoteNormalizer().normalise(proof)
    repository = AsyncMock()
    repository.require_archived_resource.return_value = proof
    repository.persist_private_votes.return_value = {
        "sync_run_id": "sync_fixture",
        "source_document_id": proof.archive_source_document_id,
        "normalised_snapshot_id": "parliament_snapshot_fixture",
        "snapshot_created": True,
        "vote_count": 1,
        "vote_record_count": 3,
        "votes_written": 1,
        "vote_records_written": 3,
        "sync_status": "PARTIAL",
        "publishable": False,
    }

    result = await ParliamentResourceVoteNormalizationStager(
        Settings(environment="test"),
        repository,
    ).store(collection)

    assert result["parent_archive_snapshot_id"] == ARCHIVE_SNAPSHOT_ID
    assert result["records_normalised"] == 4
    assert result["historical_completeness"] == "NOT_ASSERTED"
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    repository.persist_private_votes.assert_awaited_once_with(collection.dataset)


@pytest.mark.asyncio
async def test_vote_stager_rejects_content_not_derived_from_archived_bytes() -> None:
    proof = _proof()
    collection = ParliamentResourceVoteNormalizer().normalise(proof)
    altered_vote = collection.dataset.votes[0].model_copy(update={"result": "Rejeitado"})
    altered_dataset = collection.dataset.model_copy(update={"votes": [altered_vote]})
    repository = AsyncMock()
    repository.require_archived_resource.return_value = proof

    with pytest.raises(ValueError, match="não coincide com os bytes revalidados"):
        await ParliamentResourceVoteNormalizationStager(
            Settings(environment="test"),
            repository,
        ).store(replace(collection, dataset=altered_dataset))

    repository.persist_private_votes.assert_not_awaited()


@pytest.mark.asyncio
async def test_vote_stager_rejects_production_and_publication_claim() -> None:
    collection = ParliamentResourceVoteNormalizer().normalise(_proof())
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentResourceVoteNormalizationStager(
            Settings(environment="production"),
            repository,
        ).store(collection)

    with pytest.raises(ValueError, match="contrato privado"):
        await ParliamentResourceVoteNormalizationStager(
            Settings(environment="test"),
            repository,
        ).store(replace(collection, publishable=True))

    repository.require_archived_resource.assert_not_awaited()
    repository.persist_private_votes.assert_not_awaited()


def test_vote_normalization_script_requires_explicit_staging_and_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_vote_normalization_operation(
            Settings(environment="staging"),
            confirmed=False,
        )
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_vote_normalization_operation(
            Settings(environment="test"),
            confirmed=True,
        )
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_vote_normalization_operation(
            Settings(environment="staging", database_url=None),
            confirmed=True,
        )

    validate_private_vote_normalization_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
