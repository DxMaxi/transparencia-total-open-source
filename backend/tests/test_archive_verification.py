"""Integração real do cálculo de hashes sem transferir conteúdo privado."""

import hashlib
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import asyncpg
import pytest
from pydantic import SecretStr

from app.repositories.postgres import _asyncpg_connection_options
from scripts import verify_v4_archive


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="PostgreSQL descartável")
@pytest.mark.parametrize("problem", [None, "content", "size", "key"])
async def test_actual_postgres_bytes_are_verified_without_modifying_them(monkeypatch, problem):
    dsn = os.environ["DATABASE_URL"]
    assert urlsplit(dsn).hostname in {"localhost", "127.0.0.1", "::1"}
    connection_url, server_settings = _asyncpg_connection_options(dsn)
    connection = await asyncpg.connect(connection_url, server_settings=server_settings)
    content = b"synthetic archive, no private data" * 65536
    digest = hashlib.sha256(content).hexdigest()
    key = f"sha256/{digest[:2]}/{digest}"
    observed_content = b"X" + content[1:] if problem == "content" else content
    expected_size = len(content) + (1 if problem == "size" else 0)
    stored_key = "sha256/wrong" if problem == "key" else key

    class ConnectionProxy:
        def __init__(self):
            self.close = AsyncMock()

        def transaction(self, **kwargs):
            assert kwargs == {"isolation": "repeatable_read", "readonly": True}
            return connection.transaction(**kwargs)

        async def fetch(self, query, *args):
            rows = await connection.fetch(query, *args)
            assert all("content" not in row for row in rows)
            return rows

    proxy = ConnectionProxy()
    try:
        # A tabela temporária sombreia o nome apenas nesta ligação. Nunca altera o arquivo real.
        await connection.execute("""
            CREATE TEMP TABLE raw_source_objects (
                storage_key text, content_sha256 text, byte_size bigint, content bytea
            )
        """)
        await connection.execute(
            "INSERT INTO raw_source_objects VALUES ($1, $2, $3, $4)",
            stored_key,
            digest,
            expected_size,
            observed_content,
        )
        monkeypatch.setattr(verify_v4_archive.asyncpg, "connect", AsyncMock(return_value=proxy))
        monkeypatch.setattr(
            verify_v4_archive, "get_settings", lambda: SimpleNamespace(database_url=SecretStr(dsn))
        )
        result = await verify_v4_archive.verify_archive()
        assert result["checked"] == 1
        assert result["corrupt"] == int(problem is not None)
        assert result["status"] == ("CORRUPT" if problem else "VERIFIED")
        assert "synthetic archive" not in json.dumps(result)
        if problem == "content":
            assert result["failures"][0]["observed_size"] == len(content)
            assert result["failures"][0]["observed_sha256"] != digest
        assert (
            await connection.fetchval("SELECT content FROM raw_source_objects") == observed_content
        )
        proxy.close.assert_awaited_once()
        # O limite continua a limitar os objetos realmente verificados.
        assert (await verify_v4_archive.verify_archive(limit=1))["checked"] == 1
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_archive_connection_failure_has_no_private_output(monkeypatch, capsys):
    monkeypatch.setattr(verify_v4_archive, "parse_args", lambda: SimpleNamespace(limit=None))
    monkeypatch.setattr(
        verify_v4_archive,
        "get_settings",
        lambda: SimpleNamespace(database_url=SecretStr("synthetic-private-connection")),
    )
    monkeypatch.setattr(
        verify_v4_archive.asyncpg,
        "connect",
        AsyncMock(side_effect=RuntimeError("synthetic-private-connection")),
    )
    with pytest.raises(SystemExit) as caught:
        await verify_v4_archive.main_async()
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out) == {"status": "CHECK_FAILED", "read_only": True}
