"""Integração V5.28 numa base descartável: observação -> caso privado PENDING."""

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    EditorialAction,
    PoliticianProfileEditorialProposalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialRepository
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.politician_profile_editorial import (
    PoliticianProfileEditorialRepository,
)
from app.repositories.politician_profile_publication import (
    PoliticianProfilePublicationReadinessRepository,
)

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
async def repository() -> OfficialIndexStagingRepository:
    repo = OfficialIndexStagingRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_exact_deputy_observation_creates_only_an_idempotent_private_case(
    repository: OfficialIndexStagingRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12].translate(str.maketrans("0123456789", "ghijklmnop"))
    now = datetime.now(UTC).replace(microsecond=0)
    source_url = HttpUrl(
        "https://app.parlamento.pt/webutils/docs/doc.txt"
        f"?fich=AtividadeDeputadoXVII_{suffix}_json.txt&Inline=true"
    )
    content = json.dumps({"fixture": suffix, "legislature": "XVII"}).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    stored = await repository.store_index(
        source_name=f"PARLIAMENT_DEPUTY_EDITORIAL_{suffix}",
        publisher="PARLIAMENT",
        title="Atividade oficial dos deputados — teste V5.28",
        raw_document=PrivateRawDocument(
            source_url=source_url,
            retrieved_at=now,
            content_sha256=content_sha256,
            mime_type="application/json",
            content=content,
        ),
        resources=[],
        code_version=f"politician-profile-editorial-integration-{suffix}",
    )
    source_document_id = str(stored["source_document_id"])
    snapshot_id = f"parliament_deputy_snapshot_{suffix}"
    observation_id = f"parliament_deputy_observation_{suffix}"
    official_deputy_id = f"dep-{suffix}"

    async with repository.pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """
            INSERT INTO parliament_deputy_snapshots
                (id, source_document_id, legislature, parser_version,
                 normalised_sha256, collected_at, deputy_count,
                 group_period_count, situation_period_count, office_period_count,
                 created_at)
            VALUES ($1, $2, 'XVII', 'parliament-historical-deputies-v1',
                    $3, $4, 1, 1, 1, 1, NOW())
            """,
            snapshot_id,
            source_document_id,
            "b" * 64,
            now.replace(tzinfo=None),
        )
        await connection.execute(
            """
            INSERT INTO parliament_deputy_observations
                (id, snapshot_id, source_id, candidate_source_id,
                 parliamentary_name, full_name, constituency_source_id,
                 constituency_label, parliamentary_groups,
                 mandate_situations, offices, created_at)
            VALUES ($1, $2, $3, $4, 'Pessoa Deputada',
                    'Pessoa Deputada de Integração', 'circle-porto', 'Porto',
                    $5::jsonb, $6::jsonb, $7::jsonb, NOW())
            """,
            observation_id,
            snapshot_id,
            official_deputy_id,
            f"candidate-{suffix}",
            json.dumps(
                [
                    {
                        "source_id": "group-1",
                        "short_name": "GP",
                        "starts_at": "2025-06-03T00:00:00Z",
                        "ends_at": None,
                    }
                ]
            ),
            json.dumps(
                [
                    {
                        "description": "Efetivo",
                        "starts_at": "2025-06-03T00:00:00Z",
                        "ends_at": None,
                    }
                ]
            ),
            json.dumps(
                [
                    {
                        "source_id": "office-1",
                        "title": "Cargo observado",
                        "starts_at": "2026-02-01T00:00:00Z",
                        "ends_at": "2026-01-01T00:00:00Z",
                    }
                ]
            ),
        )

        auth_user_id = uuid.uuid4()
        await _prepare_disposable_auth_user(connection, auth_user_id)
        staff_id = f"staff_{suffix}"
        alias = f"revisor-{suffix}"
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
        people_before = int(await connection.fetchval("SELECT COUNT(*) FROM people"))
        mandates_before = int(await connection.fetchval("SELECT COUNT(*) FROM mandates"))

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )
    adapter = PoliticianProfileEditorialRepository(repository.pool)
    catalogue = await adapter.list_candidates(
        legislature="XVII",
        query=official_deputy_id,
        limit=20,
        offset=0,
    )
    assert catalogue["total"] == 1
    candidate = catalogue["items"][0]
    assert candidate["official_deputy_id"] == official_deputy_id
    assert candidate["manifest_matches"] is True
    assert candidate["proposal_eligible"] is True
    assert candidate["mandate_inference_allowed"] is False
    assert any("não podem originar mandatos" in warning for warning in candidate["warnings"])
    beyond_last_page = await adapter.list_candidates(
        legislature="XVII",
        query=official_deputy_id,
        limit=20,
        offset=20,
    )
    assert beyond_last_page["items"] == []
    assert beyond_last_page["total"] == 1

    request = PoliticianProfileEditorialProposalRequest(
        observation_id=observation_id,
        confirm_private_only=True,
        confirm_exact_official_id_only=True,
        confirm_no_mandate_inference=True,
    )
    created = await adapter.create_proposal(payload=request, actor=actor)
    repeated = await adapter.create_proposal(payload=request, actor=actor)
    assert created["created"] is True
    assert repeated["created"] is False
    assert repeated["case"]["id"] == created["case"]["id"]
    assert created["case"]["kind"] == "POLITICIAN_PROFILE"
    assert created["case"]["subject_type"] == "PARLIAMENT_DEPUTY_OBSERVATION"
    assert created["case"]["current_state"] == "PENDING"
    assert created["person_created"] is False
    assert created["mandate_created"] is False

    case_id = str(created["case"]["id"])
    normalized = created["case"]["versions"][0]["normalized_data"]
    serialized = json.dumps(normalized, ensure_ascii=False)
    assert official_deputy_id not in serialized
    assert observation_id not in serialized
    assert snapshot_id not in serialized
    assert source_document_id not in serialized
    assert normalized["identity_rule"] == "EXACT_AR_DEP_ID_ONLY"
    assert normalized["mandate_inference_allowed"] is False

    readiness = PoliticianProfilePublicationReadinessRepository(repository.pool)
    pending_readiness = await readiness.inspect(snapshot_id=snapshot_id)
    assert pending_readiness["eligible"] is False
    assert pending_readiness["readiness_proof_sha256"] is None
    assert any(
        blocker["code"] == "EDITORIAL_STATE_NOT_APPROVED"
        for blocker in pending_readiness["blockers"]
    )
    assert pending_readiness["publication_performed"] is False
    assert pending_readiness["public_write_performed"] is False

    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A observação oficial será comparada sem inferir qualquer mandato.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="O DepId e a fonte arquivada foram confirmados para revisão do perfil.",
        source_confirmed=True,
        actor=actor,
    )

    approved_readiness = await readiness.inspect(snapshot_id=snapshot_id)
    assert approved_readiness["eligible"] is True
    assert approved_readiness["blockers"] == []
    assert approved_readiness["editorial_counts"]["APPROVED"] == 1
    assert approved_readiness["editorial_counts"]["MISSING"] == 0
    assert approved_readiness["identity_projection"] == {
        "exact_existing_people": 0,
        "new_people_required": 1,
        "existing_memberships": 0,
        "existing_party_links": 0,
        "legacy_review_decisions": 0,
        "legacy_positive_reviews": 0,
    }
    assert len(approved_readiness["readiness_proof_sha256"]) == 64
    assert approved_readiness["mandate_inference_allowed"] is False

    async with repository.pool.acquire() as connection:
        people_after = int(await connection.fetchval("SELECT COUNT(*) FROM people"))
        mandates_after = int(await connection.fetchval("SELECT COUNT(*) FROM mandates"))
        publication_events = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                case_id,
            )
        )
        reviews = int(
            await connection.fetchval(
                """
                SELECT COUNT(*) FROM data_publication_reviews
                WHERE entity_type = 'PERSON' AND entity_id = $1
                """,
                observation_id,
            )
        )
        decisions = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1",
                case_id,
            )
        )

    assert people_after == people_before
    assert mandates_after == mandates_before
    assert publication_events == 0
    assert reviews == 0
    assert decisions == 3
