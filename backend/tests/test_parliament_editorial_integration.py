"""Integração real: snapshot -> proposta V5.2 -> publicação V5.3 por âmbito."""

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.api import (
    OfficialSource,
    SourcePublisher,
    VoteActorType,
    VoteChoice,
    VoteEvent,
    VoteRecord,
)
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    EditorialAction,
    EditorialCorrectionRequest,
    ParliamentEditorialProposalRequest,
    ParliamentEditorialPublicationRequest,
    ParliamentEditorialWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.models.parliamentary import (
    ParliamentActivityDataset,
    ParliamentaryInitiativeRecord,
    ParliamentarySessionRecord,
)
from app.repositories.editorial import EditorialConflictError, EditorialRepository
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.parliament_activity import ParliamentActivityRepository
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.parliament_editorial_publication import (
    ParliamentEditorialPublicationRepository,
)
from app.repositories.public_parliament import PublicParliamentRepository

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


def _dataset(
    *,
    legislature: str,
    marker: str,
    collected_at: datetime,
    expanded: bool,
) -> tuple[ParliamentActivityDataset, PrivateRawDocument]:
    content = json.dumps(
        {"legislature": legislature, "marker": marker, "expanded": expanded},
        sort_keys=True,
    ).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    source_url = HttpUrl(f"https://www.parlamento.pt/testes/editorial-{marker}.json")
    raw = PrivateRawDocument(
        source_url=source_url,
        retrieved_at=collected_at,
        content_sha256=content_sha256,
        mime_type="application/json",
        content=content,
    )
    source = OfficialSource(
        publisher=SourcePublisher.PARLIAMENT,
        label="Assembleia da República — teste do adaptador editorial",
        url=source_url,
        retrieved_at=collected_at,
        content_sha256=content_sha256,
    )
    sessions = [
        ParliamentarySessionRecord(
            source_id="session-stable",
            legislature=legislature,
            session_number="1",
            title="Reunião corrigida" if expanded else "Reunião inicial",
            starts_at=collected_at,
            source=source,
        )
    ]
    if expanded:
        sessions.append(
            ParliamentarySessionRecord(
                source_id="session-added",
                legislature=legislature,
                session_number="2",
                title="Reunião acrescentada",
                starts_at=collected_at,
                source=source,
            )
        )
    initiatives = [
        ParliamentaryInitiativeRecord(
            source_id="initiative-stable",
            legislature=legislature,
            number=f"1/{legislature}",
            initiative_type="Projeto de teste",
            title="Iniciativa estável",
            official_url=source_url,
            source=source,
        )
    ]
    votes = [
        VoteEvent(
            source_id="vote-stable",
            title="Votação estável com posição corrigida",
            voted_at=collected_at,
            result="Aprovado",
            initiative_number=f"1/{legislature}",
            is_nominal=False,
            records=[
                VoteRecord(
                    actor_label="Grupo sem identificador inequívoco",
                    actor_type=VoteActorType.UNKNOWN,
                    choice=VoteChoice.AGAINST if expanded else VoteChoice.FAVOR,
                )
            ],
            source=source,
        )
    ]
    if expanded:
        votes.append(
            VoteEvent(
                source_id="vote-added",
                title="Votação acrescentada",
                voted_at=collected_at,
                result=None,
                is_nominal=False,
                records=[
                    VoteRecord(
                        actor_label="Posição sem ator identificado",
                        actor_type=VoteActorType.UNKNOWN,
                        choice=VoteChoice.UNKNOWN,
                    )
                ],
                source=source,
            )
        )
    return (
        ParliamentActivityDataset(
            legislature=legislature,
            dataset_url=source_url,
            document_sha256=content_sha256,
            parser_version="parliament-editorial-integration-v1",
            collected_at=collected_at,
            raw_document=raw,
            sessions=sessions,
            initiatives=initiatives,
            votes=votes,
        ),
        raw,
    )


@pytest.mark.asyncio
async def test_parliament_editorial_cycle_preserves_scope_from_proposal_to_publication(
    repository: OfficialIndexStagingRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12]
    legislature = f"TEST-{suffix}"
    first_at = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=2)
    second_at = first_at + timedelta(minutes=1)
    first_dataset, first_raw = _dataset(
        legislature=legislature,
        marker=f"{suffix}-first",
        collected_at=first_at,
        expanded=False,
    )
    second_dataset, second_raw = _dataset(
        legislature=legislature,
        marker=f"{suffix}-second",
        collected_at=second_at,
        expanded=True,
    )
    activity = ParliamentActivityRepository(repository.pool)
    first_receipt = await repository.archive_raw_document(raw_document=first_raw)
    await activity.persist(
        first_dataset,
        archive_receipt=first_receipt,
        archived_by="parliament-editorial-integration",
    )
    second_receipt = await repository.archive_raw_document(raw_document=second_raw)
    second = await activity.persist(
        second_dataset,
        archive_receipt=second_receipt,
        archived_by="parliament-editorial-integration",
    )

    auth_user_id = uuid.uuid4()
    staff_id = f"staff_{suffix}"
    alias = f"revisor-{suffix}"
    async with repository.pool.acquire() as connection:
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
    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )

    adapter = ParliamentEditorialRepository(repository.pool)
    candidates = await adapter.list_snapshot_candidates(legislature=legislature, limit=10)
    assert len(candidates) == 2
    latest = candidates[0]
    assert latest["snapshot_id"] == second.snapshot_id
    assert latest["manifest_matches"] is True
    assert latest["manifest_counts"] == {
        "sessions": 2,
        "initiatives": 1,
        "votes": 2,
        "vote_records": 2,
    }
    assert latest["coverage"]["unknown_actor_records"] == 2
    assert latest["coverage"]["unknown_choice_records"] == 1
    assert latest["coverage"]["linked_person_records"] == 0
    assert latest["differences"] == {
        "status": "COMPARED_BY_EXACT_SOURCE_ID",
        "sessions": {"added": 1, "removed": 0, "changed": 1, "unchanged": 0},
        "initiatives": {"added": 0, "removed": 0, "changed": 1, "unchanged": 0},
        "votes": {"added": 1, "removed": 0, "changed": 1, "unchanged": 0},
    }

    activity_request = ParliamentEditorialProposalRequest(
        snapshot_id=second.snapshot_id,
        scope="activity",
        confirm_private_only=True,
        confirm_no_individual_inference=True,
    )
    created_activity = await adapter.create_proposal(payload=activity_request, actor=actor)
    repeated_activity = await adapter.create_proposal(payload=activity_request, actor=actor)
    assert created_activity["created"] is True
    assert repeated_activity["created"] is False
    assert repeated_activity["case"]["id"] == created_activity["case"]["id"]
    assert created_activity["case"]["origin"] == "INGESTION"
    assert created_activity["case"]["current_state"] == "PENDING"
    assert created_activity["case"]["versions"][0]["origin"] == "INGESTION"
    assert created_activity["case"]["versions"][0]["created_by_alias"] == ("parliament-ingestion")
    assert created_activity["case"]["decisions"][0]["actor_alias"] == alias

    created_votes = await adapter.create_proposal(
        payload=ParliamentEditorialProposalRequest(
            snapshot_id=second.snapshot_id,
            scope="votes",
            confirm_private_only=True,
            confirm_no_individual_inference=True,
        ),
        actor=actor,
    )
    assert created_votes["created"] is True
    assert created_votes["case"]["id"] != created_activity["case"]["id"]

    async with repository.pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT c.kind::text, c.created_by_id, c.origin::text,
                   v.normalized_json, v.origin::text AS version_origin,
                   count(d.id) AS decision_count
            FROM editorial_cases AS c
            JOIN editorial_versions AS v ON v.id = c.current_version_id
            JOIN editorial_decisions AS d ON d.case_id = c.id
            WHERE c.subject_id = $1
            GROUP BY c.id, v.id
            ORDER BY c.kind
            """,
            second.snapshot_id,
        )
        review_count = await connection.fetchval(
            """
            SELECT count(*)
            FROM data_publication_reviews
            WHERE entity_id = $1
              AND entity_type IN (
                  'PARLIAMENT_ACTIVITY_SNAPSHOT', 'PARLIAMENT_VOTES_SNAPSHOT'
              )
            """,
            second.snapshot_id,
        )
        publication_event_count = await connection.fetchval(
            """
            SELECT count(*)
            FROM editorial_publication_events
            WHERE case_id = ANY($1::text[])
            """,
            [str(created_activity["case"]["id"]), str(created_votes["case"]["id"])],
        )

    assert len(rows) == 2
    assert all(row["created_by_id"] is None for row in rows)
    assert all(row["origin"] == "INGESTION" for row in rows)
    assert all(row["version_origin"] == "INGESTION" for row in rows)
    assert all(int(row["decision_count"]) == 1 for row in rows)
    normalized = {
        str(row["kind"]): (
            json.loads(row["normalized_json"])
            if isinstance(row["normalized_json"], str)
            else row["normalized_json"]
        )
        for row in rows
    }
    assert "votes" not in normalized["PARLIAMENT_ACTIVITY"]["differences_from_previous_snapshot"]
    assert set(normalized["PARLIAMENT_VOTE"]["differences_from_previous_snapshot"]) == {
        "status",
        "votes",
    }
    expected_snapshot_reference = hashlib.sha256(second.snapshot_id.encode("utf-8")).hexdigest()
    for proposal in normalized.values():
        assert proposal["snapshot"]["reference_sha256"] == expected_snapshot_reference
        assert second.snapshot_id not in json.dumps(proposal, ensure_ascii=False)
        assert second.source_document_id not in json.dumps(proposal, ensure_ascii=False)
    assert "Grupo sem identificador inequívoco" not in json.dumps(
        normalized,
        ensure_ascii=False,
    )
    assert int(review_count) == 0
    assert int(publication_event_count) == 0

    public = PublicParliamentRepository(repository.pool)
    assert await public.list_sessions(legislature=legislature, limit=10, offset=0) == []
    assert await public.list_votes(legislature=legislature, limit=10, offset=0) == []

    editorial = EditorialRepository(repository.pool)
    activity_case_id = str(created_activity["case"]["id"])
    await editorial.transition(
        case_id=activity_case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A prova oficial de atividade será comparada antes da aprovação.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=activity_case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="Fonte, manifesto e âmbito de atividade confirmados pelo revisor.",
        source_confirmed=True,
        actor=actor,
    )

    admin_id = f"staff_admin_{suffix}"
    admin_alias = f"admin-{suffix}"
    admin_auth_user_id = uuid.uuid4()
    async with repository.pool.acquire() as connection:
        await _prepare_disposable_auth_user(connection, admin_auth_user_id)
        await connection.execute(
            """
            INSERT INTO staff_profiles
                (id, auth_user_id, public_alias, role, active, created_at, updated_at)
            VALUES ($1, $2, $3, 'ADMIN', TRUE, NOW(), NOW())
            """,
            admin_id,
            admin_auth_user_id,
            admin_alias,
        )
    admin = StaffSession(
        staff_id=admin_id,
        auth_user_id=admin_auth_user_id,
        public_alias=admin_alias,
        role=StaffRole.ADMIN,
        assurance_level="aal2",
        mfa_required=False,
    )
    publisher = ParliamentEditorialPublicationRepository(repository.pool)
    activity_preview = await publisher.inspect(case_id=activity_case_id)
    assert activity_preview["scope"] == "activity"
    assert activity_preview["eligible"] is True
    activity_source = activity_preview["source"]
    activity_version = activity_preview["editorial_version"]
    assert isinstance(activity_source, dict)
    assert isinstance(activity_version, dict)
    activity_publication = ParliamentEditorialPublicationRequest(
        expected_revision=int(activity_preview["revision"]),
        rationale="Administrador confirmou novamente a fonte e apenas o âmbito de atividade.",
        confirmed_scope="activity",
        expected_snapshot_id=str(activity_preview["target_id"]),
        expected_source_sha256=str(activity_source["content_sha256"]),
        expected_snapshot_sha256=str(activity_preview["snapshot_sha256"]),
        expected_editorial_sha256=str(activity_version["normalized_sha256"]),
        expected_publication_proof_sha256=str(activity_preview["publication_proof_sha256"]),
        confirm_source_reviewed=True,
        confirm_no_individual_inference=True,
        confirm_publication=True,
    )
    forged_admin = admin.model_copy(update={"public_alias": f"forjado-{suffix}"})
    with pytest.raises(Exception, match="identidade staff ativa e coerente"):
        await publisher.publish(
            case_id=activity_case_id,
            payload=activity_publication,
            actor=forged_admin,
        )
    async with repository.pool.acquire() as connection:
        rolled_back = await connection.fetchrow(
            """
            SELECT
                (SELECT count(*) FROM data_publication_reviews
                 WHERE entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                   AND entity_id = $1) AS reviews,
                (SELECT count(*) FROM audit_events
                 WHERE entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                   AND entity_id = $1
                   AND action = 'PUBLISHED') AS audits,
                (SELECT current_state::text FROM editorial_cases
                 WHERE id = $2) AS case_state
            """,
            second.snapshot_id,
            activity_case_id,
        )
    assert rolled_back is not None
    assert int(rolled_back["reviews"]) == 0
    assert int(rolled_back["audits"]) == 0
    assert rolled_back["case_state"] == "APPROVED"

    published_activity = await publisher.publish(
        case_id=activity_case_id,
        payload=activity_publication,
        actor=admin,
    )
    assert published_activity["state"] == "PUBLISHED"
    assert len(await public.list_sessions(legislature=legislature, limit=10, offset=0)) == 2
    assert len(await public.list_initiatives(legislature=legislature, limit=10, offset=0)) == 1
    assert await public.list_votes(legislature=legislature, limit=10, offset=0) == []

    votes_case_id = str(created_votes["case"]["id"])
    await editorial.transition(
        case_id=votes_case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A prova oficial das votações será comparada antes da aprovação.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=votes_case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="Fonte, manifesto e ausência de inferência individual confirmados.",
        source_confirmed=True,
        actor=actor,
    )
    votes_preview = await publisher.inspect(case_id=votes_case_id)
    assert votes_preview["scope"] == "votes"
    assert votes_preview["eligible"] is True
    votes_source = votes_preview["source"]
    votes_version = votes_preview["editorial_version"]
    assert isinstance(votes_source, dict)
    assert isinstance(votes_version, dict)
    votes_publication = ParliamentEditorialPublicationRequest(
        expected_revision=int(votes_preview["revision"]),
        rationale="Administrador confirmou novamente a fonte e apenas o âmbito de votações.",
        confirmed_scope="votes",
        expected_snapshot_id=str(votes_preview["target_id"]),
        expected_source_sha256=str(votes_source["content_sha256"]),
        expected_snapshot_sha256=str(votes_preview["snapshot_sha256"]),
        expected_editorial_sha256=str(votes_version["normalized_sha256"]),
        expected_publication_proof_sha256=str(votes_preview["publication_proof_sha256"]),
        confirm_source_reviewed=True,
        confirm_no_individual_inference=True,
        confirm_publication=True,
    )
    published_votes = await publisher.publish(
        case_id=votes_case_id,
        payload=votes_publication,
        actor=admin,
    )
    assert published_votes["state"] == "PUBLISHED"
    assert len(await public.list_votes(legislature=legislature, limit=10, offset=0)) == 2
    explored_votes = await public.explore(
        kind="votes",
        legislature=legislature,
        query="estável",
        date_from=None,
        date_to=None,
        initiative_type="Projeto de teste",
        initiative_status=None,
        vote_result="Aprovado",
        is_nominal=False,
        party_source_id=None,
        choice="AGAINST",
        limit=1,
        offset=0,
    )
    assert explored_votes["total"] == 1
    assert len(explored_votes["votes"]) == 1
    assert explored_votes["votes"][0]["source_id"] == "vote-stable"
    assert explored_votes["votes"][0]["initiative_title"] == "Iniciativa estável"
    assert explored_votes["facets"]["topics_available"] is False
    assert legislature in explored_votes["facets"]["legislatures"]

    with pytest.raises(EditorialConflictError, match="alterado por outra decisão"):
        await publisher.publish(
            case_id=votes_case_id,
            payload=votes_publication,
            actor=admin,
        )

    async with repository.pool.acquire() as connection:
        publication_rows = await connection.fetch(
            """
            SELECT c.current_state::text, c.revision, d.action::text,
                   event.target_type, event.target_id,
                   review.publishable, audit.after_json
            FROM editorial_cases AS c
            JOIN editorial_decisions AS d
              ON d.case_id = c.id AND d.action = 'PUBLISH'::"EditorialDecisionAction"
            JOIN editorial_publication_events AS event
              ON event.case_id = c.id AND event.action = 'PUBLISH'::"EditorialPublicationAction"
            JOIN data_publication_reviews AS review
              ON review.id = ANY($1::text[])
             AND review.entity_type = event.target_type
             AND review.entity_id = event.target_id
            JOIN audit_events AS audit
              ON audit.id = ANY($2::text[])
             AND audit.entity_type = event.target_type
             AND audit.entity_id = event.target_id
            WHERE c.id = ANY($3::text[])
            ORDER BY event.target_type
            """,
            [
                str(published_activity["publication_review_id"]),
                str(published_votes["publication_review_id"]),
            ],
            [
                str(published_activity["audit_event_id"]),
                str(published_votes["audit_event_id"]),
            ],
            [activity_case_id, votes_case_id],
        )
    assert len(publication_rows) == 2
    assert all(row["current_state"] == "PUBLISHED" for row in publication_rows)
    assert all(int(row["revision"]) == 4 for row in publication_rows)
    assert all(row["action"] == "PUBLISH" for row in publication_rows)
    assert all(row["publishable"] is True for row in publication_rows)
    for row in publication_rows:
        after_json = (
            json.loads(row["after_json"])
            if isinstance(row["after_json"], str)
            else row["after_json"]
        )
        assert after_json["editorial_link"]["case_id"] in {
            activity_case_id,
            votes_case_id,
        }

    withdrawal_preview = await publisher.inspect_withdrawal(case_id=activity_case_id)
    assert withdrawal_preview["eligible"] is True
    assert withdrawal_preview["public_effect"]["kind"] == "DATA_UNAVAILABLE"
    withdrawn_activity = await publisher.withdraw(
        case_id=activity_case_id,
        payload=ParliamentEditorialWithdrawalRequest(
            expected_revision=int(withdrawal_preview["revision"]),
            rationale=(
                "Ensaio isolado confirma uma divergência reproduzível e exercita a retirada "
                "append-only sem apagar a fotografia original."
            ),
            public_rationale=(
                "Fotografia de atividade retirada no ensaio por divergência reproduzível."
            ),
            reason_category="SOURCE_DIVERGENCE",
            confirmed_scope="activity",
            expected_snapshot_id=str(withdrawal_preview["target_id"]),
            expected_source_sha256=str(withdrawal_preview["source_sha256"]),
            expected_snapshot_sha256=str(withdrawal_preview["snapshot_sha256"]),
            expected_editorial_sha256=str(withdrawal_preview["editorial_sha256"]),
            expected_publication_proof_sha256=str(withdrawal_preview["publication_proof_sha256"]),
            expected_public_review_id=str(withdrawal_preview["public_review_id"]),
            expected_publication_audit_event_id=str(
                withdrawal_preview["publication_audit_event_id"]
            ),
            expected_publication_event_id=str(withdrawal_preview["publication_event_id"]),
            expected_publication_event_sha256=str(withdrawal_preview["publication_event_sha256"]),
            expected_public_effect_sha256=str(withdrawal_preview["public_effect_sha256"]),
            confirm_no_selective_removal=True,
            confirm_public_effect_reviewed=True,
            confirm_withdrawal=True,
        ),
        actor=admin,
    )
    assert withdrawn_activity["state"] == "WITHDRAWN"
    assert await public.list_sessions(legislature=legislature, limit=10, offset=0) == []
    assert await public.list_initiatives(legislature=legislature, limit=10, offset=0) == []
    assert len(await public.list_votes(legislature=legislature, limit=10, offset=0)) == 2

    public_history = await public.list_publication_history(legislature=legislature, limit=10)
    assert [row["action"] for row in public_history[:3]] == [
        "WITHDRAWN",
        "PUBLISHED",
        "PUBLISHED",
    ]
    assert public_history[0]["reason_category"] == "SOURCE_DIVERGENCE"
    assert public_history[0]["public_effect"]["kind"] == "DATA_UNAVAILABLE"
    assert "case_id" not in public_history[0]

    withdrawn_case = await editorial.get_case(activity_case_id)
    corrected_data = json.loads(json.dumps(withdrawn_case["versions"][0]["normalized_data"]))
    corrected_data["editorial_notes"] = [
        "Nova versão privada criada depois da retirada e novamente sujeita a revisão."
    ]
    corrected = await editorial.correct_case(
        case_id=activity_case_id,
        payload=EditorialCorrectionRequest(
            expected_revision=5,
            rationale=(
                "A retirada antecede esta nova versão; nenhum conteúdo publicado foi reescrito."
            ),
            normalized_data=corrected_data,
        ),
        actor=actor,
    )
    assert corrected["current_state"] == "PENDING"
    assert len(corrected["versions"]) == 2
    assert corrected["versions"][1]["is_current"] is False
    await editorial.transition(
        case_id=activity_case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=6,
        rationale="A versão corrigida será comparada novamente com a fonte arquivada.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=activity_case_id,
        action=EditorialAction.APPROVE,
        expected_revision=7,
        rationale="Fonte, prova, limitações e nota editorial novamente confirmadas.",
        source_confirmed=True,
        actor=actor,
    )
    republication_preview = await publisher.inspect(case_id=activity_case_id)
    assert republication_preview["eligible"] is True
    republication_source = republication_preview["source"]
    republication_version = republication_preview["editorial_version"]
    assert isinstance(republication_source, dict)
    assert isinstance(republication_version, dict)
    republished = await publisher.publish(
        case_id=activity_case_id,
        payload=ParliamentEditorialPublicationRequest(
            expected_revision=int(republication_preview["revision"]),
            rationale=("Administrador confirmou a nova versão e republicou apenas a atividade."),
            confirmed_scope="activity",
            expected_snapshot_id=str(republication_preview["target_id"]),
            expected_source_sha256=str(republication_source["content_sha256"]),
            expected_snapshot_sha256=str(republication_preview["snapshot_sha256"]),
            expected_editorial_sha256=str(republication_version["normalized_sha256"]),
            expected_publication_proof_sha256=str(
                republication_preview["publication_proof_sha256"]
            ),
            confirm_source_reviewed=True,
            confirm_no_individual_inference=True,
            confirm_publication=True,
        ),
        actor=admin,
    )
    assert republished["state"] == "PUBLISHED"
    assert len(await public.list_sessions(legislature=legislature, limit=10, offset=0)) == 2

    final_case = await editorial.get_case(activity_case_id)
    assert final_case["revision"] == 9
    assert [event["action"] for event in final_case["publication_events"]] == [
        "PUBLISH",
        "WITHDRAW",
        "PUBLISH",
    ]
