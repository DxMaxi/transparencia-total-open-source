"""Integração real: snapshot parlamentar -> proposta privada V5.2."""

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
    ParliamentEditorialProposalRequest,
    StaffRole,
    StaffSession,
)
from app.models.parliamentary import (
    ParliamentActivityDataset,
    ParliamentaryInitiativeRecord,
    ParliamentarySessionRecord,
)
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.parliament_activity import ParliamentActivityRepository
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.public_parliament import PublicParliamentRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
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
async def test_snapshot_adapter_builds_idempotent_private_scoped_proposals(
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
        try:
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
        except asyncpg.ForeignKeyViolationError:
            pytest.skip("A base de integração liga staff_profiles a auth.users")
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
