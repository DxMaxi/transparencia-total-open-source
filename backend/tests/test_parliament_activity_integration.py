"""Teste real do circuito parlamentar: arquivo -> snapshot -> revisão -> público.

Exige PostgreSQL descartável com todas as migrações aplicadas. Sem
``DATABASE_URL``, o módulo é ignorado para manter o desenvolvimento local leve.
"""

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

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
from app.models.parliamentary import (
    ParliamentActivityDataset,
    ParliamentaryInitiativeRecord,
    ParliamentarySessionRecord,
)
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.repositories.parliament_activity import ParliamentActivityRepository, _dataset_digest
from app.repositories.parliament_publication import ParliamentSnapshotPublicationRepository
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


def _dataset() -> tuple[ParliamentActivityDataset, PrivateRawDocument]:
    suffix = uuid.uuid4().hex[:12]
    legislature = f"TEST-{suffix}"
    retrieved_at = datetime.now(UTC)
    content = json.dumps(
        {"legislature": legislature, "fixture": suffix},
        sort_keys=True,
    ).encode()
    content_sha256 = hashlib.sha256(content).hexdigest()
    source_url = HttpUrl(f"https://www.parlamento.pt/testes/{suffix}.json")
    raw = PrivateRawDocument(
        source_url=source_url,
        retrieved_at=retrieved_at,
        content_sha256=content_sha256,
        mime_type="application/json",
        content=content,
    )
    source = OfficialSource(
        publisher=SourcePublisher.PARLIAMENT,
        label="Assembleia da República — fixture de integração",
        url=source_url,
        retrieved_at=retrieved_at,
        content_sha256=content_sha256,
    )
    dataset = ParliamentActivityDataset(
        legislature=legislature,
        dataset_url=source_url,
        document_sha256=content_sha256,
        parser_version="parliament-integration-v1",
        collected_at=retrieved_at,
        raw_document=raw,
        sessions=[
            ParliamentarySessionRecord(
                source_id=f"session-{suffix}",
                legislature=legislature,
                session_number="1",
                title="Reunião de integração",
                starts_at=retrieved_at,
                source=source,
            )
        ],
        initiatives=[
            ParliamentaryInitiativeRecord(
                source_id=f"initiative-{suffix}",
                legislature=legislature,
                number=f"1/{legislature}",
                initiative_type="Projeto de teste",
                title="Iniciativa de integração",
                official_url=source_url,
                source=source,
            )
        ],
        votes=[
            VoteEvent(
                source_id=f"vote-{suffix}",
                title="Votação de integração",
                voted_at=retrieved_at,
                result="Aprovado",
                initiative_number=f"1/{legislature}",
                is_nominal=False,
                records=[
                    VoteRecord(
                        actor_label="Grupo não associado",
                        actor_type=VoteActorType.UNKNOWN,
                        choice=VoteChoice.FAVOR,
                    )
                ],
                source=source,
            )
        ],
    )
    return dataset, raw


@pytest.mark.asyncio
async def test_full_append_only_publication_cycle(
    repository: OfficialIndexStagingRepository,
) -> None:
    dataset, raw = _dataset()
    assert repository.pool is not None
    receipt = await repository.archive_raw_document(raw_document=raw)
    activity = ParliamentActivityRepository(repository.pool)

    first = await activity.persist(dataset, archive_receipt=receipt, archived_by="integration-test")
    second = await activity.persist(
        dataset, archive_receipt=receipt, archived_by="integration-test"
    )

    assert first.snapshot_created is True
    assert second.snapshot_created is False
    assert second.snapshot_id == first.snapshot_id
    assert (
        second.sessions_written,
        second.initiatives_written,
        second.vote_events_written,
        second.vote_records_written,
    ) == (0, 0, 0, 0)

    publication = ParliamentSnapshotPublicationRepository(repository.pool)
    preview = await publication.inspect(legislature=dataset.legislature)
    expected_counts = {
        "sessions": 1,
        "initiatives": 1,
        "votes": 1,
        "vote_records": 1,
    }
    assert preview["counts"] == expected_counts
    assert preview["publication_eligible"] is True

    await publication.review(
        legislature=dataset.legislature,
        scopes={"activity", "votes"},
        publishable=True,
        expected_source_sha256=dataset.document_sha256,
        expected_normalised_sha256=_dataset_digest(dataset),
        expected_counts=expected_counts,
        reviewer_alias="integration-reviewer",
        rationale="Fotografia oficial e contagens confirmadas no teste de integração.",
    )

    public = PublicParliamentRepository(repository.pool)
    sessions = await public.list_sessions(
        legislature=dataset.legislature,
        limit=10,
        offset=0,
    )
    initiatives = await public.list_initiatives(
        legislature=dataset.legislature,
        limit=10,
        offset=0,
    )
    votes = await public.list_votes(
        legislature=dataset.legislature,
        limit=10,
        offset=0,
    )
    assert [item["source_id"] for item in sessions] == [dataset.sessions[0].source_id]
    assert [item["source_id"] for item in initiatives] == [dataset.initiatives[0].source_id]
    assert [item["source_id"] for item in votes] == [dataset.votes[0].source_id]
    assert votes[0]["records"][0]["actor_type"] == "UNKNOWN"

    await publication.review(
        legislature=dataset.legislature,
        scopes={"votes"},
        publishable=False,
        expected_source_sha256=dataset.document_sha256,
        expected_normalised_sha256=_dataset_digest(dataset),
        expected_counts=expected_counts,
        reviewer_alias="integration-reviewer",
        rationale="Retirada deliberada da votação durante o teste de integração.",
    )
    assert (
        await public.list_votes(
            legislature=dataset.legislature,
            limit=10,
            offset=0,
        )
        == []
    )
    assert await public.list_sessions(
        legislature=dataset.legislature,
        limit=10,
        offset=0,
    )

    async with repository.pool.acquire() as connection:
        with pytest.raises(Exception, match="append-only"):
            await connection.execute(
                "UPDATE vote_events SET title = 'alterado' WHERE id = $1",
                votes[0]["id"],
            )
