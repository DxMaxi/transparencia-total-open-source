"""Emite parâmetros libpq para Docker sem registar o URL PostgreSQL de produção."""

from __future__ import annotations

import os
import sys

from app.services.postgres_backup_connection import (
    PostgresBackupConnectionError,
    docker_env_file_text,
    postgres_environment_from_url,
)


def main() -> None:
    try:
        environment = postgres_environment_from_url(os.environ.get("DATABASE_URL", ""))
    except PostgresBackupConnectionError as exc:
        raise SystemExit(f"configuração PostgreSQL recusada: {exc}") from exc
    sys.stdout.write(docker_env_file_text(environment))


if __name__ == "__main__":
    main()
