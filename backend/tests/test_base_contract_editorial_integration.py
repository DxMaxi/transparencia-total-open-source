"""Integração real da porta privada BASE numa base PostgreSQL descartável."""

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    BaseContractEditorialProposalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.base_catalogue_staging import BaseCatalogueStagingRepository
from app.repositories.base_contract_editorial import BaseContractEditorialRepository
from app.repositories.editorial import EditorialSourceError
from app.repositories.postgres import PostgresRepository
from app.services.base_catalogue_scope import (
    extract_base_catalogue_scope,
    load_base_catalogue_manifest,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


def _catalogue_bytes() -> bytes:
    resources: list[dict[str, object]] = []
    for year in range(2012, 2027):
        resource_id = f"{year:08x}-1234-4abc-8def-{year:012x}"
        resources.append(
            {
                "id": resource_id,
                "title": f"contratos{year}.zip",
                "format": "zip",
                "url": (
                    "https://dados.gov.pt/s/resources/contratos-publicos-portal-base-impic-"
                    f"contratos-de-2012-a-2026/20260823/contratos{year}.zip"
                ),
                "latest": f"https://dados.gov.pt/api/1/datasets/r/{resource_id}",
                "last_modified": "2026-08-25T10:04:17.578+01:00",
                "filesize": 1_000_000 + year,
            }
        )
    return json.dumps(
        {
            "id": "66d72d488ca4b7cb2de28712",
            "title": "Contratos Públicos - Portal Base - IMPIC - Contratos de 2012 a 2026",
            "organization": {
                "id": "5ae97fa2c8d8c915d5faa3bf",
                "name": ("IMPIC - Instituto Dos Mercados Públicos, do Imobiliário e da Construção"),
            },
            "license": "other-pd",
            "frequency": "weekly",
            "private": False,
            "page": (
                "https://dados.gov.pt/datasets/"
                "contratos-publicos-portal-base-impic-contratos-de-2012-a-2026"
            ),
            "last_modified": "2026-08-26T11:53:45.607+01:00",
            "resources": resources,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


async def _prepare_disposable_auth_user(
    connection: asyncpg.Connection,
    auth_user_id: uuid.UUID,
) -> None:
    if not await connection.fetchval("SELECT to_regclass('auth.users') IS NOT NULL"):
        return
    if not await connection.fetchval(
        "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
    ):
        pytest.skip("A FK auth.users só é exercitada numa base descartável identificada")
    await connection.execute(
        "INSERT INTO auth.users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
        auth_user_id,
    )


async def _require_disposable_database(pool: asyncpg.Pool) -> None:
    """Falha antes da primeira escrita se o destino não for inequivocamente descartável."""

    async with pool.acquire() as connection:
        database_name = str(await connection.fetchval("SELECT current_database()"))
        marker_exists = bool(
            await connection.fetchval(
                "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
            )
        )
        marker_value = False
        if marker_exists:
            marker_value = bool(
                await connection.fetchval(
                    "SELECT singleton FROM auth.tt_disposable_test_marker WHERE singleton = TRUE"
                )
            )
    if not database_name.endswith("_test") or not marker_exists or not marker_value:
        pytest.fail(
            "O teste BASE recusou escrever: DATABASE_URL não aponta para uma base _test "
            "com o marcador descartável confirmado"
        )


@pytest.fixture
async def repository() -> PostgresRepository:
    repo = PostgresRepository(
        Settings(environment="test", protected_identifier_pepper=SecretStr("p" * 32))
    )
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


async def _ensure_catalogue_scope() -> str:
    catalogue = BaseCatalogueStagingRepository(Settings(environment="test"))
    await catalogue.connect()
    try:
        manifest = load_base_catalogue_manifest()
        content = _catalogue_bytes()
        retrieved_at = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
        raw = PrivateRawDocument(
            source_url=manifest.catalogue_api_url,
            retrieved_at=retrieved_at,
            content_sha256=hashlib.sha256(content).hexdigest(),
            mime_type="application/json",
            content=content,
        )
        scope = extract_base_catalogue_scope(
            catalogue_bytes=content,
            retrieved_at=retrieved_at,
            manifest=manifest,
        )
        receipt = await catalogue.archive_raw_document(raw_document=raw)
        result = await catalogue.stage_scope(
            raw_document=raw,
            archive_receipt=receipt,
            manifest=manifest,
            scope=scope,
            staged_by_alias="pytest-base-editorial",
        )
        return str(result["scope_id"])
    finally:
        await catalogue.close()


@pytest.mark.asyncio
async def test_base_contract_enters_only_private_editorial_case(
    repository: PostgresRepository,
) -> None:
    assert repository.pool is not None
    await _require_disposable_database(repository.pool)
    scope_id = await _ensure_catalogue_scope()
    suffix = uuid.uuid4().hex[:12]
    source_sha256 = hashlib.sha256(f"base-contract:{suffix}".encode()).hexdigest()
    protected_digest = hashlib.sha256(f"protected:{suffix}".encode()).hexdigest()
    resource_url = (
        "https://dados.gov.pt/s/resources/contratos-publicos-portal-base-impic-"
        "contratos-de-2012-a-2026/20260823/contratos2025.zip"
    )
    collected_at = datetime(2026, 8, 29, 11, 0, tzinfo=UTC).replace(tzinfo=None)
    auth_user_id = uuid.uuid4()
    staff_id = f"staff_base_{suffix}"
    alias = f"revisor-base-{suffix}"
    source_document_id = f"source_base_{suffix}"
    batch_id = f"batch_base_{suffix}"
    contract_snapshot_id = f"contract_base_{suffix}"
    official_contract_id = f"BASE-{suffix}"

    async with repository.pool.acquire() as connection, connection.transaction():
        assert await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM base_contract_catalogue_resources "
            "WHERE scope_id = $1 AND resource_year = 2025)",
            scope_id,
        )
        await connection.execute(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, url, retrieved_at, content_sha256,
                 mime_type, parser_version, created_at)
            VALUES ($1, 'BASE_GOV', 'OPEN_DATASET', 'Portal BASE — contratos — 2025',
                    $2, $3, $4, 'application/zip', 'base-contracts-test-v1', NOW())
            """,
            source_document_id,
            resource_url,
            collected_at,
            source_sha256,
        )
        await connection.execute(
            """
            INSERT INTO source_archive_attestations
                (id, source_document_id, storage_backend, storage_key,
                 content_sha256, byte_size, mime_type, retrieval_url,
                 retrieved_at, archived_at, archived_by,
                 attestation_sha256, created_at)
            VALUES ($1, $2, 'POSTGRES', $3, $4, 1002025, 'application/zip',
                    $5, $6, $6, 'test:v5.50', $7, NOW())
            """,
            f"archive_base_{suffix}",
            source_document_id,
            f"sha256/{source_sha256[:2]}/{source_sha256}",
            source_sha256,
            resource_url,
            collected_at,
            hashlib.sha256(f"attestation:{suffix}".encode()).hexdigest(),
        )
        await connection.execute(
            """
            INSERT INTO sync_runs
                (id, source_name, dataset_url, status, started_at, finished_at,
                 records_read, records_written, warnings, code_version)
            VALUES ($1, 'BASE_GOV', $2, 'SUCCEEDED', $3, $3, 1, 2, '[]'::jsonb,
                    'base-contracts-test-v1')
            """,
            f"run_base_{suffix}",
            resource_url,
            collected_at,
        )
        await connection.execute(
            """
            INSERT INTO base_staging_batches
                (id, source_document_id, sync_run_id, resource_year, resource_title,
                 resource_format, parser_version, normalised_sha256,
                 identifier_digests_stored, contract_count, party_count,
                 collected_at, created_at)
            VALUES ($1, $2, $3, 2025, 'contratos2025.zip', 'ZIP',
                    'base-contracts-test-v1', $4, TRUE, 1, 1, $5, NOW())
            """,
            batch_id,
            source_document_id,
            f"run_base_{suffix}",
            hashlib.sha256(f"batch:{suffix}".encode()).hexdigest(),
            collected_at,
        )
        await connection.execute(
            """
            INSERT INTO base_contract_snapshots
                (id, batch_id, source_id, object, procedure, cpv_code, contract_value,
                 currency, published_at, direct_official_url, created_at)
            VALUES ($1, $2, $3, 'Aquisição pública para teste editorial',
                    'PUBLIC_TENDER', '45000000-7', 123456789.00, 'EUR', $4,
                    'https://www.base.gov.pt/Base4/pt/detalhe/?type=contratos&id=1', NOW())
            """,
            contract_snapshot_id,
            batch_id,
            official_contract_id,
            collected_at,
        )
        await connection.execute(
            """
            INSERT INTO base_contract_party_snapshots
                (id, contract_snapshot_id, ordinal, role, source_name,
                 protected_identifier_digest, created_at)
            VALUES ($1, $2, 0, 'CONTRACTOR', 'Fornecedor Oficial de Teste, Lda.', $3, NOW())
            """,
            f"party_base_{suffix}",
            contract_snapshot_id,
            protected_digest,
        )
        await _prepare_disposable_auth_user(connection, auth_user_id)
        await connection.execute(
            """
            INSERT INTO staff_profiles
                (id, auth_user_id, public_alias, role, active, created_at, updated_at)
            VALUES ($1, $2, $3, 'REVIEWER', TRUE, NOW(), NOW())
            """,
            staff_id,
            auth_user_id,
            alias,
        )
        before = await connection.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM public_contracts) AS contracts,
              (SELECT COUNT(*) FROM organisations) AS organisations,
              (SELECT COUNT(*) FROM interest_entities) AS entities,
              (SELECT COUNT(*) FROM contract_match_reviews) AS matches,
              (SELECT COUNT(*) FROM interest_relationships) AS relationships
            """
        )

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )
    editorial = BaseContractEditorialRepository(repository.pool)
    listed = await editorial.list_candidates(
        query=official_contract_id,
        resource_year=2025,
        limit=20,
        cursor=None,
    )
    assert listed["total"] == 1
    candidate = listed["items"][0]
    assert candidate["proposal_eligible"] is True
    assert candidate["protected_identifier_exposed"] is False
    assert candidate["protected_identifier_count"] == 1
    assert candidate["parties"] == [
        {
            "id": f"party_base_{suffix}",
            "ordinal": 0,
            "role": "CONTRACTOR",
            "source_name": "Fornecedor Oficial de Teste, Lda.",
            "protected_identifier_observed": True,
        }
    ]
    assert protected_digest not in json.dumps(candidate, ensure_ascii=False)

    request = BaseContractEditorialProposalRequest(
        contract_snapshot_id=contract_snapshot_id,
        source_record_sha256=str(candidate["source_record_sha256"]),
        confirm_private_only=True,
        confirm_normalized_batch_consistency=True,
        confirm_exact_official_contract_id=True,
        confirm_no_party_identity_or_name_matching=True,
        confirm_organisations_require_independent_sources=True,
        confirm_no_contract_or_relationship_publication=True,
    )
    stale_request = request.model_copy(update={"source_record_sha256": "0" * 64})
    with pytest.raises(EditorialSourceError, match="prova deixou de coincidir"):
        await editorial.create_proposal(payload=stale_request, actor=actor)

    created = await editorial.create_proposal(payload=request, actor=actor)
    repeated = await editorial.create_proposal(payload=request, actor=actor)
    assert created["created"] is True
    assert repeated["created"] is False
    assert repeated["case"]["id"] == created["case"]["id"]
    assert created["case"]["current_state"] == "PENDING"
    assert created["publication_performed"] is False

    async with repository.pool.acquire() as connection:
        after = await connection.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM public_contracts) AS contracts,
              (SELECT COUNT(*) FROM organisations) AS organisations,
              (SELECT COUNT(*) FROM interest_entities) AS entities,
              (SELECT COUNT(*) FROM contract_match_reviews) AS matches,
              (SELECT COUNT(*) FROM interest_relationships) AS relationships
            """
        )
        publication_events = await connection.fetchval(
            "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
            created["case"]["id"],
        )
        private_counts = await connection.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM editorial_cases WHERE id = $1) AS cases,
              (SELECT COUNT(*) FROM editorial_versions WHERE case_id = $1) AS versions,
              (SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1) AS decisions
            """,
            created["case"]["id"],
        )
        normalized_json = await connection.fetchval(
            "SELECT normalized_json::text FROM editorial_versions WHERE case_id = $1",
            created["case"]["id"],
        )
    assert dict(after) == dict(before)
    assert publication_events == 0
    assert dict(private_counts) == {"cases": 1, "versions": 1, "decisions": 1}
    persisted = json.loads(str(normalized_json))
    assert persisted["candidate"]["cpv_code"] == "45000000-7"
    assert persisted["candidate"]["contract_value"] == "123456789.00"
    assert persisted["candidate"]["parties"][0]["source_name"] == (
        "Fornecedor Oficial de Teste, Lda."
    )
    assert protected_digest not in json.dumps(persisted, ensure_ascii=False)

    for entity_type in ("PUBLIC_CONTRACT", "INTEREST_ENTITY", "INTEREST_RELATIONSHIP"):
        with pytest.raises(ValueError, match="porta editorial BASE específica"):
            await repository.review_publication(
                entity_type=entity_type,
                entity_id="legacy-entity",
                publish=True,
                reviewer_alias=alias,
                rationale="A porta genérica tem de permanecer fechada durante este teste.",
            )
    with pytest.raises(ValueError, match="promoção BASE genérica foi desativada"):
        await repository.propose_base_contract_for_review(
            contract_snapshot_id=contract_snapshot_id,
            reviewer_alias=alias,
        )
    with pytest.raises(ValueError, match="promoção BASE genérica foi desativada"):
        await repository.mark_base_batch_publication_eligible(
            batch_id=batch_id,
            reviewed_by=alias,
        )
