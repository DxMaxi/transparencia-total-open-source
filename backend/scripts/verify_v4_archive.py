"""Verifica, em modo exclusivamente de leitura, os bytes oficiais arquivados na V4."""

import argparse
import asyncio
import json
from typing import Any

import asyncpg

from app.core.config import get_settings
from app.repositories.postgres import _asyncpg_connection_options


async def verify_archive(*, limit: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")

    query = """
        SELECT storage_key, content_sha256, byte_size,
               encode(sha256(content), 'hex') AS observed_sha256,
               octet_length(content)::bigint AS observed_size
        FROM raw_source_objects
        ORDER BY storage_key
    """
    arguments: tuple[object, ...] = ()
    if limit is not None:
        query += " LIMIT $1"
        arguments = (limit,)

    # O servidor calcula o hash dos bytes reais. Não transferir o arquivo inteiro
    # para a memória do processo que executa a verificação.
    dsn, server_settings = _asyncpg_connection_options(settings.database_url.get_secret_value())
    connection = await asyncpg.connect(
        dsn, server_settings=server_settings, timeout=10, command_timeout=300
    )
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            rows = await connection.fetch(query, *arguments)
    finally:
        await connection.close()

    corrupt: list[dict[str, object]] = []
    verified = 0
    for row in rows:
        expected_sha256 = str(row["content_sha256"])
        expected_size = int(row["byte_size"])
        observed_sha256 = str(row["observed_sha256"])
        observed_size = int(row["observed_size"])
        expected_key = f"sha256/{expected_sha256[:2]}/{expected_sha256}"

        problems: list[str] = []
        if str(row["storage_key"]) != expected_key:
            problems.append("storage_key não corresponde ao SHA-256")
        if observed_sha256 != expected_sha256:
            problems.append("conteúdo não corresponde ao SHA-256")
        if observed_size != expected_size:
            problems.append("tamanho não corresponde ao registo")

        if problems:
            corrupt.append(
                {
                    "storage_key": str(row["storage_key"]),
                    "expected_sha256": expected_sha256,
                    "observed_sha256": observed_sha256,
                    "expected_size": expected_size,
                    "observed_size": observed_size,
                    "problems": problems,
                }
            )
        else:
            verified += 1

    return {
        "status": "VERIFIED" if not corrupt else "CORRUPT",
        "checked": len(rows),
        "verified": verified,
        "corrupt": len(corrupt),
        "failures": corrupt,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Número máximo de objetos a verificar; por omissão verifica todos.",
    )
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit deve ser maior que zero")
    try:
        result = await verify_archive(limit=args.limit)
    except Exception:
        print(json.dumps({"status": "CHECK_FAILED", "read_only": True}))
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "VERIFIED":
        raise SystemExit(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
