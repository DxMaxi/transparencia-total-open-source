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
    ParliamentWithdrawalReason,
    PoliticianOfficeEditorialProposalRequest,
    PoliticianOfficePublicationRequest,
    PoliticianOfficeWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialConflictError, EditorialRepository
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.politician_office_editorial import (
    PoliticianOfficeEditorialRepository,
)
from app.repositories.politician_office_publication import (
    PoliticianOfficePublicationRepository,
)
from app.repositories.politician_office_withdrawal import (
    PoliticianOfficeWithdrawalRepository,
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
async def test_exact_official_office_creates_only_an_idempotent_private_case(
    repository: OfficialIndexStagingRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12].translate(str.maketrans("0123456789", "ghijklmnop"))
    now = datetime.now(UTC).replace(microsecond=0)
    legislature = f"V538-{suffix}"
    content = json.dumps({"fixture": suffix, "legislature": legislature}).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    stored = await repository.store_index(
        source_name=f"PARLIAMENT_OFFICE_EDITORIAL_{suffix}",
        publisher="PARLIAMENT",
        title="Atividade oficial dos deputados — teste V5.36",
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
        code_version=f"politician-office-editorial-integration-{suffix}",
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
        "source_id": f"office-{suffix}",
        "title": "Membro de comissão",
        "starts_at": "2025-06-10T00:00:00Z",
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
                    $4, $5, 1, 0, 0, 1, NOW())
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
                    '[]'::jsonb, '[]'::jsonb, $4::jsonb, NOW())
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
            VALUES ($1, $2, $3, 'ADMIN', TRUE, NOW(), NOW())
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
        role=StaffRole.ADMIN,
        assurance_level="aal2",
        mfa_required=False,
    )
    adapter = PoliticianOfficeEditorialRepository(repository.pool)
    catalogue = await adapter.list_candidates(
        legislature=legislature,
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

    request = PoliticianOfficeEditorialProposalRequest(
        observation_id=observation_id,
        source_period_sha256=str(candidate["source_period_sha256"]),
        confirm_private_only=True,
        confirm_exact_official_ids_only=True,
        confirm_observed_period_requires_human_review=True,
        confirm_no_mandate_or_party_inference=True,
    )
    created = await adapter.create_proposal(payload=request, actor=actor)
    repeated = await adapter.create_proposal(payload=request, actor=actor)
    assert created["created"] is True
    assert repeated["created"] is False
    assert repeated["case"]["id"] == created["case"]["id"]
    assert created["case"]["subject_type"] == "PARLIAMENT_OFFICE_PERIOD"
    assert created["case"]["current_state"] == "PENDING"
    assert created["office_created"] is False
    assert created["mandate_created"] is False

    normalized = created["case"]["versions"][0]["normalized_data"]
    serialized = json.dumps(normalized, ensure_ascii=False)
    for raw_identifier in (
        official_deputy_id,
        observation_id,
        snapshot_id,
        source_document_id,
        "circle-porto",
        f"office-{suffix}",
    ):
        assert raw_identifier not in serialized
    assert normalized["period_semantics"] == "HUMAN_REVIEW_REQUIRED"
    assert normalized["office_rule"] == "EXACT_AR_CAR_ID_ONLY"
    assert normalized["publication"]["office_creation_performed"] is False
    assert normalized["publication"]["mandate_creation_performed"] is False

    case_id = str(created["case"]["id"])
    editorial = EditorialRepository(repository.pool)
    approved = await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="O cargo será comparado com a fonte sem presumir mandato ou efeitos jurídicos.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="DepId, CarId, círculo, datas e documento oficial foram confirmados.",
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

    publisher = PoliticianOfficePublicationRepository(repository.pool)
    preview = await publisher.inspect(case_id=case_id)
    assert preview["eligible"] is True, preview["blockers"]
    assert preview["publication_proof_sha256"] is not None
    public_effect = preview["public_effect"]
    assert isinstance(public_effect, dict)
    assert public_effect["offices_to_create"] == 1
    assert public_effect["mandates_to_create"] == 0
    assert public_effect["party_links_to_create"] == 0
    payload = PoliticianOfficePublicationRequest(
        expected_case_id=case_id,
        expected_version_id=str(approved["current_version_id"]),
        expected_version_sha256=str(preview["version_sha256"]),
        expected_source_sha256=content_sha256,
        expected_period_sha256=str(candidate["source_period_sha256"]),
        expected_publication_proof_sha256=str(preview["publication_proof_sha256"]),
        rationale="A fonte, o DepId, o CarId, o círculo e as datas foram confirmados.",
        public_rationale="Cargo confirmado na ficha parlamentar oficial arquivada.",
        confirm_source_reviewed=True,
        confirm_human_office_interpretation=True,
        confirm_exact_official_ids_only=True,
        confirm_no_mandate_or_party_inference=True,
        confirm_append_only_publication=True,
        confirm_publication=True,
    )
    async with repository.pool.acquire() as connection:
        counts_before_failed_publication = {
            "offices": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM parliamentary_office_periods "
                    "WHERE source_observation_id = $1",
                    observation_id,
                )
            ),
            "reviews": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM data_publication_reviews "
                    "WHERE entity_type = 'PARLIAMENT_OFFICE'"
                )
            ),
            "audits": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM audit_events WHERE entity_type = 'PARLIAMENT_OFFICE'"
                )
            ),
            "events": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                    case_id,
                )
            ),
        }
    with pytest.raises(EditorialConflictError):
        await publisher.publish(
            case_id=case_id,
            payload=payload.model_copy(update={"expected_publication_proof_sha256": "0" * 64}),
            actor=actor,
        )
    async with repository.pool.acquire() as connection:
        counts_after_failed_publication = {
            "offices": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM parliamentary_office_periods "
                    "WHERE source_observation_id = $1",
                    observation_id,
                )
            ),
            "reviews": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM data_publication_reviews "
                    "WHERE entity_type = 'PARLIAMENT_OFFICE'"
                )
            ),
            "audits": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM audit_events WHERE entity_type = 'PARLIAMENT_OFFICE'"
                )
            ),
            "events": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                    case_id,
                )
            ),
        }
    assert counts_after_failed_publication == counts_before_failed_publication

    published = await publisher.publish(case_id=case_id, payload=payload, actor=actor)
    office_id = str(published["office_id"])
    assert published["state"] == "PUBLISHED"
    assert published["mandate_created"] is False
    assert published["party_link_created"] is False
    with pytest.raises(EditorialConflictError):
        await publisher.publish(case_id=case_id, payload=payload, actor=actor)

    async with repository.pool.acquire() as connection:
        office = await connection.fetchrow(
            """
            SELECT person_id, source_observation_id, source_period_ordinal,
                   official_office_id, title, legislature,
                   constituency_source_id, constituency, started_at, ended_at,
                   source_document_id, source_period_sha256
            FROM parliamentary_office_periods
            WHERE id = $1
            """,
            office_id,
        )
        assert office is not None
        assert office["person_id"] == person_id
        assert office["source_observation_id"] == observation_id
        assert office["source_period_ordinal"] == 1
        assert office["official_office_id"] == period["source_id"]
        assert office["title"] == period["title"]
        assert office["constituency_source_id"] == "circle-porto"
        assert office["source_document_id"] == source_document_id
        assert office["source_period_sha256"] == candidate["source_period_sha256"]
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews "
                "WHERE entity_type = 'PARLIAMENT_OFFICE' "
                "AND entity_id = $1 AND publishable = TRUE",
                office_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE entity_type = 'PARLIAMENT_OFFICE' "
                "AND entity_id = $1 AND action = 'PUBLISHED'",
                office_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events "
                "WHERE case_id = $1 AND target_type = 'PARLIAMENT_OFFICE' "
                "AND target_id = $2",
                case_id,
                office_id,
            )
            == 1
        )
        assert await connection.fetchval("SELECT COUNT(*) FROM mandates") == mandates_before
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE parliamentary_office_periods SET title = 'Alterado' WHERE id = $1",
                    office_id,
                )

    public_profile = await repository.get_public_politician(f"pessoa-{suffix}")
    assert public_profile is not None
    assert public_profile["mandates"] == []
    assert len(public_profile["parliamentary_offices"]) == 1
    assert public_profile["parliamentary_offices"][0]["official_office_id"] == period["source_id"]
    assert (
        public_profile["parliamentary_offices"][0]["source_period_sha256"]
        == candidate["source_period_sha256"]
    )

    withdrawer = PoliticianOfficeWithdrawalRepository(repository.pool)
    withdrawal_preview = await withdrawer.inspect(case_id=case_id)
    assert withdrawal_preview["eligible"] is True, withdrawal_preview["blockers"]
    assert withdrawal_preview["office_id"] == office_id
    withdrawal_effect = withdrawal_preview["public_effect"]
    assert isinstance(withdrawal_effect, dict)
    assert withdrawal_effect["kind"] == "PARLIAMENT_OFFICE_HIDDEN_HISTORY_PRESERVED"
    assert withdrawal_effect["exact_office_public_after_withdrawal"] is False
    assert withdrawal_effect["remaining_public_offices_for_person"] == 0
    assert withdrawal_effect["office_row_preserved"] is True

    withdrawal_payload = PoliticianOfficeWithdrawalRequest(
        expected_case_id=case_id,
        expected_revision=int(withdrawal_preview["case_revision"]),
        expected_version_id=str(withdrawal_preview["version_id"]),
        expected_version_sha256=str(withdrawal_preview["version_sha256"]),
        expected_office_id=office_id,
        expected_source_sha256=content_sha256,
        expected_period_sha256=str(candidate["source_period_sha256"]),
        expected_publication_proof_sha256=str(withdrawal_preview["publication_proof_sha256"]),
        expected_withdrawal_proof_sha256=str(withdrawal_preview["withdrawal_proof_sha256"]),
        expected_public_review_id=str(withdrawal_preview["public_review_id"]),
        expected_publication_audit_event_id=str(withdrawal_preview["publication_audit_event_id"]),
        expected_publication_event_id=str(withdrawal_preview["publication_event_id"]),
        expected_publication_event_sha256=str(withdrawal_preview["publication_event_sha256"]),
        expected_public_effect_sha256=str(withdrawal_preview["public_effect_sha256"]),
        rationale="A fonte oficial corrigiu o cargo anteriormente publicado.",
        public_rationale="Cargo retirado após correção documentada da fonte oficial.",
        reason_category=ParliamentWithdrawalReason.OFFICIAL_SOURCE_CORRECTION,
        confirm_source_and_publication_reviewed=True,
        confirm_exact_office=True,
        confirm_public_effect_reviewed=True,
        confirm_office_and_history_preserved=True,
        confirm_no_selective_identity_or_mandate_change=True,
        confirm_withdrawal=True,
    )
    async with repository.pool.acquire() as connection:
        counts_before_failed_withdrawal = {
            "reviews": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM data_publication_reviews "
                    "WHERE entity_type = 'PARLIAMENT_OFFICE' AND entity_id = $1",
                    office_id,
                )
            ),
            "audits": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM audit_events "
                    "WHERE entity_type = 'PARLIAMENT_OFFICE' AND entity_id = $1",
                    office_id,
                )
            ),
            "events": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                    case_id,
                )
            ),
            "decisions": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1",
                    case_id,
                )
            ),
        }
    with pytest.raises(EditorialConflictError):
        await withdrawer.withdraw(
            case_id=case_id,
            payload=withdrawal_payload.model_copy(
                update={"expected_public_effect_sha256": "0" * 64}
            ),
            actor=actor,
        )
    async with repository.pool.acquire() as connection:
        counts_after_failed_withdrawal = {
            "reviews": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM data_publication_reviews "
                    "WHERE entity_type = 'PARLIAMENT_OFFICE' AND entity_id = $1",
                    office_id,
                )
            ),
            "audits": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM audit_events "
                    "WHERE entity_type = 'PARLIAMENT_OFFICE' AND entity_id = $1",
                    office_id,
                )
            ),
            "events": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                    case_id,
                )
            ),
            "decisions": int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1",
                    case_id,
                )
            ),
        }
    assert counts_after_failed_withdrawal == counts_before_failed_withdrawal

    withdrawn = await withdrawer.withdraw(
        case_id=case_id,
        payload=withdrawal_payload,
        actor=actor,
    )
    assert withdrawn["state"] == "WITHDRAWN"
    assert withdrawn["office_id"] == office_id
    assert withdrawn["offices_deleted"] == 0
    assert withdrawn["people_deleted"] == 0
    assert withdrawn["memberships_deleted"] == 0
    with pytest.raises(EditorialConflictError):
        await withdrawer.withdraw(
            case_id=case_id,
            payload=withdrawal_payload,
            actor=actor,
        )

    async with repository.pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM parliamentary_office_periods WHERE id = $1",
                office_id,
            )
            == 1
        )
        reviews = await connection.fetch(
            "SELECT publishable FROM data_publication_reviews "
            "WHERE entity_type = 'PARLIAMENT_OFFICE' AND entity_id = $1 "
            "ORDER BY reviewed_at, id",
            office_id,
        )
        assert [row["publishable"] for row in reviews] == [True, False]
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE entity_type = 'PARLIAMENT_OFFICE' AND entity_id = $1 "
                "AND action IN ('PUBLISHED', 'WITHDRAWN')",
                office_id,
            )
            == 2
        )
        publication_actions = await connection.fetch(
            "SELECT action::text AS action FROM editorial_publication_events "
            "WHERE case_id = $1 ORDER BY created_at, id",
            case_id,
        )
        assert [row["action"] for row in publication_actions] == ["PUBLISH", "WITHDRAW"]
        assert await connection.fetchval("SELECT COUNT(*) FROM mandates") == mandates_before
        assert (
            await connection.fetchval("SELECT COUNT(*) FROM people WHERE id = $1", person_id) == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM parliamentary_membership_snapshots WHERE id = $1",
                membership_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM source_documents WHERE id = $1",
                source_document_id,
            )
            == 1
        )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM parliamentary_office_periods WHERE id = $1",
                    office_id,
                )

    public_profile_after_withdrawal = await repository.get_public_politician(f"pessoa-{suffix}")
    assert public_profile_after_withdrawal is not None
    assert public_profile_after_withdrawal["parliamentary_offices"] == []
    assert (
        public_profile_after_withdrawal["coverage"]["parliamentary_offices"]["state"]
        == "UNAVAILABLE"
    )
