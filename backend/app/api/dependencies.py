from typing import cast

from fastapi import Request

from app.repositories.postgres import PostgresRepository


def get_repository(request: Request) -> PostgresRepository:
    return cast(PostgresRepository, request.app.state.repository)
