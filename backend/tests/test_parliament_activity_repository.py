from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import HttpUrl

from app.models.api import OfficialSource, SourcePublisher
from app.models.parliamentary import (
    ParliamentActivityDataset,
    ParliamentaryInitiativeRecord,
    ParliamentarySessionRecord,
)
from app.repositories.parliament_activity import ParliamentActivityRepository


def _dataset() -> ParliamentActivityDataset:
    source = OfficialSource(
        publisher=SourcePublisher.PARLIAMENT,
        label="Assembleia da República — Dados Abertos",
        url=HttpUrl("https://www.parlamento.pt/dados.json"),
        retrieved_at=datetime(2026, 8, 6, 10, 0, tzinfo=UTC),
        content_sha256="a" * 64,
    )
    return ParliamentActivityDataset(
        legislature="XVII",
        dataset_url=HttpUrl("https://www.parlamento.pt/dados.json"),
        document_sha256="a" * 64,
        sessions=[
            ParliamentarySessionRecord(
                source_id="reu-1",
                legislature="XVII",
                session_number="1",
                title="Reunião plenária",
                starts_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
                source=source,
            )
        ],
        initiatives=[
            ParliamentaryInitiativeRecord(
                source_id="ini-1",
                legislature="XVII",
                number="1/XVII/1",
                initiative_type="Projeto de Lei",
                title="Título oficial",
                official_url=HttpUrl("https://www.parlamento.pt/iniciativa/1"),
                source=source,
            )
        ],
    )


@pytest.mark.asyncio
async def test_rejects_dataset_without_attested_source() -> None:
    connection = AsyncMock()
    connection.fetchval.return_value = None

    with pytest.raises(RuntimeError, match="arquivados e atestados"):
        await ParliamentActivityRepository._require_attested_source(connection, _dataset())


@pytest.mark.asyncio
async def test_upserts_sessions_and_initiatives() -> None:
    connection = AsyncMock()
    dataset = _dataset()

    sessions = await ParliamentActivityRepository._upsert_sessions(
        connection, dataset, "source-1"
    )
    initiatives = await ParliamentActivityRepository._upsert_initiatives(
        connection, dataset, "source-1"
    )

    assert sessions == 1
    assert initiatives == 1
    assert connection.execute.await_count == 2
