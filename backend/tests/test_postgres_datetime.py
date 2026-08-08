from datetime import datetime, timedelta, timezone

from app.repositories.postgres import _asyncpg_connection_options, _database_timestamp


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


def test_asyncpg_connection_options_translate_prisma_schema() -> None:
    database_url, server_settings = _asyncpg_connection_options(
        "postgresql://user:password@localhost:5432/database"
        "?schema=review&sslmode=require"
    )

    assert database_url == (
        "postgresql://user:password@localhost:5432/database?sslmode=require"
    )
    assert server_settings == {"search_path": "review"}


def test_asyncpg_connection_options_preserve_plain_url() -> None:
    database_url, server_settings = _asyncpg_connection_options(
        "postgresql://user:password@localhost:5432/database"
    )

    assert database_url == "postgresql://user:password@localhost:5432/database"
    assert server_settings == {}
