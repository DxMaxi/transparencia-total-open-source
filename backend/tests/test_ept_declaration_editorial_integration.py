import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.models.editorial import (
    EditorialAction,
    StaffRole,
    StaffSession,
)
from app.models.ept_declaration import (
    EptPublicInterestEditorialProposalRequest,
    EptPublicInterestObservationInput,
)
from app.repositories.editorial import EditorialRepository
from app.repositories.ept_declaration_editorial import EptDeclarationEditorialRepository
from app.repositories.ept_declaration_staging import EptDeclarationStagingRepository
from app.repositories.postgres import PostgresRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


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


@pytest.fixture
async def repository() -> PostgresRepository:
    repo = PostgresRepository(
        Settings(
            environment="test",
            protected_identifier_pepper=SecretStr("p" * 32),
        )
    )
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_ept_observation_and_approval_create_no_identity_or_publication(
    repository: PostgresRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).replace(microsecond=0)
    declaration_id = f"DU-{suffix}"
    source_document_id = f"source_ept_{suffix}"
    source_url = f"https://entidadetransparencia.pt/registos/{declaration_id}"
    content = json.dumps({"fixture": suffix, "scope": "interest-register"}).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    source_record_name = "Pessoa Titular de Integração"
    raw_subject_identifier = "titular-integracao-ept-42"
    auth_user_id = uuid.uuid4()
    staff_id = f"staff_ept_{suffix}"
    alias = f"revisor-ept-{suffix}"

    async with repository.pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, official_identifier, url,
                 retrieved_at, published_at, content_sha256, mime_type,
                 raw_storage_key, parser_version, created_at)
            VALUES ($1, 'TRANSPARENCY_ENTITY', 'DECLARATION',
                    'Registo público de interesses — teste V5.46', $2, $3,
                    $4, NULL, $5, 'application/json', $6,
                    'ept-public-interest-observation-v1', NOW())
            """,
            source_document_id,
            declaration_id,
            source_url,
            now.replace(tzinfo=None),
            content_sha256,
            f"sha256/{content_sha256[:2]}/{content_sha256}",
        )
        await connection.execute(
            """
            INSERT INTO source_archive_attestations
                (id, source_document_id, storage_backend, storage_key,
                 content_sha256, byte_size, mime_type, retrieval_url,
                 retrieved_at, archived_at, archived_by,
                 attestation_sha256, created_at)
            VALUES ($1, $2, 'POSTGRES', $3, $4, $5, 'application/json',
                    $6, $7, $7, 'test:v5.46', $8, NOW())
            """,
            f"archive_ept_{suffix}",
            source_document_id,
            f"sha256/{content_sha256[:2]}/{content_sha256}",
            content_sha256,
            len(content),
            source_url,
            now.replace(tzinfo=None),
            hashlib.sha256(f"attestation:{suffix}".encode()).hexdigest(),
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
        declarations_before = int(
            await connection.fetchval("SELECT COUNT(*) FROM asset_declaration_metadata")
        )
        reviews_before = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews "
                "WHERE entity_type = 'ASSET_DECLARATION'"
            )
        )

    settings = repository.settings
    staged = await EptDeclarationStagingRepository(repository.pool, settings).stage_observation(
        payload=EptPublicInterestObservationInput(
            source_document_id=source_document_id,
            official_declaration_id=declaration_id,
            official_subject_identifier=SecretStr(raw_subject_identifier),
            public_subject_name=source_record_name,
            declared_at=now,
            period_label="2026",
            confirm_public_interest_register_only=True,
            confirm_no_income_or_asset_content=True,
            confirm_no_protected_identifiers_persisted=True,
            confirm_private_only=True,
        ),
        actor_alias=alias,
    )
    assert staged["created"] is True
    assert staged["publication_performed"] is False

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )
    adapter = EptDeclarationEditorialRepository(repository.pool)
    catalogue = await adapter.list_candidates(query=declaration_id, limit=20, offset=0)
    assert catalogue["total"] == 1
    candidate = catalogue["items"][0]
    assert candidate["proposal_eligible"] is True
    assert candidate["person_link_allowed"] is False
    assert raw_subject_identifier not in json.dumps(candidate, ensure_ascii=False)

    request = EptPublicInterestEditorialProposalRequest(
        observation_id=str(candidate["observation_id"]),
        source_record_sha256=str(candidate["source_record_sha256"]),
        confirm_private_only=True,
        confirm_public_interest_register_only=True,
        confirm_no_income_or_asset_content=True,
        confirm_no_name_matching=True,
        confirm_identity_unlinked=True,
        confirm_independent_legal_review_required=True,
    )
    created = await adapter.create_proposal(payload=request, actor=actor)
    repeated = await adapter.create_proposal(payload=request, actor=actor)
    assert created["created"] is True
    assert repeated["created"] is False
    assert repeated["case"]["id"] == created["case"]["id"]
    assert created["case"]["current_state"] == "PENDING"
    assert created["person_link_created"] is False
    assert created["declaration_created"] is False

    case_id = str(created["case"]["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A fonte individual será verificada sem associar o titular pelo nome.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="A prova EPT e o âmbito público mínimo foram confirmados para revisão futura.",
        source_confirmed=True,
        actor=actor,
    )

    async with repository.pool.acquire() as connection:
        observation = await connection.fetchrow(
            """
            SELECT official_subject_digest, legal_review_status, identity_link_status
            FROM ept_public_interest_observations
            WHERE id = $1
            """,
            candidate["observation_id"],
        )
        assert observation is not None
        assert str(observation["official_subject_digest"]) != raw_subject_identifier
        assert observation["legal_review_status"] == "REQUIRES_INDEPENDENT_LEGAL_REVIEW"
        assert observation["identity_link_status"] == "UNLINKED_PRIVATE"
        declarations_after = int(
            await connection.fetchval("SELECT COUNT(*) FROM asset_declaration_metadata")
        )
        reviews_after = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews "
                "WHERE entity_type = 'ASSET_DECLARATION'"
            )
        )
        publication_events = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                case_id,
            )
        )
        decisions = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1",
                case_id,
            )
        )
        serialized_private = await connection.fetchval(
            """
            SELECT concat_ws(' ', observation::text, audit::text, version::text)
            FROM ept_public_interest_observations observation
            JOIN audit_events audit
              ON audit.entity_id = observation.id
             AND audit.entity_type = 'EPT_PUBLIC_INTEREST_OBSERVATION'
            JOIN editorial_cases editorial_case
              ON editorial_case.subject_id = observation.id
             AND editorial_case.subject_type = 'EPT_PUBLIC_INTEREST_OBSERVATION'
            JOIN editorial_versions version ON version.case_id = editorial_case.id
            WHERE observation.id = $1
            LIMIT 1
            """,
            candidate["observation_id"],
        )
        rls_enabled = await connection.fetchval(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE oid = 'public.ept_public_interest_observations'::regclass"
        )
        browser_roles_have_access = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_roles
                WHERE rolname IN ('anon', 'authenticated')
                  AND has_table_privilege(
                      rolname,
                      'public.ept_public_interest_observations',
                      'SELECT,INSERT,UPDATE,DELETE'
                  )
            )
            """
        )
        assert rls_enabled is True
        assert browser_roles_have_access is False

        with pytest.raises(asyncpg.PostgresError, match="UPDATE e DELETE são proibidos"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE ept_public_interest_observations SET period_label = 'alterado' "
                    "WHERE id = $1",
                    candidate["observation_id"],
                )

    assert raw_subject_identifier not in str(serialized_private)
    assert declarations_after == declarations_before
    assert reviews_after == reviews_before
    assert publication_events == 0
    assert decisions == 3
