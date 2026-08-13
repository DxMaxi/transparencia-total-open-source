"""Validação e inventário sanitizado do destino Supabase de staging."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

import asyncpg

from app.services.editorial_staging_readiness import REQUIRED_V5_MIGRATIONS

PROJECT_REF_PATTERN = re.compile(r"^[a-z0-9]{20}$")
SECURE_SSL_MODES = frozenset({"require", "verify-ca", "verify-full"})
POOLER_HOST_SUFFIX = ".pooler.supabase.com"


@dataclass(frozen=True, slots=True)
class StagingTarget:
    project_ref: str
    connection_kind: str


@dataclass(frozen=True, slots=True)
class StagingCatalogSnapshot:
    server_version_num: int
    transaction_read_only: bool
    roles: frozenset[str]
    auth_users_exists: bool
    public_table_count: int
    public_function_count: int
    applied_migrations: frozenset[str]


def _project_ref(value: str, label: str) -> str:
    normalized = value.strip()
    if not PROJECT_REF_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label} não tem a forma de um project ref Supabase")
    return normalized


def parse_forbidden_project_refs(value: str) -> frozenset[str]:
    refs = frozenset(
        _project_ref(item, "STAGING_FORBIDDEN_PROJECT_REFS")
        for item in re.split(r"[\s,]+", value.strip())
        if item
    )
    if not refs:
        raise ValueError("STAGING_FORBIDDEN_PROJECT_REFS tem de identificar pelo menos produção")
    return refs


def validate_staging_target(
    *,
    database_url: str,
    supabase_url: str,
    expected_project_ref: str,
    forbidden_project_refs: str,
) -> StagingTarget:
    """Valida o destino sem devolver ou registar a ligação privada."""

    expected_ref = _project_ref(expected_project_ref, "STAGING_SUPABASE_PROJECT_REF")
    forbidden_refs = parse_forbidden_project_refs(forbidden_project_refs)
    if expected_ref in forbidden_refs:
        raise ValueError("O project ref de staging coincide com um destino proibido")

    try:
        public_url = urlsplit(supabase_url)
    except ValueError as exc:
        raise ValueError("SUPABASE_URL inválida") from exc
    if (
        public_url.scheme != "https"
        or public_url.hostname != f"{expected_ref}.supabase.co"
        or public_url.port not in {None, 443}
        or public_url.username
        or public_url.password
        or public_url.path not in {"", "/"}
        or public_url.query
        or public_url.fragment
    ):
        raise ValueError("SUPABASE_URL não corresponde exatamente ao projeto de staging")

    try:
        database = urlsplit(database_url)
        port = database.port
    except ValueError as exc:
        raise ValueError("DATABASE_URL inválida") from exc
    if database.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL tem de usar PostgreSQL")
    if not database.hostname or not database.username or database.password in {None, ""}:
        raise ValueError("DATABASE_URL de staging está incompleta")
    database_name = unquote(database.path.removeprefix("/"))
    if database_name != "postgres" or database.fragment:
        raise ValueError("DATABASE_URL de staging tem de identificar exatamente a base postgres")

    query = parse_qs(database.query, keep_blank_values=True)
    ssl_modes = query.get("sslmode", [])
    if len(ssl_modes) != 1 or ssl_modes[0].casefold() not in SECURE_SSL_MODES:
        raise ValueError("DATABASE_URL de staging exige sslmode seguro")

    direct_host = f"db.{expected_ref}.supabase.co"
    if database.hostname == direct_host and port in {None, 5432}:
        if unquote(database.username) != "postgres":
            raise ValueError("O utilizador da ligação direta tem de ser postgres")
        connection_kind = "direct"
    elif database.hostname.endswith(POOLER_HOST_SUFFIX) and port in {None, 5432}:
        if unquote(database.username) != f"postgres.{expected_ref}":
            raise ValueError("O utilizador do pooler não corresponde ao projeto de staging")
        connection_kind = "session_pooler"
    else:
        raise ValueError(
            "DATABASE_URL não corresponde à ligação direta ou ao session pooler de staging"
        )

    return StagingTarget(project_ref=expected_ref, connection_kind=connection_kind)


def _check(code: str, ok: bool, success: str, failure: str) -> dict[str, object]:
    return {"code": code, "ok": ok, "detail": success if ok else failure}


def evaluate_staging_catalog(
    snapshot: StagingCatalogSnapshot,
    target: StagingTarget,
    *,
    require_v5_migrations: bool,
) -> dict[str, object]:
    expected_roles = frozenset({"anon", "authenticated"})
    expected_migrations = frozenset(REQUIRED_V5_MIGRATIONS)
    migrations_ok = not require_v5_migrations or expected_migrations.issubset(
        snapshot.applied_migrations
    )
    checks = [
        _check(
            "postgres_17",
            170000 <= snapshot.server_version_num < 180000,
            "PostgreSQL 17 confirmado.",
            "A base não executa a versão principal PostgreSQL 17 suportada.",
        ),
        _check(
            "transaction_read_only",
            snapshot.transaction_read_only,
            "A transação de inventário é read-only.",
            "A transação de inventário não está em modo read-only.",
        ),
        _check(
            "supabase_roles",
            expected_roles.issubset(snapshot.roles),
            "Os papéis Supabase esperados existem.",
            "Faltam papéis Supabase esperados.",
        ),
        _check(
            "auth_users",
            snapshot.auth_users_exists,
            "auth.users existe.",
            "auth.users não existe.",
        ),
        _check(
            "required_v5_migrations",
            migrations_ok,
            "As migrações V5 exigidas pela operação estão aplicadas.",
            "Faltam migrações V5 exigidas pela operação.",
        ),
    ]
    return {
        "catalog_ready": all(bool(check["ok"]) for check in checks),
        "checks": checks,
        "target": {
            "project_ref": target.project_ref,
            "connection_kind": target.connection_kind,
        },
        "database_inventory": {
            "postgres_major": snapshot.server_version_num // 10000,
            "public_table_count": snapshot.public_table_count,
            "public_function_count": snapshot.public_function_count,
            "applied_migration_count": len(snapshot.applied_migrations),
            "required_v5_migration_count": len(
                expected_migrations.intersection(snapshot.applied_migrations)
            ),
        },
        "scope": (
            "Catálogo PostgreSQL em transação read-only; sem linhas editoriais, emails, UUID, "
            "tokens ou ligação privada."
        ),
    }


async def collect_staging_catalog_snapshot(
    connection: asyncpg.Connection,
) -> StagingCatalogSnapshot:
    """Recolhe apenas catálogo e nomes de migração, nunca conteúdo editorial."""

    server_version_num = int(await connection.fetchval("SHOW server_version_num"))
    transaction_read_only = (
        str(await connection.fetchval("SHOW transaction_read_only")).casefold() == "on"
    )
    role_rows = await connection.fetch(
        """
        SELECT rolname
        FROM pg_roles
        WHERE rolname = ANY($1::text[])
        ORDER BY rolname
        """,
        ["anon", "authenticated"],
    )
    auth_users_exists = bool(
        await connection.fetchval("SELECT to_regclass('auth.users') IS NOT NULL")
    )
    public_table_count = int(
        await connection.fetchval(
            """
            SELECT count(*)
            FROM pg_class AS relation
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = 'public' AND relation.relkind IN ('r', 'p')
            """
        )
    )
    public_function_count = int(
        await connection.fetchval(
            """
            SELECT count(*)
            FROM pg_proc AS function_record
            JOIN pg_namespace AS namespace ON namespace.oid = function_record.pronamespace
            WHERE namespace.nspname = 'public'
            """
        )
    )
    migrations_exist = bool(
        await connection.fetchval(
            """SELECT to_regclass('public."_prisma_migrations"') IS NOT NULL"""
        )
    )
    migration_rows = (
        await connection.fetch(
            """
            SELECT migration_name
            FROM public."_prisma_migrations"
            WHERE finished_at IS NOT NULL AND rolled_back_at IS NULL
            ORDER BY migration_name
            """
        )
        if migrations_exist
        else []
    )
    return StagingCatalogSnapshot(
        server_version_num=server_version_num,
        transaction_read_only=transaction_read_only,
        roles=frozenset(str(row["rolname"]) for row in role_rows),
        auth_users_exists=auth_users_exists,
        public_table_count=public_table_count,
        public_function_count=public_function_count,
        applied_migrations=frozenset(str(row["migration_name"]) for row in migration_rows),
    )


async def inspect_staging_target(
    connection: asyncpg.Connection,
    target: StagingTarget,
    *,
    require_v5_migrations: bool,
) -> dict[str, object]:
    return evaluate_staging_catalog(
        await collect_staging_catalog_snapshot(connection),
        target,
        require_v5_migrations=require_v5_migrations,
    )
