import asyncio
from typing import Any

from app.repositories.postgres import PostgresRepository


class DeactivationConnection:
    def __init__(self, result: int) -> None:
        self.result = result
        self.query = ""
        self.arguments: tuple[Any, ...] = ()

    async def fetchval(self, query: str, *arguments: object) -> int:
        self.query = query
        self.arguments = arguments
        return self.result


def test_deactivates_only_people_missing_from_same_legislature_snapshot() -> None:
    connection = DeactivationConnection(1_160)

    result = asyncio.run(
        PostgresRepository._deactivate_stale_parliament_people(
            connection,  # type: ignore[arg-type]
            legislature="XVII",
            incoming_source_ids=["101", "102"],
        )
    )

    assert result == 1_160
    assert connection.arguments == ("XVII", ["101", "102"])
    assert "snapshot.legislature = $1" in connection.query
    assert "person.source_id <> ALL($2::text[])" in connection.query
    assert "source.publisher = 'PARLIAMENT'" in connection.query
    assert "SET active = FALSE" in connection.query
