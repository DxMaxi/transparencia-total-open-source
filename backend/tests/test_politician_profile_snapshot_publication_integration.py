"""V5.30–V5.31: publicação e retirada integrais numa base PostgreSQL descartável."""

import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    EditorialAction,
    PoliticianProfileEditorialProposalRequest,
    PoliticianProfileSnapshotPublicationRequest,
    PoliticianProfileSnapshotWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.politician_profile_editorial import (
    PoliticianProfileEditorialRepository,
)
from app.repositories.politician_profile_snapshot_publication import (
    PoliticianProfileSnapshotPublicationRepository,
)
from app.repositories.politician_profile_snapshot_withdrawal import (
    PoliticianProfileSnapshotWithdrawalRepository,
)
from app.repositories.public_politicians import PublicPoliticianRepository

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
async def test_complete_snapshot_publication_and_withdrawal_are_atomic_exact_and_public(
    repository: OfficialIndexStagingRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12].translate(str.maketrans("0123456789", "ghijklmnop"))
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=2)
    legislature = f"V530-{suffix}"
    parliamentary_name = f"Pessoa V530 {suffix}"
    official_deputy_id = f"dep-v530-{suffix}"
    source_url = HttpUrl(
        "https://app.parlamento.pt/webutils/docs/doc.txt"
        f"?fich=AtividadeDeputadoV530_{suffix}_json.txt&Inline=true"
    )
    content = json.dumps({"fixture": suffix, "legislature": legislature}).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    stored = await repository.store_index(
        source_name=f"PARLIAMENT_DEPUTY_PUBLICATION_{suffix}",
        publisher="PARLIAMENT",
        title="Atividade oficial dos deputados — teste V5.30",
        raw_document=PrivateRawDocument(
            source_url=source_url,
            retrieved_at=now,
            content_sha256=content_sha256,
            mime_type="application/json",
            content=content,
        ),
        resources=[],
        code_version=f"politician-profile-publication-integration-{suffix}",
    )
    source_document_id = str(stored["source_document_id"])
    snapshot_id = f"parliament_deputy_snapshot_v530_{suffix}"
    observation_id = f"parliament_deputy_observation_v530_{suffix}"

    async with repository.pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """
            INSERT INTO parliament_deputy_snapshots
                (id, source_document_id, legislature, parser_version,
                 normalised_sha256, collected_at, deputy_count,
                 group_period_count, situation_period_count, office_period_count,
                 created_at)
            VALUES ($1, $2, $3, 'parliament-historical-deputies-v1',
                    $4, $5, 1, 1, 1, 0, NOW())
            """,
            snapshot_id,
            source_document_id,
            legislature,
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
            VALUES ($1, $2, $3, NULL, $4, $5, 'circle-test', 'Círculo de teste',
                    $6::jsonb, $7::jsonb, '[]'::jsonb, NOW())
            """,
            observation_id,
            snapshot_id,
            official_deputy_id,
            parliamentary_name,
            f"{parliamentary_name} Nome Completo",
            json.dumps(
                [
                    {
                        "source_id": "group-test",
                        "short_name": "GP Teste",
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
        )
        auth_user_id = uuid.uuid4()
        await _prepare_disposable_auth_user(connection, auth_user_id)
        staff_id = f"staff_v530_{suffix}"
        alias = f"admin-v530-{suffix}"
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

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.ADMIN,
        assurance_level="aal2",
        mfa_required=False,
    )
    profile_editorial = PoliticianProfileEditorialRepository(repository.pool)
    created = await profile_editorial.create_proposal(
        payload=PoliticianProfileEditorialProposalRequest(
            observation_id=observation_id,
            confirm_private_only=True,
            confirm_exact_official_id_only=True,
            confirm_no_mandate_inference=True,
        ),
        actor=actor,
    )
    case_id = str(created["case"]["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A identidade e a observação serão comparadas com a fonte arquivada.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="DepId, fotografia completa e fonte arquivada confirmados pelo revisor.",
        source_confirmed=True,
        actor=actor,
    )

    publication = PoliticianProfileSnapshotPublicationRepository(repository.pool)
    preview = await publication.inspect(snapshot_id=snapshot_id)
    assert preview["eligible"] is True
    assert preview["public_effect"] == {
        "people_to_create": 1,
        "people_to_reuse_by_exact_depid": 0,
        "memberships_to_create": 1,
        "memberships_to_reuse": 0,
        "person_reviews_to_append": 1,
        "cases_to_publish": 1,
        "mandates_to_create": 0,
        "party_links_to_create": 0,
    }
    assert len(preview["readiness_proof_sha256"]) == 64
    assert len(preview["publication_proof_sha256"]) == 64

    request_data = {
        "expected_snapshot_id": snapshot_id,
        "expected_source_sha256": content_sha256,
        "expected_snapshot_sha256": "b" * 64,
        "expected_readiness_proof_sha256": preview["readiness_proof_sha256"],
        "expected_publication_proof_sha256": preview["publication_proof_sha256"],
        "expected_deputy_count": 1,
        "rationale": "A fotografia integral e todas as versões aprovadas foram confirmadas.",
        "public_rationale": "Identidades parlamentares revistas com fonte e prova completas.",
        "confirm_source_reviewed": True,
        "confirm_complete_snapshot": True,
        "confirm_exact_official_id_only": True,
        "confirm_no_mandate_inference": True,
        "confirm_no_party_inference": True,
        "confirm_publication": True,
    }
    wrong_request = PoliticianProfileSnapshotPublicationRequest.model_validate(
        {**request_data, "expected_publication_proof_sha256": "e" * 64}
    )
    async with repository.pool.acquire() as connection:
        counts_before_failed_attempt = await connection.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1) AS decisions,
                (SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1) AS events,
                (
                    SELECT COUNT(*) FROM data_publication_reviews
                    WHERE source_document_id = $2
                      AND entity_type IN ('PERSON', 'PARLIAMENT_DEPUTY_SNAPSHOT')
                ) AS reviews,
                (
                    SELECT COUNT(*) FROM audit_events
                    WHERE entity_type = 'PARLIAMENT_DEPUTY_SNAPSHOT' AND entity_id = $3
                ) AS snapshot_audits
            """,
            case_id,
            source_document_id,
            snapshot_id,
        )
        assert counts_before_failed_attempt is not None
    with pytest.raises(EditorialConflictError):
        await publication.publish(
            snapshot_id=snapshot_id,
            payload=wrong_request,
            actor=actor,
        )
    async with repository.pool.acquire() as connection:
        assert not await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM people WHERE source_id = $1)",
            official_deputy_id,
        )
        assert (
            int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                    case_id,
                )
            )
            == 0
        )
        counts_after_failed_attempt = await connection.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1) AS decisions,
                (SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1) AS events,
                (
                    SELECT COUNT(*) FROM data_publication_reviews
                    WHERE source_document_id = $2
                      AND entity_type IN ('PERSON', 'PARLIAMENT_DEPUTY_SNAPSHOT')
                ) AS reviews,
                (
                    SELECT COUNT(*) FROM audit_events
                    WHERE entity_type = 'PARLIAMENT_DEPUTY_SNAPSHOT' AND entity_id = $3
                ) AS snapshot_audits
            """,
            case_id,
            source_document_id,
            snapshot_id,
        )
        assert counts_after_failed_attempt == counts_before_failed_attempt

    result = await publication.publish(
        snapshot_id=snapshot_id,
        payload=PoliticianProfileSnapshotPublicationRequest.model_validate(request_data),
        actor=actor,
    )
    assert result["state"] == "PUBLISHED"
    assert result["people_created"] == 1
    assert result["memberships_created"] == 1
    assert result["person_reviews_created"] == 1
    assert result["editorial_decisions_created"] == 1
    assert result["publication_events_created"] == 1
    assert result["mandates_created"] == 0
    assert result["party_links_created"] == 0

    async with repository.pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT person.id, person.slug, person.role::text AS role,
                   membership.party_id, membership.constituency,
                   editorial_case.current_state::text AS case_state,
                   editorial_case.revision
            FROM people AS person
            JOIN parliamentary_membership_snapshots AS membership
              ON membership.person_id = person.id
            JOIN editorial_cases AS editorial_case ON editorial_case.id = $2
            WHERE person.source_id = $1
              AND membership.source_document_id = $3
            """,
            official_deputy_id,
            case_id,
            source_document_id,
        )
        assert row is not None
        assert row["role"] == "DEPUTY"
        assert official_deputy_id not in str(row["slug"])
        assert row["party_id"] is None
        assert row["constituency"] == "Círculo de teste"
        assert row["case_state"] == "PUBLISHED"
        assert row["revision"] == 4
        assert int(await connection.fetchval("SELECT COUNT(*) FROM mandates")) == mandates_before
        assert (
            int(
                await connection.fetchval(
                    """
                SELECT COUNT(*) FROM data_publication_reviews
                WHERE entity_type = 'PERSON' AND entity_id = $1
                  AND source_document_id = $2 AND publishable = TRUE
                """,
                    row["id"],
                    source_document_id,
                )
            )
            == 1
        )
        assert (
            int(
                await connection.fetchval(
                    """
                SELECT COUNT(*) FROM data_publication_reviews
                WHERE entity_type = 'PARLIAMENT_DEPUTY_SNAPSHOT'
                  AND entity_id = $1 AND publishable = TRUE
                """,
                    snapshot_id,
                )
            )
            == 1
        )
        event = await connection.fetchrow(
            """
            SELECT target_type, target_id, event_sha256
            FROM editorial_publication_events WHERE case_id = $1
            """,
            case_id,
        )
        assert event is not None
        assert event["target_type"] == "PERSON"
        assert event["target_id"] == row["id"]
        assert re.fullmatch(r"[0-9a-f]{64}", str(event["event_sha256"]))

    public = await PublicPoliticianRepository(repository.pool).explore(
        query=parliamentary_name,
        party_short=None,
        limit=10,
        cursor=None,
    )
    assert public["total"] == 1
    assert public["items"][0]["name"] == parliamentary_name
    assert public["items"][0]["party"] == "Sem filiação indicada"
    assert public["items"][0]["profile_source"]["content_sha256"] == content_sha256

    with pytest.raises(EditorialConflictError):
        await publication.publish(
            snapshot_id=snapshot_id,
            payload=PoliticianProfileSnapshotPublicationRequest.model_validate(request_data),
            actor=actor,
        )

    withdrawal = PoliticianProfileSnapshotWithdrawalRepository(repository.pool)
    withdrawal_preview = await withdrawal.inspect(snapshot_id=snapshot_id)
    assert withdrawal_preview["eligible"] is True
    assert withdrawal_preview["published_profile_count"] == 1
    assert withdrawal_preview["public_effect"]["kind"] == "DATA_UNAVAILABLE"
    assert len(str(withdrawal_preview["withdrawal_proof_sha256"])) == 64
    assert len(str(withdrawal_preview["public_effect_sha256"])) == 64

    withdrawal_data = {
        "expected_snapshot_id": snapshot_id,
        "expected_source_sha256": content_sha256,
        "expected_snapshot_sha256": "b" * 64,
        "expected_publication_proof_sha256": withdrawal_preview["publication_proof_sha256"],
        "expected_withdrawal_proof_sha256": withdrawal_preview["withdrawal_proof_sha256"],
        "expected_public_effect_sha256": withdrawal_preview["public_effect_sha256"],
        "expected_deputy_count": 1,
        "rationale": "A fonte publicada diverge de forma reproduzível da fotografia revista.",
        "public_rationale": "Fotografia retirada por divergência factual documentada.",
        "reason_category": "SOURCE_DIVERGENCE",
        "confirm_complete_snapshot": True,
        "confirm_no_selective_removal": True,
        "confirm_public_effect_reviewed": True,
        "confirm_people_and_history_preserved": True,
        "confirm_withdrawal": True,
    }
    async with repository.pool.acquire() as connection:
        counts_before_failed_withdrawal = await connection.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1) AS decisions,
                (SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1) AS events,
                (
                    SELECT COUNT(*) FROM data_publication_reviews
                    WHERE source_document_id = $2
                      AND entity_type IN ('PERSON', 'PARLIAMENT_DEPUTY_SNAPSHOT')
                ) AS reviews,
                (
                    SELECT COUNT(*) FROM audit_events
                    WHERE entity_type IN ('PERSON', 'PARLIAMENT_DEPUTY_SNAPSHOT')
                      AND entity_id IN ($3, $4)
                ) AS audits
            """,
            case_id,
            source_document_id,
            str(row["id"]),
            snapshot_id,
        )
        assert counts_before_failed_withdrawal is not None
    wrong_withdrawal = PoliticianProfileSnapshotWithdrawalRequest.model_validate(
        {**withdrawal_data, "expected_public_effect_sha256": "e" * 64}
    )
    with pytest.raises(EditorialConflictError):
        await withdrawal.withdraw(
            snapshot_id=snapshot_id,
            payload=wrong_withdrawal,
            actor=actor,
        )
    async with repository.pool.acquire() as connection:
        counts_after_failed_withdrawal = await connection.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM editorial_decisions WHERE case_id = $1) AS decisions,
                (SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1) AS events,
                (
                    SELECT COUNT(*) FROM data_publication_reviews
                    WHERE source_document_id = $2
                      AND entity_type IN ('PERSON', 'PARLIAMENT_DEPUTY_SNAPSHOT')
                ) AS reviews,
                (
                    SELECT COUNT(*) FROM audit_events
                    WHERE entity_type IN ('PERSON', 'PARLIAMENT_DEPUTY_SNAPSHOT')
                      AND entity_id IN ($3, $4)
                ) AS audits
            """,
            case_id,
            source_document_id,
            str(row["id"]),
            snapshot_id,
        )
        assert counts_after_failed_withdrawal == counts_before_failed_withdrawal

    withdrawn = await withdrawal.withdraw(
        snapshot_id=snapshot_id,
        payload=PoliticianProfileSnapshotWithdrawalRequest.model_validate(withdrawal_data),
        actor=actor,
    )
    assert withdrawn["state"] == "WITHDRAWN"
    assert withdrawn["person_reviews_created"] == 1
    assert withdrawn["person_audits_created"] == 1
    assert withdrawn["editorial_decisions_created"] == 1
    assert withdrawn["withdrawal_events_created"] == 1
    assert withdrawn["people_deleted"] == 0
    assert withdrawn["memberships_deleted"] == 0
    assert withdrawn["versions_deleted"] == 0

    async with repository.pool.acquire() as connection:
        preserved = await connection.fetchrow(
            """
            SELECT person.id,
                   editorial_case.current_state::text AS case_state,
                   editorial_case.revision,
                   (
                       SELECT review.publishable
                       FROM data_publication_reviews AS review
                       WHERE review.entity_type = 'PERSON'
                         AND review.entity_id = person.id
                         AND review.source_document_id = $3
                       ORDER BY review.reviewed_at DESC, review.id DESC
                       LIMIT 1
                   ) AS person_publishable,
                   (
                       SELECT review.publishable
                       FROM data_publication_reviews AS review
                       WHERE review.entity_type = 'PARLIAMENT_DEPUTY_SNAPSHOT'
                         AND review.entity_id = $4
                         AND review.source_document_id = $3
                       ORDER BY review.reviewed_at DESC, review.id DESC
                       LIMIT 1
                   ) AS snapshot_publishable
            FROM people AS person
            JOIN parliamentary_membership_snapshots AS membership
              ON membership.person_id = person.id
             AND membership.source_document_id = $3
            JOIN editorial_cases AS editorial_case ON editorial_case.id = $2
            WHERE person.source_id = $1
            """,
            official_deputy_id,
            case_id,
            source_document_id,
            snapshot_id,
        )
        assert preserved is not None
        assert preserved["case_state"] == "WITHDRAWN"
        assert preserved["revision"] == 5
        assert preserved["person_publishable"] is False
        assert preserved["snapshot_publishable"] is False
        assert int(await connection.fetchval("SELECT COUNT(*) FROM mandates")) == mandates_before
        actions = await connection.fetch(
            """
            SELECT action::text, event_sha256
            FROM editorial_publication_events
            WHERE case_id = $1
            ORDER BY created_at, id
            """,
            case_id,
        )
        assert [str(item["action"]) for item in actions] == ["PUBLISH", "WITHDRAW"]
        assert all(re.fullmatch(r"[0-9a-f]{64}", str(item["event_sha256"])) for item in actions)

    no_longer_public = await PublicPoliticianRepository(repository.pool).explore(
        query=parliamentary_name,
        party_short=None,
        limit=10,
        cursor=None,
    )
    assert no_longer_public["total"] == 0
    assert await repository.pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM people WHERE source_id = $1)", official_deputy_id
    )

    with pytest.raises((EditorialConflictError, EditorialSourceError)):
        await withdrawal.withdraw(
            snapshot_id=snapshot_id,
            payload=PoliticianProfileSnapshotWithdrawalRequest.model_validate(withdrawal_data),
            actor=actor,
        )

    retired_preview = await withdrawal.inspect(snapshot_id=snapshot_id)
    assert retired_preview["eligible"] is False
    assert retired_preview["withdrawal_proof_sha256"] is None

    next_retrieved_at = now + timedelta(minutes=1)
    next_parliamentary_name = f"{parliamentary_name} Atualizada"
    next_content = json.dumps(
        {
            "fixture": f"{suffix}-next",
            "legislature": legislature,
            "official_deputy_id": official_deputy_id,
        }
    ).encode()
    next_content_sha256 = hashlib.sha256(next_content).hexdigest()
    next_stored = await repository.store_index(
        source_name=f"PARLIAMENT_DEPUTY_REPUBLICATION_{suffix}",
        publisher="PARLIAMENT",
        title="Atividade oficial dos deputados — teste V5.32",
        raw_document=PrivateRawDocument(
            source_url=HttpUrl(
                "https://app.parlamento.pt/webutils/docs/doc.txt"
                f"?fich=AtividadeDeputadoV532_{suffix}_json.txt&Inline=true"
            ),
            retrieved_at=next_retrieved_at,
            content_sha256=next_content_sha256,
            mime_type="application/json",
            content=next_content,
        ),
        resources=[],
        code_version=f"politician-profile-republication-integration-{suffix}",
    )
    next_source_document_id = str(next_stored["source_document_id"])
    next_snapshot_id = f"parliament_deputy_snapshot_v532_{suffix}"
    next_observation_id = f"parliament_deputy_observation_v532_{suffix}"

    async with repository.pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """
            INSERT INTO parliament_deputy_snapshots
                (id, source_document_id, legislature, parser_version,
                 normalised_sha256, collected_at, deputy_count,
                 group_period_count, situation_period_count, office_period_count,
                 created_at)
            VALUES ($1, $2, $3, 'parliament-historical-deputies-v1',
                    $4, $5, 1, 1, 1, 0, NOW())
            """,
            next_snapshot_id,
            next_source_document_id,
            legislature,
            "c" * 64,
            next_retrieved_at.replace(tzinfo=None),
        )
        await connection.execute(
            """
            INSERT INTO parliament_deputy_observations
                (id, snapshot_id, source_id, candidate_source_id,
                 parliamentary_name, full_name, constituency_source_id,
                 constituency_label, parliamentary_groups,
                 mandate_situations, offices, created_at)
            VALUES ($1, $2, $3, NULL, $4, $5, 'circle-test', 'Círculo de teste',
                    $6::jsonb, $7::jsonb, '[]'::jsonb, NOW())
            """,
            next_observation_id,
            next_snapshot_id,
            official_deputy_id,
            next_parliamentary_name,
            f"{next_parliamentary_name} Nome Completo",
            json.dumps(
                [
                    {
                        "source_id": "group-test",
                        "short_name": "GP Teste",
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
        )

    next_created = await profile_editorial.create_proposal(
        payload=PoliticianProfileEditorialProposalRequest(
            observation_id=next_observation_id,
            confirm_private_only=True,
            confirm_exact_official_id_only=True,
            confirm_no_mandate_inference=True,
        ),
        actor=actor,
    )
    next_case_id = str(next_created["case"]["id"])
    await editorial.transition(
        case_id=next_case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A nova fotografia será comparada de forma independente com a nova fonte.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=next_case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale=(
            "Novo arquivo, DepId e versão exata confirmados sem reativar a fotografia antiga."
        ),
        source_confirmed=True,
        actor=actor,
    )

    next_preview = await publication.inspect(snapshot_id=next_snapshot_id)
    assert next_preview["eligible"] is True
    assert next_preview["identity_projection"]["legacy_review_decisions"] == 0
    assert next_preview["public_effect"] == {
        "people_to_create": 0,
        "people_to_reuse_by_exact_depid": 1,
        "memberships_to_create": 1,
        "memberships_to_reuse": 0,
        "person_reviews_to_append": 1,
        "cases_to_publish": 1,
        "mandates_to_create": 0,
        "party_links_to_create": 0,
    }
    next_publication_data = {
        "expected_snapshot_id": next_snapshot_id,
        "expected_source_sha256": next_content_sha256,
        "expected_snapshot_sha256": "c" * 64,
        "expected_readiness_proof_sha256": next_preview["readiness_proof_sha256"],
        "expected_publication_proof_sha256": next_preview["publication_proof_sha256"],
        "expected_deputy_count": 1,
        "rationale": "A nova fotografia integral e a nova prova oficial foram confirmadas.",
        "public_rationale": "Fotografia parlamentar posterior revista com prova completa.",
        "confirm_source_reviewed": True,
        "confirm_complete_snapshot": True,
        "confirm_exact_official_id_only": True,
        "confirm_no_mandate_inference": True,
        "confirm_no_party_inference": True,
        "confirm_publication": True,
    }
    republished = await publication.publish(
        snapshot_id=next_snapshot_id,
        payload=PoliticianProfileSnapshotPublicationRequest.model_validate(next_publication_data),
        actor=actor,
    )
    assert republished["state"] == "PUBLISHED"
    assert republished["people_created"] == 0
    assert republished["memberships_created"] == 1
    assert republished["mandates_created"] == 0
    assert republished["party_links_created"] == 0

    public_after_republication = await PublicPoliticianRepository(repository.pool).explore(
        query=next_parliamentary_name,
        party_short=None,
        limit=10,
        cursor=None,
    )
    assert public_after_republication["total"] == 1
    assert public_after_republication["items"][0]["name"] == next_parliamentary_name
    assert (
        public_after_republication["items"][0]["profile_source"]["content_sha256"]
        == next_content_sha256
    )

    async with repository.pool.acquire() as connection:
        lifecycle = await connection.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM people WHERE source_id = $1) AS people,
                (
                    SELECT COUNT(*)
                    FROM parliamentary_membership_snapshots AS membership
                    JOIN people AS person ON person.id = membership.person_id
                    WHERE person.source_id = $1
                      AND membership.source_document_id IN ($2, $3)
                ) AS memberships,
                (
                    SELECT current_state::text FROM editorial_cases WHERE id = $4
                ) AS old_state,
                (
                    SELECT current_state::text FROM editorial_cases WHERE id = $5
                ) AS new_state,
                (
                    SELECT COUNT(*) FROM editorial_versions WHERE case_id IN ($4, $5)
                ) AS versions
            """,
            official_deputy_id,
            source_document_id,
            next_source_document_id,
            case_id,
            next_case_id,
        )
        assert lifecycle is not None
        assert int(lifecycle["people"]) == 1
        assert int(lifecycle["memberships"]) == 2
        assert lifecycle["old_state"] == "WITHDRAWN"
        assert lifecycle["new_state"] == "PUBLISHED"
        assert int(lifecycle["versions"]) == 2
        old_version_id = await connection.fetchval(
            "SELECT current_version_id FROM editorial_cases WHERE id = $1", case_id
        )
        next_version_id = await connection.fetchval(
            "SELECT current_version_id FROM editorial_cases WHERE id = $1", next_case_id
        )
        assert old_version_id != next_version_id
        assert int(await connection.fetchval("SELECT COUNT(*) FROM mandates")) == mandates_before
        old_actions = await connection.fetch(
            """
            SELECT action::text FROM editorial_publication_events
            WHERE case_id = $1 ORDER BY created_at, id
            """,
            case_id,
        )
        next_actions = await connection.fetch(
            """
            SELECT action::text FROM editorial_publication_events
            WHERE case_id = $1 ORDER BY created_at, id
            """,
            next_case_id,
        )
        assert [str(item["action"]) for item in old_actions] == ["PUBLISH", "WITHDRAW"]
        assert [str(item["action"]) for item in next_actions] == ["PUBLISH"]

    with pytest.raises((EditorialConflictError, EditorialSourceError)):
        await publication.publish(
            snapshot_id=snapshot_id,
            payload=PoliticianProfileSnapshotPublicationRequest.model_validate(request_data),
            actor=actor,
        )
    old_snapshot_after_republication = await withdrawal.inspect(snapshot_id=snapshot_id)
    assert old_snapshot_after_republication["eligible"] is False
    assert old_snapshot_after_republication["withdrawal_proof_sha256"] is None
