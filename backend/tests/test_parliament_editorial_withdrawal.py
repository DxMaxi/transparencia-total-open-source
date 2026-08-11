from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest

from app.models.editorial import (
    ParliamentEditorialScope,
    ParliamentEditorialWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialConflictError
from app.repositories.parliament_editorial import ParliamentEditorialRepository
from app.repositories.parliament_editorial_publication import (
    ParliamentEditorialPublicationRepository,
    _publication_event_sha256,
    _publication_proof,
    _sha256_json,
)


class Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: object) -> None:
        return None


class WithdrawalConnection:
    def __init__(self, case: dict[str, Any], *, fallback: dict[str, Any] | None = None) -> None:
        self.case = case
        self.fallback = fallback
        self.commands: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> Transaction:
        return Transaction()

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any] | None:
        if "FROM editorial_cases AS c" in query:
            assert arguments == (self.case["id"],)
            return self.case
        if "FROM parliament_activity_snapshots AS snapshot" in query:
            assert arguments == (
                self.case["snapshot_legislature"],
                self.case["subject_id"],
                self.case["subject_type"],
            )
            return self.fallback
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
            return datetime(2026, 8, 11, 13, 0, 0, 123000)
        assert "SELECT GREATEST" in query
        assert arguments == (self.case["public_reviewed_at"],)
        return datetime(2026, 8, 11, 13, 0, 0, 124000)


class Acquire:
    def __init__(self, connection: WithdrawalConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> WithdrawalConnection:
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class Pool:
    def __init__(self, connection: WithdrawalConnection) -> None:
        self.connection = connection

    def acquire(self) -> Acquire:
        return Acquire(self.connection)


def _candidate() -> dict[str, object]:
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
            "sessions": 2,
            "initiatives": 3,
            "votes": 4,
            "vote_records": 5,
        },
        "manifest_matches": True,
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
                "state": "PUBLISHED",
                "revision": 4,
                "origin": "INGESTION",
            },
            "votes": None,
        },
        "proposal_eligible": True,
        "publication_state": "PRIVATE_ONLY",
    }


def _case() -> dict[str, Any]:
    candidate = _candidate()
    normalized = ParliamentEditorialRepository.normalized_proposal_for_publication(
        candidate,
        ParliamentEditorialScope.ACTIVITY,
    )
    proof = _publication_proof(normalized)
    assert proof is not None
    published_at = datetime(2026, 8, 11, 12, 0, 0, 123000)
    event_sha256 = _publication_event_sha256(
        event_id="editorial_publication_original",
        case_id="case-1",
        version_id="version-1",
        action="PUBLISH",
        target_type="PARLIAMENT_ACTIVITY_SNAPSHOT",
        target_id="snapshot-1",
        rationale="Fonte e âmbito parlamentar confirmados antes da publicação.",
        actor_id="staff-admin",
        actor_alias="admin-teste",
        created_at=published_at,
    )
    reviewed_at = datetime(2026, 8, 11, 12, 0, 0, 124000)
    return {
        "id": "case-1",
        "kind": "PARLIAMENT_ACTIVITY",
        "subject_type": "PARLIAMENT_ACTIVITY_SNAPSHOT",
        "subject_id": "snapshot-1",
        "source_document_id": "source-1",
        "origin": "INGESTION",
        "current_version_id": "version-1",
        "current_state": "PUBLISHED",
        "revision": 4,
        "normalized_json": normalized,
        "editorial_sha256": _sha256_json(normalized),
        "source_sha256": "a" * 64,
        "snapshot_legislature": "XVII",
        "snapshot_normalised_sha256": "b" * 64,
        "public_review_id": "publication_review_original",
        "public_publishable": True,
        "public_reviewed_at": reviewed_at,
        "public_reviewed_by": "admin-teste",
        "publication_event_id": "editorial_publication_original",
        "publication_event_version_id": "version-1",
        "publication_event_target_type": "PARLIAMENT_ACTIVITY_SNAPSHOT",
        "publication_event_target_id": "snapshot-1",
        "publication_event_rationale": (
            "Fonte e âmbito parlamentar confirmados antes da publicação."
        ),
        "publication_event_actor_id": "staff-admin",
        "publication_event_actor_alias": "admin-teste",
        "publication_event_sha256": event_sha256,
        "publication_event_created_at": published_at,
        "withdrawal_event_id": None,
        "publication_audit_event_id": "audit_original",
        "publication_audit_after_json": {
            "publishable": True,
            "scope": "activity",
            "legislature": "XVII",
            "source_sha256": "a" * 64,
            "normalised_sha256": "b" * 64,
            "counts": candidate["manifest_counts"],
            "editorial_link": {
                "case_id": "case-1",
                "case_revision": 4,
                "version_id": "version-1",
                "editorial_sha256": _sha256_json(normalized),
                "publication_proof_sha256": _sha256_json(proof),
            },
        },
        "publication_audit_created_at": reviewed_at,
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
    *,
    fallback: dict[str, Any] | None = None,
) -> tuple[ParliamentEditorialPublicationRepository, WithdrawalConnection]:
    connection = WithdrawalConnection(_case(), fallback=fallback)
    repository = ParliamentEditorialPublicationRepository(Pool(connection))  # type: ignore[arg-type]
    return repository, connection


def _payload(
    preview: dict[str, object],
    **changes: object,
) -> ParliamentEditorialWithdrawalRequest:
    values: dict[str, object] = {
        "expected_revision": preview["revision"],
        "rationale": (
            "A fonte oficial diverge de forma reproduzível da fotografia publicada e exige revisão."
        ),
        "public_rationale": (
            "Fotografia retirada por divergência reproduzível com a fonte oficial."
        ),
        "reason_category": "SOURCE_DIVERGENCE",
        "confirmed_scope": preview["scope"],
        "expected_snapshot_id": preview["target_id"],
        "expected_source_sha256": preview["source_sha256"],
        "expected_snapshot_sha256": preview["snapshot_sha256"],
        "expected_editorial_sha256": preview["editorial_sha256"],
        "expected_publication_proof_sha256": preview["publication_proof_sha256"],
        "expected_public_review_id": preview["public_review_id"],
        "expected_publication_audit_event_id": preview["publication_audit_event_id"],
        "expected_publication_event_id": preview["publication_event_id"],
        "expected_publication_event_sha256": preview["publication_event_sha256"],
        "expected_public_effect_sha256": preview["public_effect_sha256"],
        "confirm_no_selective_removal": True,
        "confirm_public_effect_reviewed": True,
        "confirm_withdrawal": True,
    }
    values.update(changes)
    return ParliamentEditorialWithdrawalRequest.model_validate(values)


@pytest.mark.asyncio
async def test_withdrawal_preview_is_read_only_and_exposes_unavailable_effect() -> None:
    repository, connection = _repository()

    preview = await repository.inspect_withdrawal(case_id="case-1")

    assert preview["eligible"] is True
    assert preview["scope"] == "activity"
    assert preview["public_effect"] == {
        "kind": "DATA_UNAVAILABLE",
        "scope": "activity",
        "legislature": "XVII",
        "message": (
            "Depois da retirada não ficará outra fotografia aprovada neste âmbito; "
            "a interface mostrará dados indisponíveis."
        ),
    }
    assert connection.commands == []


@pytest.mark.asyncio
async def test_withdrawal_preview_exposes_an_exact_approved_fallback() -> None:
    repository, _connection = _repository(
        fallback={
            "id": "snapshot-previous",
            "normalised_sha256": "c" * 64,
            "collected_at": datetime(2026, 8, 10, 9, 0),
            "source_url": "https://www.parlamento.pt/anterior.json",
            "source_retrieved_at": datetime(2026, 8, 10, 9, 1),
            "source_sha256": "d" * 64,
            "verified_at": datetime(2026, 8, 10, 11, 0),
        }
    )

    preview = await repository.inspect_withdrawal(case_id="case-1")

    effect = preview["public_effect"]
    assert isinstance(effect, dict)
    assert effect["kind"] == "FALLBACK_TO_PREVIOUS_SNAPSHOT"
    assert effect["source_sha256"] == "d" * 64
    assert effect["snapshot_sha256"] == "c" * 64
    assert preview["public_effect_sha256"] == _sha256_json(effect)


@pytest.mark.asyncio
async def test_withdrawal_appends_public_gate_decision_projection_and_event() -> None:
    repository, connection = _repository()
    preview = await repository.inspect_withdrawal(case_id="case-1")

    result = await repository.withdraw(
        case_id="case-1",
        payload=_payload(preview),
        actor=_actor(),
    )

    assert result["state"] == "WITHDRAWN"
    assert result["reason_category"] == "SOURCE_DIVERGENCE"
    commands = [query for query, _arguments in connection.commands]
    assert "pg_advisory_xact_lock" in commands[0]
    assert "pg_advisory_xact_lock" in commands[1]
    assert "INSERT INTO data_publication_reviews" in commands[2]
    assert "INSERT INTO audit_events" in commands[3]
    assert "INSERT INTO editorial_decisions" in commands[4]
    assert "UPDATE editorial_cases" in commands[5]
    assert "INSERT INTO editorial_publication_events" in commands[6]
    assert connection.commands[2][1][3] is False
    assert connection.commands[3][1][7] == (
        "Fotografia retirada por divergência reproduzível com a fonte oficial."
    )


@pytest.mark.asyncio
async def test_stale_effect_or_public_review_fails_before_public_writes() -> None:
    repository, connection = _repository()
    preview = await repository.inspect_withdrawal(case_id="case-1")

    with pytest.raises(EditorialConflictError, match="efeito público"):
        await repository.withdraw(
            case_id="case-1",
            payload=_payload(preview, expected_public_effect_sha256="f" * 64),
            actor=_actor(),
        )
    assert not any("INSERT INTO" in query for query, _arguments in connection.commands)

    review_repository, review_connection = _repository()
    review_preview = await review_repository.inspect_withdrawal(case_id="case-1")
    with pytest.raises(EditorialConflictError, match="revisão pública"):
        await review_repository.withdraw(
            case_id="case-1",
            payload=_payload(review_preview, expected_public_review_id="stale-review"),
            actor=_actor(),
        )
    assert not any("INSERT INTO" in query for query, _arguments in review_connection.commands)


@pytest.mark.asyncio
async def test_reviewer_cannot_open_a_withdrawal_transaction() -> None:
    repository, connection = _repository()
    preview = await repository.inspect_withdrawal(case_id="case-1")

    with pytest.raises(EditorialConflictError, match="administrador"):
        await repository.withdraw(
            case_id="case-1",
            payload=_payload(preview),
            actor=_actor(StaffRole.REVIEWER),
        )
    assert connection.commands == []
