from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.models.ept_declaration import EptPublicInterestObservationInput
from app.repositories.ept_declaration_staging import EptDeclarationStagingRepository


class Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class Connection:
    def __init__(self, *, source_url: str = "https://entidadetransparencia.pt/registo/DU-42"):
        self.source_url = source_url
        self.arguments: list[tuple[object, ...]] = []
        self.commands: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> Transaction:
        return Transaction()

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any] | None:
        self.arguments.append(arguments)
        if "FROM source_documents AS source" in query:
            return {
                "id": "source-ept-1",
                "publisher": "TRANSPARENCY_ENTITY",
                "kind": "DECLARATION",
                "title": "Registo público de interesses",
                "official_identifier": "DU-42",
                "url": self.source_url,
                "retrieved_at": datetime(2026, 8, 28, tzinfo=UTC),
                "content_sha256": "a" * 64,
                "archive_id": "archive-1",
                "attestation_sha256": "b" * 64,
            }
        return None

    async def fetchval(self, query: str, *arguments: object) -> bool:
        self.arguments.append(arguments)
        assert "INSERT INTO ept_public_interest_observations" in query
        return True

    async def execute(self, query: str, *arguments: object) -> None:
        self.commands.append((query, arguments))


class Acquire(AbstractAsyncContextManager[Connection]):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> Connection:
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class Pool:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def acquire(self) -> Acquire:
        return Acquire(self.connection)


def _payload() -> EptPublicInterestObservationInput:
    return EptPublicInterestObservationInput(
        source_document_id="source-ept-1",
        official_declaration_id="DU-42",
        official_subject_identifier=SecretStr("titular-ept-42"),
        public_subject_name="Pessoa Titular",
        declared_at=datetime(2026, 7, 1, tzinfo=UTC),
        period_label="2026",
        confirm_public_interest_register_only=True,
        confirm_no_income_or_asset_content=True,
        confirm_no_protected_identifiers_persisted=True,
        confirm_private_only=True,
    )


@pytest.mark.asyncio
async def test_staging_hashes_subject_and_creates_no_public_projection() -> None:
    connection = Connection()
    settings = Settings(
        environment="test",
        protected_identifier_pepper=SecretStr("p" * 32),
    )
    result = await EptDeclarationStagingRepository(
        Pool(connection),  # type: ignore[arg-type]
        settings,
    ).stage_observation(payload=_payload(), actor_alias="operador-ept")

    serialized_arguments = repr(connection.arguments)
    assert "titular-ept-42" not in serialized_arguments
    assert result["created"] is True
    assert result["publication_performed"] is False
    assert result["person_link_created"] is False
    assert result["protected_identifier_persisted_in_clear"] is False
    assert len(str(result["source_record_sha256"])) == 64
    audit = next(command for command in connection.commands if "audit_events" in command[0])
    assert "STAGED_PRIVATE" in audit[0]
    assert "titular-ept-42" not in repr(audit)


@pytest.mark.asyncio
async def test_staging_requires_durable_pepper_before_database_access() -> None:
    connection = Connection()
    with pytest.raises(ValueError, match="PROTECTED_IDENTIFIER_PEPPER"):
        await EptDeclarationStagingRepository(
            Pool(connection),  # type: ignore[arg-type]
            Settings(environment="test"),
        ).stage_observation(payload=_payload(), actor_alias="operador-ept")

    assert connection.arguments == []
    assert connection.commands == []


@pytest.mark.asyncio
async def test_staging_rejects_general_portal_as_individual_proof() -> None:
    connection = Connection(source_url="https://entidadetransparencia.pt/")
    with pytest.raises(ValueError, match="portal geral"):
        await EptDeclarationStagingRepository(
            Pool(connection),  # type: ignore[arg-type]
            Settings(
                environment="test",
                protected_identifier_pepper=SecretStr("p" * 32),
            ),
        ).stage_observation(payload=_payload(), actor_alias="operador-ept")

    assert connection.commands == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_url",
    [
        "https://example.org/registo/DU-42",
        "https://entidadetransparencia.pt/?declaracao=DU-42",
        "https://www.tribunalconstitucional.pt/tc/ept/?declaracao=DU-42",
    ],
)
async def test_staging_rejects_non_individual_or_non_official_url(source_url: str) -> None:
    connection = Connection(source_url=source_url)
    with pytest.raises(ValueError, match="prova EPT individual"):
        await EptDeclarationStagingRepository(
            Pool(connection),  # type: ignore[arg-type]
            Settings(
                environment="test",
                protected_identifier_pepper=SecretStr("p" * 32),
            ),
        ).stage_observation(payload=_payload(), actor_alias="operador-ept")

    assert connection.commands == []
