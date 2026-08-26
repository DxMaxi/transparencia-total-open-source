import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    EditorialAction,
    PoliticianMandateEditorialProposalRequest,
    PoliticianMandatePublicationRequest,
    PoliticianMandateWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialConflictError, EditorialRepository
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.politician_mandate_editorial import (
    PoliticianMandateEditorialRepository,
)
from app.repositories.politician_mandate_publication import (
    PoliticianMandatePublicationRepository,
)
from app.repositories.politician_mandate_withdrawal import (
    PoliticianMandateWithdrawalRepository,
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
async def repository() -> AsyncIterator[OfficialIndexStagingRepository]:
    repo = OfficialIndexStagingRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_admin_publishes_one_exact_append_only_mandate_or_nothing(
    repository: OfficialIndexStagingRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12].translate(str.maketrans("0123456789", "ghijklmnop"))
    legislature = f"TEST-{suffix}"
    now = datetime.now(UTC).replace(microsecond=0)
    content = json.dumps({"fixture": suffix, "legislature": legislature}).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    stored = await repository.store_index(
        source_name=f"PARLIAMENT_MANDATE_PUBLICATION_{suffix}",
        publisher="PARLIAMENT",
        title="Atividade oficial dos deputados — publicação V5.34",
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
        code_version=f"politician-mandate-publication-integration-{suffix}",
    )
    source_document_id = str(stored["source_document_id"])
    snapshot_id = f"parliament_deputy_snapshot_{suffix}"
    observation_id = f"parliament_deputy_observation_{suffix}"
    official_deputy_id = f"dep-{suffix}"
    person_id = f"person_{suffix}"
    membership_id = f"membership_{suffix}"
    person_review_id = f"review_{suffix}"
    staff_id = f"staff_{suffix}"
    auth_user_id = uuid.uuid4()
    alias = f"admin-{suffix}"
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
            VALUES ($1, $2, $3, 'parliament-historical-deputies-v1',
                    $4, $5, 1, 0, 1, 0, NOW())
            """,
            snapshot_id,
            source_document_id,
            legislature,
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
                    $3, 'Porto', $4, $5)
            """,
            membership_id,
            person_id,
            legislature,
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
            person_review_id,
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
            VALUES ($1, $2, $3, 'ADMIN', TRUE, NOW(), NOW())
            """,
            staff_id,
            auth_user_id,
            alias,
        )

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.ADMIN,
        assurance_level="aal2",
        mfa_required=False,
    )
    candidate_repository = PoliticianMandateEditorialRepository(repository.pool)
    catalogue = await candidate_repository.list_candidates(
        legislature=legislature,
        query=official_deputy_id,
        limit=20,
        offset=0,
    )
    candidate_items = catalogue["items"]
    assert isinstance(candidate_items, list)
    candidate = candidate_items[0]
    assert isinstance(candidate, dict)
    proposal = await candidate_repository.create_proposal(
        payload=PoliticianMandateEditorialProposalRequest(
            observation_id=observation_id,
            source_period_sha256=str(candidate["source_period_sha256"]),
            confirm_private_only=True,
            confirm_exact_official_id_only=True,
            confirm_period_semantics_require_human_review=True,
            confirm_no_party_inference=True,
        ),
        actor=actor,
    )
    proposal_case = proposal["case"]
    assert isinstance(proposal_case, dict)
    case_id = str(proposal_case["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="O intervalo será comparado sem presumir outros cargos ou filiações.",
        source_confirmed=False,
        actor=actor,
    )
    approved = await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="O DepId, o período e o círculo foram confirmados na fonte arquivada.",
        source_confirmed=True,
        actor=actor,
    )

    publisher = PoliticianMandatePublicationRepository(repository.pool)
    preview = await publisher.inspect(case_id=case_id)
    assert preview["eligible"] is True
    assert preview["publication_proof_sha256"] is not None
    public_effect = preview["public_effect"]
    assert isinstance(public_effect, dict)
    assert public_effect["people_to_create"] == 0
    assert public_effect["party_links_to_create"] == 0
    payload = PoliticianMandatePublicationRequest(
        expected_case_id=case_id,
        expected_version_id=str(approved["current_version_id"]),
        expected_version_sha256=str(preview["version_sha256"]),
        expected_source_sha256=content_sha256,
        expected_period_sha256=str(candidate["source_period_sha256"]),
        expected_publication_proof_sha256=str(preview["publication_proof_sha256"]),
        rationale="A fonte, o DepId, o círculo e as datas foram novamente confirmados.",
        public_rationale="Mandato confirmado no documento parlamentar oficial arquivado.",
        confirm_source_reviewed=True,
        confirm_human_period_interpretation=True,
        confirm_exact_official_id_only=True,
        confirm_no_party_inference=True,
        confirm_append_only_publication=True,
        confirm_publication=True,
    )
    with pytest.raises(EditorialConflictError):
        await publisher.publish(
            case_id=case_id,
            payload=payload.model_copy(update={"expected_publication_proof_sha256": "0" * 64}),
            actor=actor,
        )
    async with repository.pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM mandates WHERE source_observation_id = $1",
                observation_id,
            )
            == 0
        )

    published = await publisher.publish(case_id=case_id, payload=payload, actor=actor)
    mandate_id = str(published["mandate_id"])
    assert published["state"] == "PUBLISHED"
    assert published["party_link_created"] is False
    with pytest.raises(EditorialConflictError):
        await publisher.publish(case_id=case_id, payload=payload, actor=actor)

    async with repository.pool.acquire() as connection:
        mandate = await connection.fetchrow(
            """
            SELECT person_id, party_id, legislature, office_title, constituency,
                   started_at, ended_at, source_document_id, source_observation_id,
                   source_period_ordinal, source_period_sha256
            FROM mandates
            WHERE id = $1
            """,
            mandate_id,
        )
        assert mandate is not None
        assert mandate["person_id"] == person_id
        assert mandate["party_id"] is None
        assert mandate["source_document_id"] == source_document_id
        assert mandate["source_observation_id"] == observation_id
        assert mandate["source_period_ordinal"] == 1
        assert mandate["source_period_sha256"] == candidate["source_period_sha256"]
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews "
                "WHERE entity_type = 'MANDATE' AND entity_id = $1 AND publishable = TRUE",
                mandate_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE entity_type = 'MANDATE' AND entity_id = $1 AND action = 'PUBLISHED'",
                mandate_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events "
                "WHERE case_id = $1 AND target_type = 'MANDATE' AND target_id = $2",
                case_id,
                mandate_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1",
                case_id,
            )
            == 4
        )

    async with repository.pool.acquire() as connection:
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE mandates SET constituency = 'Lisboa' WHERE id = $1",
                    mandate_id,
                )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE data_publication_reviews SET publishable = FALSE WHERE id = $1",
                    str(published["mandate_review_id"]),
                )

    public_profile = await repository.get_public_politician(f"pessoa-{suffix}")
    assert public_profile is not None
    assert len(public_profile["mandates"]) == 1
    assert (
        public_profile["mandates"][0]["source_period_sha256"] == candidate["source_period_sha256"]
    )

    withdrawer = PoliticianMandateWithdrawalRepository(repository.pool)
    withdrawal_preview = await withdrawer.inspect(case_id=case_id)
    assert withdrawal_preview["eligible"] is True, withdrawal_preview["blockers"]
    assert withdrawal_preview["withdrawal_proof_sha256"] is not None
    withdrawal_effect = withdrawal_preview["public_effect"]
    assert isinstance(withdrawal_effect, dict)
    assert withdrawal_effect["exact_mandate_public_after_withdrawal"] is False
    assert withdrawal_effect["mandate_row_preserved"] is True
    withdrawal_payload = PoliticianMandateWithdrawalRequest(
        expected_case_id=case_id,
        expected_revision=int(withdrawal_preview["case_revision"]),
        expected_version_id=str(withdrawal_preview["version_id"]),
        expected_version_sha256=str(withdrawal_preview["version_sha256"]),
        expected_mandate_id=mandate_id,
        expected_source_sha256=content_sha256,
        expected_period_sha256=str(candidate["source_period_sha256"]),
        expected_publication_proof_sha256=str(withdrawal_preview["publication_proof_sha256"]),
        expected_withdrawal_proof_sha256=str(withdrawal_preview["withdrawal_proof_sha256"]),
        expected_public_review_id=str(withdrawal_preview["public_review_id"]),
        expected_publication_audit_event_id=str(withdrawal_preview["publication_audit_event_id"]),
        expected_publication_event_id=str(withdrawal_preview["publication_event_id"]),
        expected_publication_event_sha256=str(withdrawal_preview["publication_event_sha256"]),
        expected_public_effect_sha256=str(withdrawal_preview["public_effect_sha256"]),
        rationale="A fonte oficial corrigiu o intervalo anteriormente publicado.",
        public_rationale="Mandato retirado após correção documentada da fonte oficial.",
        reason_category="OFFICIAL_SOURCE_CORRECTION",
        confirm_source_and_publication_reviewed=True,
        confirm_exact_mandate=True,
        confirm_public_effect_reviewed=True,
        confirm_mandate_and_history_preserved=True,
        confirm_no_selective_identity_change=True,
        confirm_withdrawal=True,
    )
    with pytest.raises(EditorialConflictError):
        await withdrawer.withdraw(
            case_id=case_id,
            payload=withdrawal_payload.model_copy(
                update={"expected_public_effect_sha256": "0" * 64}
            ),
            actor=actor,
        )
    async with repository.pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews "
                "WHERE entity_type = 'MANDATE' AND entity_id = $1",
                mandate_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT current_state::text FROM editorial_cases WHERE id = $1",
                case_id,
            )
            == "PUBLISHED"
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events "
                "WHERE case_id = $1 AND action = 'WITHDRAW'",
                case_id,
            )
            == 0
        )

    withdrawn = await withdrawer.withdraw(
        case_id=case_id,
        payload=withdrawal_payload,
        actor=actor,
    )
    assert withdrawn["state"] == "WITHDRAWN"
    assert withdrawn["mandates_deleted"] == 0
    assert withdrawn["people_deleted"] == 0
    assert withdrawn["memberships_deleted"] == 0
    with pytest.raises(EditorialConflictError):
        await withdrawer.withdraw(
            case_id=case_id,
            payload=withdrawal_payload,
            actor=actor,
        )

    async with repository.pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM mandates WHERE id = $1)",
            mandate_id,
        )
        reviews = await connection.fetch(
            "SELECT publishable FROM data_publication_reviews "
            "WHERE entity_type = 'MANDATE' AND entity_id = $1 "
            "ORDER BY reviewed_at, id",
            mandate_id,
        )
        assert [row["publishable"] for row in reviews] == [True, False]
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE entity_type = 'MANDATE' AND entity_id = $1 AND action = 'WITHDRAWN'",
                mandate_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events "
                "WHERE case_id = $1 AND target_type = 'MANDATE' AND target_id = $2",
                case_id,
                mandate_id,
            )
            == 2
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1",
                case_id,
            )
            == 5
        )

    public_profile_after_withdrawal = await repository.get_public_politician(f"pessoa-{suffix}")
    assert public_profile_after_withdrawal is not None
    assert public_profile_after_withdrawal["mandates"] == []
