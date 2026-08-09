from __future__ import annotations

import pytest

from app.services.postgres_backup_connection import (
    PostgresBackupConnectionError,
    docker_env_file_text,
    postgres_environment_from_url,
)


def test_postgres_environment_separates_uri_credentials_and_options() -> None:
    environment = postgres_environment_from_url(
        "postgresql://backup%2Euser:p%40ss%3Dword@[2001:db8::2]:6543/transparencia"
        "?schema=public&sslmode=require&connect_timeout=20"
    )

    assert environment == {
        "PGHOST": "2001:db8::2",
        "PGPORT": "6543",
        "PGUSER": "backup.user",
        "PGPASSWORD": "p@ss=word",
        "PGDATABASE": "transparencia",
        "PGSSLMODE": "require",
        "PGCONNECT_TIMEOUT": "20",
    }
    rendered = docker_env_file_text(environment)
    assert "postgresql://" not in rendered
    assert rendered.endswith("\n")


def test_postgres_environment_translates_ssl_true_and_default_port() -> None:
    environment = postgres_environment_from_url(
        "postgres://user:password@db.example.invalid/database?ssl=true"
    )

    assert environment["PGPORT"] == "5432"
    assert environment["PGSSLMODE"] == "require"


@pytest.mark.parametrize(
    "database_url, message",
    [
        ("", "não configurada"),
        ("mysql://user:password@db.example.invalid/database", "postgres"),
        ("postgresql://user@db.example.invalid/database", "palavra-passe"),
        (
            "postgresql://user:password@db.example.invalid/database?schema=private",
            "schema=public",
        ),
        (
            "postgresql://user:password@db.example.invalid/database?pool_timeout=10",
            "não suportado",
        ),
        (
            "postgresql://user:password@db.example.invalid/database?ssl=true&sslmode=verify-full",
            "contraditória",
        ),
        (
            "postgresql://user:password@db.example.invalid/database?sslmode=require%0AEXPOSED",
            "separadores",
        ),
    ],
)
def test_postgres_environment_rejects_ambiguous_or_unsafe_urls(
    database_url: str, message: str
) -> None:
    with pytest.raises(PostgresBackupConnectionError, match=message):
        postgres_environment_from_url(database_url)
