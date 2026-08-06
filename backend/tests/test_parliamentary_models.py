from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.api import OfficialSource, SourcePublisher
from app.models.parliamentary import (
    ParliamentActivityDataset,
    ParliamentaryInitiativeRecord,
    ParliamentarySessionRecord,
)


def _source() -> OfficialSource:
    return OfficialSource(
        publisher=SourcePublisher.PARLIAMENT,
        label="Assembleia da República — Dados Abertos",
        url="https://www.parlamento.pt/dados-abertos.json",
        retrieved_at=datetime(2026, 8, 6, 8, 0, tzinfo=UTC),
        content_sha256="a" * 64,
    )


def test_session_normalises_naive_datetimes_to_utc() -> None:
    session = ParliamentarySessionRecord(
        source_id="sessao-1",
        legislature="XVII",
        session_number="1",
        title="Reunião plenária",
        starts_at=datetime(2026, 8, 6, 10, 0),
        source=_source(),
    )

    assert session.starts_at.tzinfo is UTC


def test_initiative_preserves_missing_optional_facts() -> None:
    initiative = ParliamentaryInitiativeRecord(
        source_id="ini-1",
        legislature="XVII",
        number="1/XVII/1",
        initiative_type="Projeto de Lei",
        title="Exemplo oficial",
        official_url="https://www.parlamento.pt/ActividadeParlamentar/Paginas/DetalheIniciativa.aspx?BID=1",
        source=_source(),
    )

    assert initiative.status is None
    assert initiative.introduced_at is None


def test_dataset_rejects_invalid_document_hash() -> None:
    with pytest.raises(ValidationError):
        ParliamentActivityDataset(
            legislature="XVII",
            dataset_url="https://www.parlamento.pt/dados-abertos.json",
            document_sha256="invalido",
        )
