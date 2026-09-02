"""Contrato de privacidade e prova independente da identidade organizacional V5.52."""

import json
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.security import hmac_protected_identifier
from app.models.base_organisation import (
    BaseOrganisationIdentityEditorialProposalRequest,
    BaseOrganisationIdentityObservationInput,
    safe_registry_record_id,
    safe_registry_text,
)
from app.repositories.base_organisation_editorial import (
    BaseOrganisationEditorialRepository,
    _validate_projection,
)
from app.repositories.base_organisation_staging import BaseOrganisationStagingRepository
from app.repositories.editorial import EditorialSourceError
from app.services.base_organisation_identity import (
    PARSER_VERSION,
    POLICY_VERSION,
    canonical_json,
    observation_sha256,
    proposal_confirmation_sha256,
    sha256,
    source_proof,
    source_record,
)
from scripts import stage_base_organisation_identity as command

_RAW = "501234567"
_PEPPER = "test-only-durable-pepper-not-production" * 2
_NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)
_OBSERVATION_ID = "base_org_identity_" + "ab" * 16


def _payload(**overrides: Any) -> BaseOrganisationIdentityObservationInput:
    values = {
        "source_document_id": "source_registry_fixture",
        "registry_record_id": "AP-1-2026",
        "legal_name": "Organização de teste independente",
        "kind": "COMPANY",
        "fiscal_identifier": SecretStr(_RAW),
        "confirm_independent_official_source": True,
        "confirm_identifier_hmac_only": True,
        "confirm_private_identity_only": True,
        "confirm_no_publication": True,
    }
    return BaseOrganisationIdentityObservationInput.model_validate(values | overrides)


def _source() -> dict[str, Any]:
    return {
        "source_document_id": "source_registry_fixture",
        "source_publisher": "JUSTICE_REGISTRY",
        "source_kind": "ORGANISATION_REGISTRY",
        "source_title": "Publicação de ato de registo de entidade — teste",
        "source_official_identifier": "AP-1-2026",
        "source_url": "https://publicacoes.mj.pt/DetalhePublicacao.aspx",
        "source_retrieved_at": _NOW,
        "source_sha256": "a" * 64,
        "source_mime_type": "text/html",
        "attestation_sha256": "c" * 64,
    }


def _row() -> dict[str, Any]:
    source = _source()
    record_hash = sha256(
        source_record(
            source_document_id=source["source_document_id"],
            registry_record_id="AP-1-2026",
            legal_name="Organização de teste independente",
            kind="COMPANY",
            source=source_proof(source, "AP-1-2026"),
        )
    )
    digest = hmac_protected_identifier(_RAW, _PEPPER)
    return source | {
        "observation_id": _OBSERVATION_ID,
        "registry_record_id": "AP-1-2026",
        "legal_name": "Organização de teste independente",
        "organisation_kind": "COMPANY",
        "identifier_scheme": "PORTUGUESE_FISCAL_IDENTIFIER",
        "protected_identifier_digest": digest,
        "identity_scope": "ORGANISATION_IDENTITY_ONLY",
        "link_status": "UNLINKED_PRIVATE",
        "publication_eligible": False,
        "source_record_sha256": record_hash,
        "observation_sha256": observation_sha256(record_hash, digest),
        "observed_at": _NOW,
        "parser_version": PARSER_VERSION,
        "policy_version": POLICY_VERSION,
        "storage_backend": "ENCRYPTED_TEST_ARCHIVE",
        "byte_size": 128,
        "archived_at": _NOW,
        "case_id": None,
        "case_state": None,
        "case_revision": None,
        "case_origin": None,
    }


@pytest.mark.parametrize(
    "value",
    [
        "NIPC 501234567",
        "AP501234567Z",
        "Empresa 501 234 567",
        "Empresa ５０１２３４５６７",
        "Empresa ٥٠١٢٣٤٥٦٧",
        "5_0_1_2_3_4_5_6_7",
        "a" * 64,
        "aa-" * 32,
        "Texto\u200boculto",
        "Nome\ncom controlo",
    ],
)
def test_metadata_rejects_raw_fiscal_or_digest_or_hidden_text(value: str) -> None:
    with pytest.raises(ValueError):
        safe_registry_text(value)


@pytest.mark.parametrize("value", ["501234567", "AP-501-234-567", "AP501234567Z"])
def test_record_locator_cannot_be_a_fiscal_identifier(value: str) -> None:
    with pytest.raises(ValueError):
        safe_registry_record_id(value)


def test_secret_is_excluded_from_representation_and_serialization() -> None:
    payload = _payload()
    assert _RAW not in str(payload)
    assert _RAW not in repr(payload)
    assert "fiscal_identifier" not in payload.model_dump()
    assert _RAW not in payload.model_dump_json()
    assert (
        _payload(
            fiscal_identifier=SecretStr("５０１ ２３４-５６７")
        ).fiscal_identifier.get_secret_value()
        == _RAW
    )
    with pytest.raises(ValidationError) as error:
        _payload(fiscal_identifier=SecretStr("PT" + _RAW))
    assert _RAW not in str(error.value)


@pytest.mark.parametrize(
    "field",
    [
        "fiscal_identifier",
        "protected_identifier_digest",
        "observation_sha256",
        "legal_name",
        "source_document_id",
        "nipc",
    ],
)
def test_http_proposal_rejects_all_additional_identity_fields(field: str) -> None:
    payload = {
        "observation_id": _OBSERVATION_ID,
        "source_record_sha256": "a" * 64,
        "proposal_confirmation_sha256": "b" * 64,
        "confirm_independent_official_source": True,
        "confirm_private_identity_only": True,
        "confirm_no_publication": True,
        field: _RAW,
    }
    with pytest.raises(ValidationError):
        BaseOrganisationIdentityEditorialProposalRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_publisher", "BASE_GOV"),
        ("source_publisher", "OTHER_OFFICIAL"),
        ("source_kind", "OPEN_DATASET"),
        ("source_official_identifier", "AP-2-2026"),
        ("source_url", "https://publicacoes.mj.pt/pesquisa.aspx"),
        ("source_url", "https://publicacoes.mj.pt/DetalhePublicacao.aspx?id=123"),
        ("source_url", "https://publicacoes.mj.pt.evil.test/DetalhePublicacao.aspx"),
        ("source_title", "Organização " + _RAW),
        ("source_mime_type", "application/json"),
    ],
)
def test_source_requires_independent_safe_individual_record(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        source_proof(_source() | {field: value}, "AP-1-2026")


def test_candidate_and_normalized_proposal_have_no_internal_identifier_proof() -> None:
    row = _row()
    candidate = BaseOrganisationEditorialRepository._candidate(row)
    normalized = BaseOrganisationEditorialRepository._normalized_proposal(candidate)
    assert candidate["proposal_eligible"] is True
    assert _validate_projection(normalized) == normalized
    serialized = canonical_json({"candidate": candidate, "normalized": normalized})
    for forbidden in (_RAW, row["protected_identifier_digest"], row["observation_sha256"]):
        assert forbidden not in serialized
    assert "protected_identifier_digest" not in serialized
    assert "observation_sha256" not in serialized
    assert normalized["review_constraints"]["approval_is_not_publication"] is True
    assert candidate["protected_identifier_exposed"] is False


@pytest.mark.parametrize("part", ["candidate", "source", "archive", "review_constraints"])
def test_projection_is_closed_even_under_digest_looking_keys(part: str) -> None:
    candidate = BaseOrganisationEditorialRepository._candidate(_row())
    normalized = BaseOrganisationEditorialRepository._normalized_proposal(candidate)
    normalized[part]["private_hmac"] = "d" * 64
    with pytest.raises(ValueError):
        _validate_projection(normalized)


def test_external_confirmation_is_bound_to_source_and_observation_not_hmac() -> None:
    row = _row()
    first = BaseOrganisationEditorialRepository._candidate(row)
    changed_private = dict(row)
    changed_private["protected_identifier_digest"] = "d" * 64
    changed_private["observation_sha256"] = observation_sha256(
        row["source_record_sha256"],
        "d" * 64,
    )
    second = BaseOrganisationEditorialRepository._candidate(changed_private)
    assert first["source_record_sha256"] == second["source_record_sha256"]
    assert first["proposal_confirmation_sha256"] == second["proposal_confirmation_sha256"]
    changed_observation = row | {"observation_id": "base_org_identity_" + "cd" * 16}
    third = BaseOrganisationEditorialRepository._candidate(changed_observation)
    assert first["proposal_confirmation_sha256"] != third["proposal_confirmation_sha256"]
    assert (
        proposal_confirmation_sha256(
            observation_id=_OBSERVATION_ID,
            source_document_id="different_source",
            source_content_sha256="a" * 64,
            source_record_sha256=row["source_record_sha256"],
            archive_attestation_sha256="c" * 64,
        )
        != first["proposal_confirmation_sha256"]
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha256", "e" * 64),
        ("observation_sha256", "f" * 64),
        ("protected_identifier_digest", "e" * 64),
        ("source_record_sha256", "c" * 64),
        ("parser_version", "different-parser"),
        ("policy_version", "different-policy"),
        ("identity_scope", "PUBLIC"),
        ("publication_eligible", True),
        ("storage_backend", None),
    ],
)
def test_changed_proof_or_archive_blocks_submission(field: str, value: object) -> None:
    candidate = BaseOrganisationEditorialRepository._candidate(_row() | {field: value})
    assert candidate["proposal_eligible"] is False
    assert candidate["blocked_reasons"]


def test_unsafe_mutated_source_is_never_reflected_as_candidate() -> None:
    with pytest.raises(EditorialSourceError) as error:
        BaseOrganisationEditorialRepository._candidate(_row() | {"source_title": _RAW})
    assert _RAW not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("environment", "pepper"),
    [
        ("production", SecretStr(_PEPPER)),
        ("development", SecretStr(_PEPPER)),
        ("test", None),
    ],
)
async def test_preflight_rejects_before_any_database_access(
    environment: str,
    pepper: SecretStr | None,
) -> None:
    pool = MagicMock()
    settings = Settings(_env_file=None, environment=environment, protected_identifier_pepper=pepper)
    repository = BaseOrganisationStagingRepository(pool, settings)
    with pytest.raises(ValueError):
        await repository.stage_observation(payload=_payload(), actor_alias="operador-teste")
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_unfiltered_queue_does_not_read_database() -> None:
    pool = MagicMock()
    result = await BaseOrganisationEditorialRepository(pool).list_candidates(
        query=None,
        limit=20,
        offset=0,
    )
    assert result["filter_required"] is True
    assert result["items"] == []
    pool.fetch.assert_not_called()
    pool.fetchval.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        _RAW,
        "A1B2C3D4E5F6G7H8I9",
        "٥٠١٢٣٤٥٦٧",
        "aa-" * 32,
        "b" * 64,
    ],
)
async def test_queue_rejects_protected_search_before_database(query: str) -> None:
    pool = MagicMock()
    with pytest.raises(EditorialSourceError):
        await BaseOrganisationEditorialRepository(pool).list_candidates(
            query=query,
            limit=20,
            offset=0,
        )
    pool.fetch.assert_not_called()
    pool.fetchval.assert_not_called()


class _Connection(AbstractAsyncContextManager):
    def __init__(self) -> None:
        self.source = _source()
        self.inserted: tuple[Any, ...] | None = None
        self.events: list[tuple[str, tuple[Any, ...]]] = []
        self.error = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def transaction(self):
        return self

    async def execute(self, sql, *args):
        self.events.append((sql, args))
        return "SELECT 1"

    async def fetchrow(self, sql, *args):
        if "FROM source_documents AS source" in sql:
            return self.source
        if self.inserted:
            return {
                "id": self.inserted[0],
                "source_record_sha256": self.inserted[6],
                "observation_sha256": self.inserted[7],
            }
        return None

    async def fetchval(self, sql, *args):
        if self.error:
            raise asyncpg.CheckViolationError("sensitive driver detail " + _RAW)
        if self.inserted is not None:
            return None
        self.inserted = args
        return args[0]


def _staging(connection: _Connection) -> BaseOrganisationStagingRepository:
    pool = MagicMock()
    pool.acquire.return_value = connection
    return BaseOrganisationStagingRepository(
        pool,
        Settings(
            _env_file=None,
            environment="test",
            protected_identifier_pepper=SecretStr(_PEPPER),
        ),
    )


@pytest.mark.asyncio
async def test_staging_is_idempotent_and_audit_never_contains_hmac() -> None:
    connection = _Connection()
    repository = _staging(connection)
    first = await repository.stage_observation(payload=_payload(), actor_alias="operador-teste")
    second = await repository.stage_observation(payload=_payload(), actor_alias="operador-teste")
    assert first["created"] is True and second["created"] is False
    assert first["observation_id"] == second["observation_id"]
    audits = [args for sql, args in connection.events if "INSERT INTO audit_events" in sql]
    assert len(audits) == 1
    serialized = json.dumps([first, second, audits], ensure_ascii=False)
    assert _RAW not in serialized
    assert hmac_protected_identifier(_RAW, _PEPPER) not in serialized
    assert connection.inserted[7] not in serialized
    assert first["publication_performed"] is False


@pytest.mark.asyncio
async def test_staging_refuses_mismatched_repeat_without_new_audit() -> None:
    connection = _Connection()
    repository = _staging(connection)
    await repository.stage_observation(payload=_payload(), actor_alias="operador-teste")
    before = len(connection.events)
    with pytest.raises(ValueError, match="prova diferente"):
        await repository.stage_observation(
            payload=_payload(legal_name="Outra organização"),
            actor_alias="operador-teste",
        )
    assert all("INSERT INTO audit_events" not in sql for sql, _ in connection.events[before:])


@pytest.mark.asyncio
async def test_staging_requires_archive_before_insert() -> None:
    connection = _Connection()
    connection.source["attestation_sha256"] = None
    with pytest.raises(ValueError, match="arquivo privado"):
        await _staging(connection).stage_observation(
            payload=_payload(),
            actor_alias="operador-teste",
        )
    assert connection.inserted is None


@pytest.mark.asyncio
async def test_driver_detail_is_removed_from_exception() -> None:
    connection = _Connection()
    connection.error = True
    with pytest.raises(ValueError) as error:
        await _staging(connection).stage_observation(
            payload=_payload(),
            actor_alias="operador-teste",
        )
    assert _RAW not in str(error.value)
    assert error.value.__suppress_context__ is True


def test_cli_parser_has_no_raw_identifier_or_hmac_argument() -> None:
    destinations = {action.dest for action in command._parser()._actions}
    assert "fiscal_identifier" not in destinations
    assert "nipc" not in destinations
    assert "protected_identifier_digest" not in destinations


@pytest.mark.asyncio
async def test_cli_rejects_production_before_prompt_or_connect(monkeypatch) -> None:
    monkeypatch.setattr(
        command,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            protected_identifier_pepper=SecretStr(_PEPPER),
        ),
    )
    prompt = MagicMock()
    repository = MagicMock()
    monkeypatch.setattr(command, "getpass", prompt)
    monkeypatch.setattr(command, "PostgresRepository", repository)
    with pytest.raises(RuntimeError):
        await command.run(SimpleNamespace(confirm_private_staging=True))
    prompt.assert_not_called()
    repository.assert_not_called()


def test_cli_hides_validation_or_driver_exception(monkeypatch, capsys) -> None:
    parser = MagicMock()
    monkeypatch.setattr(command, "_parser", lambda: parser)
    monkeypatch.setattr(command, "run", AsyncMock(side_effect=ValueError(_RAW)))
    with pytest.raises(SystemExit) as error:
        command.main()
    assert _RAW not in str(error.value)
    assert _RAW not in capsys.readouterr().err
