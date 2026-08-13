"""Inspeção estrutural, read-only, da fundação editorial num PostgreSQL Supabase."""

from dataclasses import dataclass

import asyncpg

EDITORIAL_TABLES = (
    "staff_profiles",
    "editorial_cases",
    "editorial_versions",
    "editorial_decisions",
    "editorial_publication_events",
)

EDITORIAL_FUNCTION_SEARCH_PATHS = {
    "validate_editorial_case_insert": "search_path=pg_catalog, public",
    "validate_editorial_version_insert": "search_path=pg_catalog, public",
    "validate_editorial_decision_insert": "search_path=pg_catalog, public",
    "protect_editorial_case_projection": "search_path=pg_catalog, public",
    "reject_editorial_history_mutation": "search_path=pg_catalog",
    "validate_editorial_publication_event_insert": "search_path=pg_catalog, public",
    "require_editorial_publication_event": "search_path=pg_catalog, public",
}

EDITORIAL_TRIGGERS = (
    "editorial_cases_validate_insert",
    "editorial_versions_validate_insert",
    "editorial_versions_append_only",
    "editorial_decisions_validate_insert",
    "editorial_decisions_append_only",
    "editorial_cases_protect_projection",
    "editorial_publication_events_validate_insert",
    "editorial_publication_events_append_only",
    "editorial_cases_require_publication_event",
)

REQUIRED_V5_MIGRATIONS = (
    "20260811110000_v5_editorial_foundation",
    "20260811133000_v5_editorial_withdrawal_cycle",
)

MANUAL_AUTH_GATES = (
    "Confirmar no dashboard que o registo público está desativado.",
    "Confirmar URL do site e redirect /auth/confirmar exatos, sem wildcard amplo.",
    "Confirmar que um JWT real usa RS256 ou ES256 e é aceite pelo backend.",
    "Confirmar que uma sessão aal1 não entra nas rotas editoriais.",
    "Confirmar TOTP e acesso aal2 com uma conta ADMIN convidada.",
)


@dataclass(slots=True)
class EditorialDatabaseSnapshot:
    server_version_num: int
    roles: frozenset[str]
    role_privileges: dict[str, frozenset[str]]
    auth_users_exists: bool
    table_rls: dict[str, bool]
    policy_count: int
    roles_with_schema_usage: frozenset[str]
    table_privileges: frozenset[str]
    function_search_paths: dict[str, frozenset[str]]
    function_privileges: frozenset[str]
    enabled_triggers: frozenset[str]
    auth_fk_target: str | None
    auth_fk_delete: str | None
    auth_fk_update: str | None
    migrations: frozenset[str]
    active_staff_counts: dict[str, int]


def _check(code: str, ok: bool, success: str, failure: str) -> dict[str, object]:
    return {"code": code, "ok": ok, "detail": success if ok else failure}


def evaluate_editorial_staging_snapshot(
    snapshot: EditorialDatabaseSnapshot,
) -> dict[str, object]:
    """Avalia a prova estrutural sem transformar verificações manuais em sucesso automático."""

    expected_roles = frozenset({"anon", "authenticated"})
    expected_tables = frozenset(EDITORIAL_TABLES)
    expected_functions = frozenset(EDITORIAL_FUNCTION_SEARCH_PATHS)
    expected_triggers = frozenset(EDITORIAL_TRIGGERS)
    expected_migrations = frozenset(REQUIRED_V5_MIGRATIONS)

    browser_roles_are_unprivileged = all(
        role in snapshot.roles and not snapshot.role_privileges.get(role) for role in expected_roles
    )
    search_paths_ok = all(
        expected in snapshot.function_search_paths.get(function_name, frozenset())
        for function_name, expected in EDITORIAL_FUNCTION_SEARCH_PATHS.items()
    )
    checks = [
        _check(
            "postgres_17",
            snapshot.server_version_num >= 170000,
            "PostgreSQL 17 ou superior confirmado.",
            "A base não executa PostgreSQL 17 ou superior.",
        ),
        _check(
            "supabase_roles",
            expected_roles.issubset(snapshot.roles),
            "Papéis anon e authenticated existem.",
            "Faltam papéis esperados do Supabase.",
        ),
        _check(
            "browser_roles_unprivileged",
            browser_roles_are_unprivileged,
            "anon e authenticated não têm login nem capacidades administrativas.",
            "Um papel browser tem login, BYPASSRLS ou outra capacidade administrativa.",
        ),
        _check(
            "auth_users",
            snapshot.auth_users_exists,
            "auth.users existe.",
            "auth.users não existe.",
        ),
        _check(
            "editorial_tables",
            expected_tables == frozenset(snapshot.table_rls),
            "As cinco tabelas editoriais existem.",
            "O conjunto de tabelas editoriais está incompleto.",
        ),
        _check(
            "editorial_rls",
            expected_tables == frozenset(snapshot.table_rls) and all(snapshot.table_rls.values()),
            "RLS está ativa em todas as tabelas editoriais.",
            "Existe uma tabela editorial sem RLS ativa.",
        ),
        _check(
            "no_browser_policies",
            snapshot.policy_count == 0,
            "Não existem políticas de acesso browser às tabelas editoriais.",
            "Existem políticas RLS inesperadas nas tabelas editoriais.",
        ),
        _check(
            "no_browser_schema_usage",
            not snapshot.roles_with_schema_usage,
            "anon e authenticated não têm USAGE no esquema public.",
            "Um papel browser tem USAGE no esquema public.",
        ),
        _check(
            "no_browser_table_privileges",
            not snapshot.table_privileges,
            "anon e authenticated não têm privilégios efetivos nas tabelas editoriais.",
            "Um papel browser tem privilégios efetivos numa tabela editorial.",
        ),
        _check(
            "function_search_paths",
            expected_functions == frozenset(snapshot.function_search_paths) and search_paths_ok,
            "As funções editoriais têm search_path mínimo fixo.",
            "Existe uma função editorial ausente ou com search_path inseguro.",
        ),
        _check(
            "no_browser_function_privileges",
            not snapshot.function_privileges,
            "anon e authenticated não podem executar funções editoriais.",
            "Um papel browser pode executar uma função editorial.",
        ),
        _check(
            "editorial_triggers",
            expected_triggers == snapshot.enabled_triggers,
            "Todos os triggers editoriais obrigatórios estão ativos.",
            "Existe um trigger editorial ausente ou desativado.",
        ),
        _check(
            "staff_auth_fk",
            snapshot.auth_fk_target == "auth.users"
            and snapshot.auth_fk_delete == "r"
            and snapshot.auth_fk_update == "c",
            "staff_profiles está ligado a auth.users com DELETE RESTRICT.",
            "A ligação entre staff_profiles e auth.users não corresponde ao contrato.",
        ),
        _check(
            "v5_migrations",
            expected_migrations.issubset(snapshot.migrations),
            "As migrações editoriais V5 obrigatórias estão aplicadas.",
            "Falta uma migração editorial V5 obrigatória.",
        ),
        _check(
            "active_admin",
            snapshot.active_staff_counts.get("ADMIN", 0) >= 1,
            "Existe pelo menos uma conta ADMIN ativa.",
            "Ainda não existe uma conta ADMIN ativa.",
        ),
    ]

    return {
        "database_ready": all(bool(check["ok"]) for check in checks),
        "checks": checks,
        "active_staff_counts": {
            "ADMIN": snapshot.active_staff_counts.get("ADMIN", 0),
            "REVIEWER": snapshot.active_staff_counts.get("REVIEWER", 0),
        },
        "manual_auth_gates": list(MANUAL_AUTH_GATES),
        "scope": "A inspeção prova apenas estrutura PostgreSQL e nunca configura o Supabase Auth.",
    }


async def collect_editorial_database_snapshot(
    connection: asyncpg.Connection,
) -> EditorialDatabaseSnapshot:
    """Recolhe apenas catálogo, privilégios e contagens; não lê conteúdo editorial."""

    server_version_num = int(await connection.fetchval("SHOW server_version_num"))
    role_rows = await connection.fetch(
        """
        SELECT rolname,
               rolcanlogin,
               rolsuper,
               rolcreatedb,
               rolcreaterole,
               rolreplication,
               rolbypassrls
        FROM pg_roles
        WHERE rolname = ANY($1::text[])
        ORDER BY rolname
        """,
        ["anon", "authenticated"],
    )
    roles = frozenset(str(row["rolname"]) for row in role_rows)
    role_privileges = {
        str(row["rolname"]): frozenset(
            privilege
            for privilege, enabled in (
                ("LOGIN", row["rolcanlogin"]),
                ("SUPERUSER", row["rolsuper"]),
                ("CREATEDB", row["rolcreatedb"]),
                ("CREATEROLE", row["rolcreaterole"]),
                ("REPLICATION", row["rolreplication"]),
                ("BYPASSRLS", row["rolbypassrls"]),
            )
            if bool(enabled)
        )
        for row in role_rows
    }

    table_rows = await connection.fetch(
        """
        SELECT c.relname, c.relrowsecurity
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND c.relname = ANY($1::text[])
        ORDER BY c.relname
        """,
        list(EDITORIAL_TABLES),
    )
    table_rls = {str(row["relname"]): bool(row["relrowsecurity"]) for row in table_rows}
    policy_count = int(
        await connection.fetchval(
            """
            SELECT count(*)
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = ANY($1::text[])
            """,
            list(EDITORIAL_TABLES),
        )
    )

    roles_with_schema_usage: set[str] = set()
    table_privileges: set[str] = set()
    for role in sorted(roles):
        if await connection.fetchval("SELECT has_schema_privilege($1, 'public', 'USAGE')", role):
            roles_with_schema_usage.add(role)
        privileged_tables = await connection.fetch(
            """
            SELECT c.relname
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname = ANY($2::text[])
              AND (
                has_table_privilege($1, c.oid, 'SELECT')
                OR has_table_privilege($1, c.oid, 'INSERT')
                OR has_table_privilege($1, c.oid, 'UPDATE')
                OR has_table_privilege($1, c.oid, 'DELETE')
                OR has_table_privilege($1, c.oid, 'TRUNCATE')
                OR has_table_privilege($1, c.oid, 'REFERENCES')
                OR has_table_privilege($1, c.oid, 'TRIGGER')
              )
            ORDER BY c.relname
            """,
            role,
            list(EDITORIAL_TABLES),
        )
        table_privileges.update(f"{role}:{row['relname']}" for row in privileged_tables)

    function_rows = await connection.fetch(
        """
        SELECT p.oid, p.proname, p.proconfig
        FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = ANY($1::text[])
        ORDER BY p.proname
        """,
        list(EDITORIAL_FUNCTION_SEARCH_PATHS),
    )
    function_search_paths = {
        str(row["proname"]): frozenset(str(value) for value in (row["proconfig"] or []))
        for row in function_rows
    }
    function_privileges: set[str] = set()
    for role in sorted(roles):
        for row in function_rows:
            if await connection.fetchval(
                "SELECT has_function_privilege($1, $2::oid, 'EXECUTE')",
                role,
                row["oid"],
            ):
                function_privileges.add(f"{role}:{row['proname']}")

    trigger_rows = await connection.fetch(
        """
        SELECT t.tgname, t.tgenabled
        FROM pg_trigger AS t
        JOIN pg_class AS c ON c.oid = t.tgrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND NOT t.tgisinternal
          AND t.tgname = ANY($1::text[])
        ORDER BY t.tgname
        """,
        list(EDITORIAL_TRIGGERS),
    )
    enabled_triggers = frozenset(
        str(row["tgname"]) for row in trigger_rows if str(row["tgenabled"]) != "D"
    )

    auth_users_exists = bool(
        await connection.fetchval("SELECT to_regclass('auth.users') IS NOT NULL")
    )
    auth_fk = await connection.fetchrow(
        """
        SELECT target_namespace.nspname AS target_schema,
               target.relname AS target_table,
               constraint_record.confdeltype,
               constraint_record.confupdtype
        FROM pg_constraint AS constraint_record
        JOIN pg_class AS source ON source.oid = constraint_record.conrelid
        JOIN pg_namespace AS source_namespace ON source_namespace.oid = source.relnamespace
        JOIN pg_class AS target ON target.oid = constraint_record.confrelid
        JOIN pg_namespace AS target_namespace ON target_namespace.oid = target.relnamespace
        WHERE constraint_record.contype = 'f'
          AND constraint_record.conname = 'staff_profiles_auth_user_id_fkey'
          AND source_namespace.nspname = 'public'
          AND source.relname = 'staff_profiles'
        """
    )

    migration_rows = await connection.fetch(
        """
        SELECT migration_name
        FROM public."_prisma_migrations"
        WHERE migration_name = ANY($1::text[])
          AND finished_at IS NOT NULL
          AND rolled_back_at IS NULL
        ORDER BY migration_name
        """,
        list(REQUIRED_V5_MIGRATIONS),
    )
    staff_rows = await connection.fetch(
        """
        SELECT role::text AS role, count(*) AS count
        FROM public.staff_profiles
        WHERE active = TRUE
        GROUP BY role
        ORDER BY role
        """
    )

    return EditorialDatabaseSnapshot(
        server_version_num=server_version_num,
        roles=roles,
        role_privileges=role_privileges,
        auth_users_exists=auth_users_exists,
        table_rls=table_rls,
        policy_count=policy_count,
        roles_with_schema_usage=frozenset(roles_with_schema_usage),
        table_privileges=frozenset(table_privileges),
        function_search_paths=function_search_paths,
        function_privileges=frozenset(function_privileges),
        enabled_triggers=enabled_triggers,
        auth_fk_target=(
            f"{auth_fk['target_schema']}.{auth_fk['target_table']}" if auth_fk else None
        ),
        auth_fk_delete=str(auth_fk["confdeltype"]) if auth_fk else None,
        auth_fk_update=str(auth_fk["confupdtype"]) if auth_fk else None,
        migrations=frozenset(str(row["migration_name"]) for row in migration_rows),
        active_staff_counts={str(row["role"]): int(row["count"]) for row in staff_rows},
    )


async def inspect_editorial_staging_readiness(
    connection: asyncpg.Connection,
) -> dict[str, object]:
    return evaluate_editorial_staging_snapshot(
        await collect_editorial_database_snapshot(connection)
    )
