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
    PoliticianMandateEditorialProposalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialRepository
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.politician_mandate_editorial import (
    PoliticianMandateEditorialRepository,
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
async def test_exact_official_period_creates_only_an_idempotent_private_mandate_case(
    repository: OfficialIndexStagingRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12].translate(str.maketrans("0123456789", "ghijklmnop"))
    now = datetime.now(UTC).replace(microsecond=0)
    content = json.dumps({"fixture": suffix, "legislature": "XVII"}).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    stored = await repository.store_index(
        source_name=f"PARLIAMENT_MANDATE_EDITORIAL_{suffix}",
        publisher="PARLIAMENT",
        title="Atividade oficial dos deputados — teste V5.33",
        raw_document=PrivateRawDocument(
            source_url=HttpUrl(
                "https://app.parlamento.pt/webutils/docs/doc.txt"
                f"?fich=AtividadeDeputadoXVII_{suffix}_json.txt&Inline=true"
            ),
            retrieved_at=now,
            content_sha256=content_sha256,
            mime_type="application/json",
            content=content,
        ),
        resources=[],
        code_version=f"politician-mandate-editorial-integration-{suffix}",
    )
    source_document_id = str(stored["source_document_id"])
    snapshot_id = f"parliament_deputy_snapshot_{suffix}"
    observation_id = f"parliament_deputy_observation_{suffix}"
    official_deputy_id = f"dep-{suffix}"
    person_id = f"person_{suffix}"
    membership_id = f"membership_{suffix}"
    review_id = f"review_{suffix}"
    staff_id = f"staff_{suffix}"
    auth_user_id = uuid.uuid4()
    alias = f"revisor-{suffix}"
    period = {
        "description": "Efetivo",
        "starts_at": "2025-06-03T00:00:00Z",
        "ends_at": None,
    }

    async with repository.pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """
            INSERT INTO parliament_deputy_snapshots
                (id, source_document_id, legislature, parser_version,
                 normalised_sha256, collected_at, deputy_count,
                 group_period_count, situation_period_count, office_period_count,
                 created_at)
            VALUES ($1, $2, 'XVII', 'parliament-historical-deputies-v1',
                    $3, $4, 1, 0, 1, 0, NOW())
            """,
            snapshot_id,
            source_document_id,
            "a" * 64,
            now.replace(tzinfo=None),
        )
        await connection.execute(
            """
            INSERT INTO parliament_deputy_observations
                (id, snapshot_id, source_id, candidate_source_id,
                 parliamentary_name, full_name, constituency_source_id,
                 constituency_label, parliamentary_groups,
                 mandate_situations, offices, created_at)
            VALUES ($1, $2, $3, NULL, 'Pessoa Deputada',
                    'Pessoa Deputada de Integração', 'circle-porto', 'Porto',
                    '[]'::jsonb, $4::jsonb, '[]'::jsonb, NOW())
            """,
            observation_id,
            snapshot_id,
            official_deputy_id,
            json.dumps([period]),
        )
        await connection.execute(
            """
            INSERT INTO people
                (id, source_id, full_name, parliamentary_name, slug, role,
                 photo_url, official_profile_url, active, created_at, updated_at)
            VALUES ($1, $2, 'Pessoa Deputada de Integração', 'Pessoa Deputada',
                    $3, 'DEPUTY', NULL, NULL, TRUE, NOW(), NOW())
            """,
            person_id,
            official_deputy_id,
            f"pessoa-{suffix}",
        )
        await connection.execute(
            """
            INSERT INTO parliamentary_membership_snapshots
                (id, person_id, parliamentary_name, full_name, party_id,
                 legislature, constituency, observed_at, source_document_id)
            VALUES ($1, $2, 'Pessoa Deputada', 'Pessoa Deputada de Integração', NULL,
                    'XVII', 'Porto', $3, $4)
            """,
            membership_id,
            person_id,
            now.replace(tzinfo=None),
            source_document_id,
        )
        await connection.execute(
            """
            INSERT INTO data_publication_reviews
                (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                 necessity_assessment, proportionality_test, retention_until,
                 publishable, source_document_id, reviewed_by, reviewed_at)
            VALUES ($1, 'PERSON', $2, 'Diretório parlamentar factual',
                    'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                    'Identidade parlamentar necessária para ligar prova oficial.',
                    'Publicação limitada ao perfil oficial e respetiva fonte.', NULL,
                    TRUE, $3, $4, $5)
            """,
            review_id,
            person_id,
            source_document_id,
            alias,
            now.replace(tzinfo=None),
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
        mandates_before = int(await connection.fetchval("SELECT COUNT(*) FROM mandates"))
        reviews_before = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews WHERE entity_type = 'MANDATE'"
            )
        )

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )
    adapter = PoliticianMandateEditorialRepository(repository.pool)
    catalogue = await adapter.list_candidates(
        legislature="XVII",
        query=official_deputy_id,
        limit=20,
        offset=0,
    )
    assert catalogue["total"] == 1
    candidate = catalogue["items"][0]
    assert candidate["proposal_eligible"] is True
    assert candidate["identity_publication_ready"] is True
    assert candidate["blocked_reasons"] == []
    assert candidate["public_projection_allowed"] is False

    request = PoliticianMandateEditorialProposalRequest(
        observation_id=observation_id,
        source_period_sha256=str(candidate["source_period_sha256"]),
        confirm_private_only=True,
        confirm_exact_official_id_only=True,
        confirm_period_semantics_require_human_review=True,
        confirm_no_party_inference=True,
    )
    created = await adapter.create_proposal(payload=request, actor=actor)
    repeated = await adapter.create_proposal(payload=request, actor=actor)
    assert created["created"] is True
    assert repeated["created"] is False
    assert repeated["case"]["id"] == created["case"]["id"]
    assert created["case"]["subject_type"] == "PARLIAMENT_MANDATE_SITUATION"
    assert created["case"]["current_state"] == "PENDING"
    assert created["mandate_created"] is False

    normalized = created["case"]["versions"][0]["normalized_data"]
    serialized = json.dumps(normalized, ensure_ascii=False)
    for raw_identifier in (
        official_deputy_id,
        observation_id,
        snapshot_id,
        source_document_id,
        "circle-porto",
    ):
        assert raw_identifier not in serialized
    assert normalized["period_semantics"] == "HUMAN_REVIEW_REQUIRED"
    assert normalized["publication"]["mandate_creation_performed"] is False

    case_id = str(created["case"]["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="O intervalo será comparado com a fonte sem presumir efeitos jurídicos.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="DepId, círculo, datas e documento oficial foram confirmados pelo revisor.",
        source_confirmed=True,
        actor=actor,
    )

    async with repository.pool.acquire() as connection:
        mandates_after = int(await connection.fetchval("SELECT COUNT(*) FROM mandates"))
        reviews_after = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews WHERE entity_type = 'MANDATE'"
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

    assert mandates_after == mandates_before
    assert reviews_after == reviews_before
    assert publication_events == 0
    assert decisions == 3
