"""Ciclo editorial real numa base descartável com todas as migrações aplicadas."""

import hashlib
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

from app.core.config import Settings
from app.models.editorial import (
    EditorialAction,
    EditorialCaseCreateRequest,
    EditorialCorrectionRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialRepository
from app.repositories.official_index_staging import OfficialIndexStagingRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


async def _prepare_disposable_auth_user(
    connection: asyncpg.Connection,
    auth_user_id: uuid.UUID,
) -> None:
    auth_users_exists = await connection.fetchval("SELECT to_regclass('auth.users') IS NOT NULL")
    if not auth_users_exists:
        return
    marker_exists = await connection.fetchval(
        "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
    )
    if not marker_exists:
        pytest.skip("A FK auth.users só é exercitada numa base descartável identificada")
    await connection.execute(
        "INSERT INTO auth.users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
        auth_user_id,
    )


@pytest.fixture
async def repository() -> OfficialIndexStagingRepository:
    repo = OfficialIndexStagingRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_full_private_editorial_cycle_is_versioned_and_never_publishes(
    repository: OfficialIndexStagingRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex
    now = datetime.now(UTC).replace(tzinfo=None)
    auth_user_id = uuid.uuid4()
    staff_id = f"staff_{suffix}"
    source_id = f"source_{suffix}"
    content = f"fonte-editorial-{suffix}".encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    source_url = f"https://www.parlamento.pt/testes/editorial-{suffix}.json"

    async with repository.pool.acquire() as connection, connection.transaction():
        await _prepare_disposable_auth_user(connection, auth_user_id)
        await connection.execute(
            """
            INSERT INTO staff_profiles
                (id, auth_user_id, public_alias, role, active, created_at, updated_at)
            VALUES ($1, $2, $3, 'REVIEWER', TRUE, $4, $4)
            """,
            staff_id,
            auth_user_id,
            f"revisor-{suffix[:10]}",
            now,
        )
        await connection.execute(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, url, retrieved_at,
                 content_sha256, mime_type, created_at)
            VALUES ($1, 'PARLIAMENT', 'OPEN_DATASET', $2, $3, $4, $5,
                    'application/json', $4)
            """,
            source_id,
            "Fonte editorial de integração",
            source_url,
            now,
            content_sha256,
        )
        await connection.execute(
            """
            INSERT INTO source_archive_attestations
                (id, source_document_id, storage_backend, storage_key,
                 content_sha256, byte_size, mime_type, retrieval_url,
                 retrieved_at, archived_at, archived_by, attestation_sha256)
            VALUES ($1, $2, 'POSTGRES', $3, $4, $5, 'application/json',
                    $6, $7, $7, 'integration-test', $8)
            """,
            f"archive_{suffix}",
            source_id,
            f"sha256/{content_sha256[:2]}/{content_sha256}",
            content_sha256,
            len(content),
            source_url,
            now,
            hashlib.sha256(f"attestation-{suffix}".encode()).hexdigest(),
        )

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=f"revisor-{suffix[:10]}",
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )
    editorial = EditorialRepository(repository.pool)
    created = await editorial.create_case(
        payload=EditorialCaseCreateRequest(
            kind="PARLIAMENT_ACTIVITY",
            subject_type="PARLIAMENT_SNAPSHOT",
            subject_id=f"XVII-{suffix}",
            source_document_id=source_id,
            normalized_data={"titulo": "Fotografia parlamentar", "faltas": []},
            confirm_private_only=True,
        ),
        actor=actor,
    )
    case_id = str(created["id"])
    assert created["current_state"] == "PENDING"
    assert created["publishable"] is False
    assert len(created["versions"]) == 1

    reviewing = await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A fonte arquivada e a normalização estão prontas para comparação.",
        source_confirmed=False,
        actor=actor,
    )
    assert reviewing["current_state"] == "IN_REVIEW"

    approved = await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="Comparei a fonte oficial, os hashes e todos os campos normalizados.",
        source_confirmed=True,
        actor=actor,
    )
    assert approved["current_state"] == "APPROVED"
    assert approved["publication_events"] == []

    corrected = await editorial.correct_case(
        case_id=case_id,
        payload=EditorialCorrectionRequest(
            expected_revision=3,
            rationale="Corrijo o título sem substituir nem apagar a versão aprovada anteriormente.",
            normalized_data={"titulo": "Fotografia parlamentar corrigida", "faltas": []},
        ),
        actor=actor,
    )
    assert corrected["current_state"] == "PENDING"
    assert corrected["revision"] == 4
    assert len(corrected["versions"]) == 2
    assert len(corrected["decisions"]) == 4
    assert corrected["publication_events"] == []

    async with repository.pool.acquire() as connection:
        with pytest.raises(Exception, match="append-only"):
            await connection.execute(
                "UPDATE editorial_decisions SET rationale = 'alterada' WHERE case_id = $1",
                case_id,
            )
        with pytest.raises(Exception, match="decisão imutável"):
            await connection.execute(
                """
                UPDATE editorial_cases
                SET current_state = 'PUBLISHED', revision = revision + 1, updated_at = NOW()
                WHERE id = $1
                """,
                case_id,
            )
