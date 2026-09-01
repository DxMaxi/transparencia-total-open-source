from typing import Final

import asyncpg

_UNCONFIGURED_DATABASE_MESSAGE: Final = "Base de dados não configurada"

PUBLIC_DATABASE_BOUNDARY_ERRORS = (
    RuntimeError,
    OSError,
    TimeoutError,
    asyncpg.PostgresConnectionError,
    asyncpg.CannotConnectNowError,
    asyncpg.TooManyConnectionsError,
    asyncpg.AdminShutdownError,
    asyncpg.CrashShutdownError,
    asyncpg.IdleSessionTimeoutError,
    asyncpg.QueryCanceledError,
    asyncpg.UndefinedTableError,
    asyncpg.UndefinedColumnError,
    asyncpg.InvalidSchemaNameError,
)


def is_public_database_unavailable(exc: BaseException) -> bool:
    """Distingue indisponibilidade prevista de defeitos de SQL ou programação."""

    if isinstance(exc, RuntimeError):
        return str(exc) == _UNCONFIGURED_DATABASE_MESSAGE
    return isinstance(exc, PUBLIC_DATABASE_BOUNDARY_ERRORS[1:])
