from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.models.editorial import (
    ParliamentEditorialPublicationRequest,
    ParliamentEditorialScope,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialConflictError, EditorialSourceError
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.parliament_editorial_publication import (
    ParliamentEditorialPublicationRepository,
    _sha256_json,
)


class Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class PublicationConnection:
    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case
        self.commands: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> Transaction:
        return Transaction()

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any]:
        if "FROM editorial_cases AS c" in query:
            assert arguments == (self.case["id"],)
            return self.case
        assert "FROM data_publication_reviews" in query
        assert arguments == (
            self.case["subject_type"],
            self.case["subject_id"],
            self.case["source_document_id"],
        )
        return {
            "id": self.case["public_review_id"],
            "publishable": self.case["public_publishable"],
            "reviewed_at": self.case["public_reviewed_at"],
        }

    async def execute(self, query: str, *arguments: object) -> str:
        self.commands.append((query, arguments))
        return "OK"

    async def fetchval(self, query: str, *arguments: object) -> datetime:
        if query == "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)":
            assert arguments == ()
            return datetime(2026, 8, 11, 12, 0, 0, 123000)
        assert "SELECT GREATEST" in query
        assert arguments == (self.case["public_reviewed_at"],)
        return datetime(2026, 8, 11, 12, 0, 0, 124000)


class Acquire:
    def __init__(self, connection: PublicationConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> PublicationConnection:
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class Pool:
    def __init__(self, connection: PublicationConnection) -> None:
        self.connection = connection

    def acquire(self) -> Acquire:
        return Acquire(self.connection)


def _candidate(*, manifest_matches: bool = True) -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "source_document_id": "source-1",
        "legislature": "XVII",
        "parser_version": "parliament-activity-v2",
        "normalised_sha256": "b" * 64,
        "collected_at": "2026-08-11T10:00:00Z",
        "source": {
            "title": "Atividade parlamentar",
            "official_identifier": "XVII",
            "url": "https://www.parlamento.pt/dados.json",
            "retrieved_at": "2026-08-11T10:00:00Z",
            "content_sha256": "a" * 64,
            "mime_type": "application/json",
        },
        "archive": {
            "storage_backend": "local-test",
            "byte_size": 1234,
            "archived_at": "2026-08-11T10:01:00Z",
            "attestation_sha256": "e" * 64,
        },
        "manifest_counts": {
            "sessions": 2,
            "initiatives": 3,
            "votes": 4,
            "vote_records": 5,
        },
        "materialised_counts": {
            "sessions": 2 if manifest_matches else 1,
            "initiatives": 3,
            "votes": 4,
            "vote_records": 5,
        },
        "manifest_matches": manifest_matches,
        "coverage": {
            "nominal_votes": 1,
            "votes_without_records": 0,
            "person_records": 2,
            "linked_person_records": 2,
            "unlinked_person_records": 0,
            "party_records": 1,
            "linked_party_records": 1,
            "unlinked_party_records": 0,
            "unknown_actor_records": 2,
            "unknown_choice_records": 1,
            "inconsistent_actor_links": 0,
        },
        "previous_snapshot": None,
        "differences": {
            "status": "NO_PREVIOUS_SNAPSHOT",
            "sessions": None,
            "initiatives": None,
            "votes": None,
        },
        "limitations": [
            "Ausência de dados é apresentada como dados indisponíveis.",
            "Não existe correspondência aproximada de nomes.",
        ],
        "editorial_cases": {
            "activity": {
                "id": "case-1",
                "state": "APPROVED",
                "revision": 3,
                "origin": "INGESTION",
            },
            "votes": None,
        },
        "proposal_eligible": manifest_matches,
        "publication_state": "PRIVATE_ONLY",
    }


def _case(candidate: dict[str, object]) -> dict[str, Any]:
    normalized = ParliamentEditorialRepository.normalized_proposal_for_publication(
        candidate,
        ParliamentEditorialScope.ACTIVITY,
    )
    return {
        "id": "case-1",
        "kind": "PARLIAMENT_ACTIVITY",
        "subject_type": "PARLIAMENT_ACTIVITY_SNAPSHOT",
        "subject_id": "snapshot-1",
        "source_document_id": "source-1",
        "origin": "INGESTION",
        "current_version_id": "version-1",
        "current_state": "APPROVED",
        "revision": 3,
        "normalized_json": normalized,
        "editorial_sha256": _sha256_json(normalized),
        "source_sha256": "a" * 64,
        "snapshot_legislature": "XVII",
        "snapshot_normalised_sha256": "b" * 64,
        "public_review_id": None,
        "public_publishable": None,
        "public_reviewed_at": None,
        "public_reviewed_by": None,
        "publication_event_id": None,
        "publication_event_version_id": None,
        "publication_event_target_type": None,
        "publication_event_target_id": None,
        "publication_event_rationale": None,
        "publication_event_actor_id": None,
        "publication_event_actor_alias": None,
        "publication_event_sha256": None,
        "publication_event_created_at": None,
        "withdrawal_event_id": None,
        "publication_audit_event_id": None,
        "publication_audit_after_json": None,
        "publication_audit_created_at": None,
    }


def _actor(role: StaffRole = StaffRole.ADMIN) -> StaffSession:
    return StaffSession(
        staff_id="staff-admin",
        auth_user_id=UUID("a430b34c-8615-4cb4-aebb-3054d796783e"),
        public_alias="admin-teste",
        role=role,
        assurance_level="aal2",
        mfa_required=False,
    )


def _repository(
    candidate: dict[str, object],
) -> tuple[ParliamentEditorialPublicationRepository, PublicationConnection]:
    connection = PublicationConnection(_case(candidate))
    repository = ParliamentEditorialPublicationRepository(Pool(connection))  # type: ignore[arg-type]
    repository.parliament.load_snapshot_candidate_for_publication = AsyncMock(  # type: ignore[method-assign]
        return_value=candidate
    )
    return repository, connection


def _payload(
    preview: dict[str, object], **changes: object
) -> ParliamentEditorialPublicationRequest:
    source = preview["source"]
    editorial_version = preview["editorial_version"]
    assert isinstance(source, dict)
    assert isinstance(editorial_version, dict)
    values: dict[str, object] = {
        "expected_revision": preview["revision"],
        "rationale": "Fonte, âmbito e prova parlamentar confirmados antes da publicação.",
        "confirmed_scope": preview["scope"],
        "expected_snapshot_id": preview["target_id"],
        "expected_source_sha256": source["content_sha256"],
        "expected_snapshot_sha256": preview["snapshot_sha256"],
        "expected_editorial_sha256": editorial_version["normalized_sha256"],
        "expected_publication_proof_sha256": preview["publication_proof_sha256"],
        "confirm_source_reviewed": True,
        "confirm_no_individual_inference": True,
        "confirm_publication": True,
    }
    values.update(changes)
    return ParliamentEditorialPublicationRequest.model_validate(values)


@pytest.mark.asyncio
async def test_preview_is_read_only_and_derives_scope_from_the_case() -> None:
    repository, connection = _repository(_candidate())

    preview = await repository.inspect(case_id="case-1")

    assert preview["scope"] == "activity"
    assert preview["target_type"] == "PARLIAMENT_ACTIVITY_SNAPSHOT"
    assert preview["eligible"] is True
    assert preview["blockers"] == []
    assert connection.commands == []


@pytest.mark.asyncio
async def test_publication_commits_v4_gate_decision_projection_and_event_in_order() -> None:
    repository, connection = _repository(_candidate())
    preview = await repository.inspect(case_id="case-1")

    result = await repository.publish(
        case_id="case-1",
        payload=_payload(preview),
        actor=_actor(),
    )

    assert result["state"] == "PUBLISHED"
    assert result["scope"] == "activity"
    commands = [query for query, _arguments in connection.commands]
    assert "pg_advisory_xact_lock" in commands[0]
    assert "pg_advisory_xact_lock" in commands[1]
    assert "INSERT INTO data_publication_reviews" in commands[2]
    assert "INSERT INTO audit_events" in commands[3]
    assert "INSERT INTO editorial_decisions" in commands[4]
    assert "UPDATE editorial_cases" in commands[5]
    assert "INSERT INTO editorial_publication_events" in commands[6]
    review_arguments = connection.commands[2][1]
    assert review_arguments[1] == "PARLIAMENT_ACTIVITY_SNAPSHOT"
    assert review_arguments[2] == "snapshot-1"
    assert review_arguments[4] == "source-1"


@pytest.mark.asyncio
async def test_changed_confirmation_or_manifest_fails_before_any_public_write() -> None:
    repository, connection = _repository(_candidate())
    preview = await repository.inspect(case_id="case-1")

    with pytest.raises(EditorialConflictError, match="SHA-256 da fonte"):
        await repository.publish(
            case_id="case-1",
            payload=_payload(preview, expected_source_sha256="f" * 64),
            actor=_actor(),
        )
    assert not any("INSERT INTO" in query for query, _arguments in connection.commands)

    scope_repository, scope_connection = _repository(_candidate())
    scope_preview = await scope_repository.inspect(case_id="case-1")
    with pytest.raises(EditorialConflictError, match="âmbito"):
        await scope_repository.publish(
            case_id="case-1",
            payload=_payload(scope_preview, confirmed_scope="votes"),
            actor=_actor(),
        )
    assert not any("INSERT INTO" in query for query, _arguments in scope_connection.commands)

    blocked_repository, blocked_connection = _repository(_candidate(manifest_matches=False))
    blocked_preview = await blocked_repository.inspect(case_id="case-1")
    with pytest.raises(EditorialSourceError, match="manifesto imutável"):
        await blocked_repository.publish(
            case_id="case-1",
            payload=_payload(blocked_preview),
            actor=_actor(),
        )
    assert not any("INSERT INTO" in query for query, _arguments in blocked_connection.commands)


@pytest.mark.asyncio
async def test_editorial_notes_are_allowed_but_source_limitations_cannot_be_weakened() -> None:
    candidate = _candidate()
    repository, connection = _repository(candidate)
    normalized = connection.case["normalized_json"]
    assert isinstance(normalized, dict)
    normalized["editorial_notes"] = ["Nota humana adicional, ainda privada e auditável."]
    connection.case["editorial_sha256"] = _sha256_json(normalized)

    preview = await repository.inspect(case_id="case-1")
    assert preview["eligible"] is True

    normalized["limitations"] = []
    connection.case["editorial_sha256"] = _sha256_json(normalized)
    weakened = await repository.inspect(case_id="case-1")
    blocker_codes = {item["code"] for item in weakened["blockers"]}
    assert "PUBLICATION_PROOF_MISMATCH" in blocker_codes


@pytest.mark.asyncio
async def test_reviewer_cannot_open_a_publication_transaction() -> None:
    repository, connection = _repository(_candidate())
    preview = await repository.inspect(case_id="case-1")

    with pytest.raises(EditorialConflictError, match="administrador"):
        await repository.publish(
            case_id="case-1",
            payload=_payload(preview),
            actor=_actor(StaffRole.REVIEWER),
        )
    assert connection.commands == []
