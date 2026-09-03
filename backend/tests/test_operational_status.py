"""A monitorização nunca confunde recolha bloqueada com sucesso nem divulga erros."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from pydantic import SecretStr

from app.services.parliament_readiness import EXACT_VOTE_IDENTITY_MIGRATION
from scripts import check_v4_operational_status as monitor


@pytest.fixture
def database(monkeypatch):
    connection = MagicMock()
    connection.fetchval = AsyncMock(return_value=True)
    connection.fetch = AsyncMock(
        return_value=[
            {
                "source_name": name,
                "status": "SUCCEEDED",
                "started_at": datetime.now(UTC) - timedelta(minutes=1),
                "finished_at": datetime.now(UTC),
                "records_read": 2,
                "records_written": 1,
                "has_error": False,
            }
            for name in monitor.OPERATIONAL_SOURCES
        ]
    )
    connection.close = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    connection.transaction.return_value = transaction
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(monitor.asyncpg, "connect", connect)
    monkeypatch.setattr(
        monitor,
        "get_settings",
        lambda: SimpleNamespace(database_url=SecretStr("synthetic-private-connection")),
    )
    monkeypatch.setenv("V4_SOURCE_MAX_AGE_HOURS", "36")
    return connection, connect


def _parliament(database):
    return next(
        row for row in database[0].fetch.return_value if row["source_name"] == "PARLIAMENT_ACTIVITY"
    )


def _source(report):
    return next(row for row in report["sources"] if row["source_name"] == "PARLIAMENT_ACTIVITY")


@pytest.mark.asyncio
async def test_monitor_reads_one_snapshot_without_writes_or_error_text(database):
    connection, connect = database
    report = await monitor.check_status()

    assert report["status"] == "HEALTHY"
    assert report["read_only"] is True
    assert report["publication"] == "NOT_ATTEMPTED"
    assert report["unhealthy_sources"] == []
    assert _source(report)["ingestion_readiness"] == "READY"
    assert _source(report)["required_migration"] is None
    connection.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
    connection.close.assert_awaited_once()
    assert connect.await_args.kwargs == {"timeout": 10, "command_timeout": 10}
    query = connection.fetch.await_args.args[0]
    assert "(error_message IS NOT NULL) AS has_error" in query
    assert "records_written, error_message" not in query
    assert "id DESC" in query
    for method in (connection.fetch, connection.fetchval):
        sql = method.await_args.args[0].upper()
        assert not any(keyword in sql for keyword in ("INSERT", "UPDATE", "DELETE", "ALTER"))
    assert not connection.execute.called


@pytest.mark.asyncio
@pytest.mark.parametrize("last_status", ["SUCCEEDED", "PARTIAL", "FAILED"])
async def test_missing_schema_is_current_blocker_even_with_recent_run(database, last_status):
    database[0].fetchval.return_value = False
    _parliament(database)["status"] = last_status
    report = await monitor.check_status()
    parliament = _source(report)

    assert report["status"] == "ATTENTION_REQUIRED"
    assert report["unhealthy_sources"] == ["PARLIAMENT_ACTIVITY"]
    assert parliament["status"] == "SCHEMA_MIGRATION_REQUIRED"
    assert parliament["last_run_status"] == last_status
    assert parliament["stale"] is False
    assert parliament["records_read"] == 2
    assert parliament["required_migration"] == EXACT_VOTE_IDENTITY_MIGRATION
    assert parliament["blocking_reason"] == "EXACT_VOTE_IDENTITY_SCHEMA_MISSING"
    assert parliament["ingestion_readiness"] == "BLOCKED_SCHEMA"
    other = next(row for row in report["sources"] if row["source_name"] == "BASE_CONTRACTS")
    assert other["status"] == "SUCCEEDED"
    assert other["ingestion_readiness"] == "NOT_CHECKED"


@pytest.mark.asyncio
async def test_old_failure_stays_visible_without_repeating_private_content(database):
    database[0].fetchval.return_value = False
    row = _parliament(database)
    row.update(
        status="FAILED",
        finished_at=datetime.now(UTC) - timedelta(days=6),
        has_error=True,
        error_message="synthetic-secret https://example.invalid/?token=private",
    )
    report = await monitor.check_status()
    parliament = _source(report)
    assert parliament["stale"] is True
    assert parliament["last_run_status"] == "FAILED"
    assert parliament["error"] == (
        "A última execução registou um erro; diagnóstico interno reservado."
    )
    assert "synthetic-secret" not in json.dumps(report)
    assert "token=private" not in json.dumps(report)


@pytest.mark.asyncio
@pytest.mark.parametrize("schema_ready", [True, False])
async def test_no_run_is_never_healthy_and_still_reports_schema_blocker(database, schema_ready):
    database[0].fetchval.return_value = schema_ready
    database[0].fetch.return_value.remove(_parliament(database))
    report = await monitor.check_status()
    parliament = _source(report)
    assert report["status"] == "ATTENTION_REQUIRED"
    assert parliament["last_run_status"] == "MISSING"
    assert parliament["status"] == ("MISSING" if schema_ready else "SCHEMA_MIGRATION_REQUIRED")
    assert parliament["observed_at"] is None
    assert parliament["stale"] is True
    assert parliament["records_written"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("last_status", ["RUNNING", "FAILED", "PARTIAL", "SUCCEEDED"])
async def test_schema_ready_never_clears_an_old_or_unsuccessful_run(database, last_status):
    _parliament(database).update(
        status=last_status,
        # Valores PostgreSQL sem fuso são UTC, como no contrato existente.
        finished_at=(datetime.now(UTC) - timedelta(days=3)).replace(tzinfo=None),
    )
    report = await monitor.check_status()
    assert report["status"] == "ATTENTION_REQUIRED"
    assert _source(report)["status"] == last_status
    assert _source(report)["blocking_reason"] is None
    assert _source(report)["observed_at"].endswith("+00:00")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["SUCCEEDED", "PARTIAL"])
async def test_recent_success_preserves_existing_health_policy(database, status):
    _parliament(database)["status"] = status
    assert (await monitor.check_status())["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_monitor_main_keeps_nonzero_exit_for_blocked_schema(database, capsys):
    database[0].fetchval.return_value = False
    with pytest.raises(SystemExit) as error:
        await monitor.main_async()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "ATTENTION_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["connect", "probe", "fetch", "close"])
async def test_monitor_failure_has_safe_json_and_nonzero_exit(database, capsys, failure_point):
    connection, connect = database
    failed = {
        "connect": connect,
        "probe": connection.fetchval,
        "fetch": connection.fetch,
        "close": connection.close,
    }[failure_point]
    failed.side_effect = asyncpg.PostgresError("postgresql://private-secret@invalid/private")
    with pytest.raises(SystemExit) as error:
        await monitor.main_async()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "private-secret" not in output.out + output.err
    assert not output.err
    assert json.loads(output.out)["status"] == "CHECK_FAILED"
    if failure_point != "connect":
        connection.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("age", ["0", "721", "private-invalid-setting"])
async def test_invalid_max_age_does_not_connect_or_echo_input(database, monkeypatch, capsys, age):
    monkeypatch.setenv("V4_SOURCE_MAX_AGE_HOURS", age)
    with pytest.raises(SystemExit):
        await monitor.main_async()
    database[1].assert_not_awaited()
    output = capsys.readouterr()
    assert "private-invalid-setting" not in output.out + output.err
    assert json.loads(output.out)["status"] == "CHECK_FAILED"
