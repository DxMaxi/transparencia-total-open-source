"""Converte um URL PostgreSQL em variáveis libpq sem expor credenciais em argumentos.

O ``pg_dump`` executado dentro de Docker recebe estas variáveis através de um
``--env-file`` ligado por pipe. O URL completo não é colocado na linha de
comandos, num ficheiro temporário ou nos registos da workflow.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, unquote, urlsplit


class PostgresBackupConnectionError(ValueError):
    """Indica um URL de backup ausente, ambíguo ou inseguro para exportação."""


_QUERY_ENVIRONMENT = {
    "application_name": "PGAPPNAME",
    "channel_binding": "PGCHANNELBINDING",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "gssencmode": "PGGSSENCMODE",
    "hostaddr": "PGHOSTADDR",
    "load_balance_hosts": "PGLOADBALANCEHOSTS",
    "options": "PGOPTIONS",
    "require_auth": "PGREQUIREAUTH",
    "sslcert": "PGSSLCERT",
    "sslcrl": "PGSSLCRL",
    "sslcrldir": "PGSSLCRLDIR",
    "sslkey": "PGSSLKEY",
    "sslmode": "PGSSLMODE",
    "sslnegotiation": "PGSSLNEGOTIATION",
    "sslrootcert": "PGSSLROOTCERT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
}


def _safe_env_value(value: str, *, field: str) -> str:
    if not value:
        raise PostgresBackupConnectionError(f"{field} não pode ficar vazio")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise PostgresBackupConnectionError(f"{field} contém separadores proibidos")
    return value


def postgres_environment_from_url(database_url: str) -> dict[str, str]:
    """Devolve parâmetros libpq explícitos para um único URL PostgreSQL.

    Parâmetros desconhecidos são rejeitados. Assim, a cópia nunca ignora em
    silêncio uma opção de ligação que possa alterar o servidor ou a segurança.
    ``schema=public`` é aceite mas não exportado: o âmbito é imposto pelo
    argumento fixo ``--schema=public`` da workflow.
    """

    raw_url = database_url.strip()
    if not raw_url:
        raise PostgresBackupConnectionError("DATABASE_URL não configurada")

    parsed = urlsplit(raw_url)
    if parsed.scheme.casefold() not in {"postgres", "postgresql"}:
        raise PostgresBackupConnectionError("DATABASE_URL deve usar postgres ou postgresql")
    if parsed.fragment:
        raise PostgresBackupConnectionError("DATABASE_URL não pode conter fragmento")
    try:
        port = parsed.port or 5432
    except ValueError as exc:
        raise PostgresBackupConnectionError("porta PostgreSQL inválida") from exc

    environment = {
        "PGHOST": _safe_env_value(parsed.hostname or "", field="host"),
        "PGPORT": str(port),
        "PGUSER": _safe_env_value(unquote(parsed.username or ""), field="utilizador"),
        "PGPASSWORD": _safe_env_value(unquote(parsed.password or ""), field="palavra-passe"),
        "PGDATABASE": _safe_env_value(
            unquote(parsed.path.removeprefix("/")), field="base de dados"
        ),
    }

    seen_query: set[str] = set()
    seen_query_environment: set[str] = set()
    try:
        query_items = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise PostgresBackupConnectionError("parâmetros PostgreSQL inválidos") from exc

    for raw_key, raw_value in query_items:
        key = raw_key.casefold()
        if key in seen_query:
            raise PostgresBackupConnectionError(f"parâmetro PostgreSQL repetido: {key}")
        seen_query.add(key)

        if key == "schema":
            if raw_value not in {"", "public"}:
                raise PostgresBackupConnectionError("o backup só aceita schema=public")
            continue
        if key == "ssl" and raw_value.casefold() == "true":
            if "PGSSLMODE" in seen_query_environment:
                raise PostgresBackupConnectionError("opções SSL contraditórias")
            environment["PGSSLMODE"] = "require"
            seen_query_environment.add("PGSSLMODE")
            continue

        env_name = _QUERY_ENVIRONMENT.get(key)
        if env_name is None:
            raise PostgresBackupConnectionError(
                f"parâmetro PostgreSQL não suportado no backup: {key}"
            )
        if env_name in seen_query_environment:
            raise PostgresBackupConnectionError(f"opção PostgreSQL contraditória: {key}")
        environment[env_name] = _safe_env_value(raw_value, field=key)
        seen_query_environment.add(env_name)

    return environment


def docker_env_file_text(environment: dict[str, str]) -> str:
    """Serializa variáveis já validadas no formato aceite por ``docker --env-file``."""

    return "".join(f"{name}={value}\n" for name, value in sorted(environment.items()))
