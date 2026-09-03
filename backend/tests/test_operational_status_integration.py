"""Prova do diagnóstico apenas no PostgreSQL local descartável do CI/ensaio."""

import os
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from pydantic import SecretStr

from app.services.parliament_readiness import exact_vote_identity_schema_is_ready
from scripts import check_v4_operational_status as monitor

_configured_url = os.getenv("DATABASE_URL", "")
_url = urlsplit(_configured_url)
pytestmark = pytest.mark.skipif(
    _url.hostname not in {"127.0.0.1", "localhost", "::1"} or not _url.path.endswith("_test"),
    reason="Exige PostgreSQL local descartável identificado",
)


@pytest.fixture
async def connection():
    dsn = urlunsplit((_url.scheme, _url.netloc, _url.path, "", ""))
    connection = await asyncpg.connect(dsn)
    try:
        assert await connection.fetchval(
            "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
        ), "Recusado: destino não identificado como descartável"
        assert await connection.fetchval(
            "SELECT singleton FROM auth.tt_disposable_test_marker WHERE singleton = TRUE"
        )
        yield connection, dsn
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_real_monitor_cannot_write_and_does_not_change_runs(connection, monkeypatch):
    database, dsn = connection
    before = await database.fetchval("SELECT count(*) FROM sync_runs")
    real_connect = asyncpg.connect
    observations = []

    class ReadOnlyInspection:
        """Observa a transação usada pelo monitor, sem a substituir por um mock."""

        def __init__(self, actual):
            self.actual = actual

        def transaction(self, **kwargs):
            return self.actual.transaction(**kwargs)

        async def fetchval(self, query):
            observations.append(await self.actual.fetchval("SHOW transaction_read_only"))
            assert await self.actual.fetchval("SHOW transaction_isolation") == "repeatable read"
            # Um savepoint contém a tentativa sintética; zero linhas chegam a ser escritas.
            with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
                async with self.actual.transaction():
                    await self.actual.execute("DELETE FROM sync_runs WHERE FALSE")
            return await self.actual.fetchval(query)

        async def fetch(self, query, *args):
            return await self.actual.fetch(query, *args)

        async def close(self):
            await self.actual.close()

    async def connect(*args, **kwargs):
        return ReadOnlyInspection(await real_connect(*args, **kwargs))

    monkeypatch.setattr(monitor.asyncpg, "connect", connect)
    monkeypatch.setattr(
        monitor, "get_settings", lambda: SimpleNamespace(database_url=SecretStr(dsn))
    )
    report = await monitor.check_status()
    assert report["read_only"] is True
    assert report["publication"] == "NOT_ATTEMPTED"
    assert observations == ["on"]
    parliament = next(
        row for row in report["sources"] if row["source_name"] == "PARLIAMENT_ACTIVITY"
    )
    assert parliament["ingestion_readiness"] == "READY"
    assert await database.fetchval("SELECT count(*) FROM sync_runs") == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remove_object",
    [
        "DROP INDEX public.vote_records_person_official_id_per_event_key",
        "ALTER TABLE public.vote_records DROP CONSTRAINT vote_records_actor_source_id_not_blank",
        "ALTER TABLE public.vote_records DROP COLUMN actor_source_id",
    ],
)
async def test_shared_gate_refuses_each_missing_object_without_persisting_changes(
    connection, remove_object
):
    database, _ = connection
    assert await exact_vote_identity_schema_is_ready(database) is True
    transaction = database.transaction()
    await transaction.start()
    try:
        await database.execute(remove_object)
        assert await exact_vote_identity_schema_is_ready(database) is False
    finally:
        # Apenas esquema descartável; reposição por rollback, nunca por reescrita de dados.
        await transaction.rollback()
    assert await exact_vote_identity_schema_is_ready(database) is True
