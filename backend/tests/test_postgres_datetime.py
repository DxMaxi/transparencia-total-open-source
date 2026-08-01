from datetime import datetime, timedelta, timezone

from app.repositories.postgres import _database_timestamp


def test_database_timestamp_converts_aware_value_to_naive_utc() -> None:
    source = datetime(2026, 8, 1, 20, 32, tzinfo=timezone(timedelta(hours=1)))

    result = _database_timestamp(source)

    assert result == datetime(2026, 8, 1, 19, 32)
    assert result is not None
    assert result.tzinfo is None


def test_database_timestamp_preserves_none_and_naive_values() -> None:
    naive = datetime(2026, 8, 1, 19, 32)

    assert _database_timestamp(None) is None
    assert _database_timestamp(naive) is naive
