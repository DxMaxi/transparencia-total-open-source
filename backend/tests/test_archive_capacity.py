import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from scripts import report_archive_capacity


def test_archive_warning_limit_uses_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAW_ARCHIVE_WARNING_BYTES", raising=False)
    assert report_archive_capacity._warning_limit() == 400_000_000


def test_archive_warning_limit_accepts_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAW_ARCHIVE_WARNING_BYTES", "750000000")
    assert report_archive_capacity._warning_limit() == 750_000_000


@pytest.mark.parametrize("value", ["texto", "0", "9999999"])
def test_archive_warning_limit_rejects_unsafe_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("RAW_ARCHIVE_WARNING_BYTES", value)
    with pytest.raises(RuntimeError):
        report_archive_capacity._warning_limit()


@pytest.fixture
def capacity_database(monkeypatch):
    connection = MagicMock()
    connection.fetchrow = AsyncMock(
        return_value={
            "object_count": 145,
            "logical_bytes": 1_697_791_199,
            "relation_bytes": 295_739_392,
            "largest_object_bytes": 100_000_000,
            "database_bytes": 532_106_387,
        }
    )
    connection.close = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock(return_value=False)
    connection.transaction.return_value = transaction
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(report_archive_capacity.asyncpg, "connect", connect)
    monkeypatch.setattr(
        report_archive_capacity,
        "get_settings",
        lambda: SimpleNamespace(database_url=SecretStr("synthetic-private-connection")),
    )
    monkeypatch.delenv("DATABASE_WARNING_BYTES", raising=False)
    monkeypatch.delenv("RAW_ARCHIVE_WARNING_BYTES", raising=False)
    return connection, connect


@pytest.mark.asyncio
async def test_database_warns_even_when_archive_relation_is_below_limit(capacity_database):
    connection, connect = capacity_database
    result = await report_archive_capacity.report()
    assert result["status"] == "WARNING"
    assert result["warning_reasons"] == ["DATABASE_WARNING_THRESHOLD_REACHED"]
    assert result["database_bytes"] == 532_106_387
    assert result["database_warning_bytes"] == 450_000_000
    assert result["utilization_percent"] < 100
    assert result["database_utilization_percent"] > 100
    connection.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)
    connection.close.assert_awaited_once()
    assert connect.call_args.kwargs["command_timeout"] == 30


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "archive,database,reasons",
    [
        (399_999_999, 449_999_999, []),
        (400_000_000, 449_999_999, ["ARCHIVE_WARNING_THRESHOLD_REACHED"]),
        (100_000_000, 450_000_000, ["DATABASE_WARNING_THRESHOLD_REACHED"]),
        (
            400_000_000,
            450_000_000,
            ["ARCHIVE_WARNING_THRESHOLD_REACHED", "DATABASE_WARNING_THRESHOLD_REACHED"],
        ),
    ],
)
async def test_capacity_thresholds_are_independent(capacity_database, archive, database, reasons):
    row = capacity_database[0].fetchrow.return_value
    row.update(relation_bytes=archive, database_bytes=database)
    result = await report_archive_capacity.report()
    assert result["warning_reasons"] == reasons
    assert result["status"] == ("WARNING" if reasons else "OK")


@pytest.mark.asyncio
async def test_capacity_threshold_can_be_reviewed_for_another_host(capacity_database, monkeypatch):
    monkeypatch.setenv("DATABASE_WARNING_BYTES", "2000000000")
    result = await report_archive_capacity.report()
    assert result["status"] == "OK"
    assert result["database_warning_bytes"] == 2_000_000_000
    assert "compra" not in result["action"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["bad-private-value", "0", "9999999"])
async def test_invalid_database_threshold_never_connects(capacity_database, monkeypatch, value):
    monkeypatch.setenv("DATABASE_WARNING_BYTES", value)
    with pytest.raises(RuntimeError):
        await report_archive_capacity.report()
    capacity_database[1].assert_not_awaited()


@pytest.mark.asyncio
async def test_capacity_connection_error_is_not_exposed(capacity_database, capsys):
    capacity_database[1].side_effect = RuntimeError("synthetic-private-connection")
    with pytest.raises(SystemExit) as caught:
        await report_archive_capacity.main_async()
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out) == {"status": "CHECK_FAILED", "read_only": True}


@pytest.mark.asyncio
async def test_capacity_warning_has_distinct_exit_status(capacity_database, capsys):
    with pytest.raises(SystemExit) as caught:
        await report_archive_capacity.main_async()
    assert caught.value.code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "WARNING"
