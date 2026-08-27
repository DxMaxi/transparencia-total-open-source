from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models.editorial import PoliticianAttendanceWithdrawalRequest
from app.repositories.editorial import EditorialConflictError
from app.repositories.politician_attendance_withdrawal import (
    PoliticianAttendanceWithdrawalRepository,
    _publication_effect,
)


def _payload(**overrides: object) -> PoliticianAttendanceWithdrawalRequest:
    values: dict[str, object] = {
        "expected_case_id": "case_attendance_fixture",
        "expected_revision": 4,
        "expected_version_id": "version_attendance_fixture",
        "expected_version_sha256": "a" * 64,
        "expected_snapshot_id": "snapshot_attendance_fixture",
        "expected_source_sha256": "b" * 64,
        "expected_snapshot_sha256": "c" * 64,
        "expected_mapping_sha256": "d" * 64,
        "expected_publication_proof_sha256": "e" * 64,
        "expected_withdrawal_proof_sha256": "f" * 64,
        "expected_public_review_id": "review_attendance_fixture",
        "expected_publication_audit_event_id": "audit_attendance_fixture",
        "expected_publication_event_id": "event_attendance_fixture",
        "expected_publication_event_sha256": "1" * 64,
        "expected_public_effect_sha256": "2" * 64,
        "expected_record_count": 100,
        "rationale": "A retirada integral foi revista com toda a prova oficial preservada.",
        "public_rationale": "Reunião retirada após revisão humana documentada da fonte.",
        "reason_category": "OFFICIAL_SOURCE_CORRECTION",
        "confirm_source_and_publication_reviewed": True,
        "confirm_complete_meeting": True,
        "confirm_public_effect_reviewed": True,
        "confirm_session_records_and_history_preserved": True,
        "confirm_no_selective_person_or_mandate_change": True,
        "confirm_absence_is_not_noncompliance": True,
        "confirm_withdrawal": True,
    }
    values.update(overrides)
    return PoliticianAttendanceWithdrawalRequest.model_validate(values)


def _preview() -> dict[str, object]:
    return {
        "case_id": "case_attendance_fixture",
        "case_revision": 4,
        "version_id": "version_attendance_fixture",
        "version_sha256": "a" * 64,
        "snapshot_id": "snapshot_attendance_fixture",
        "source": {"content_sha256": "b" * 64},
        "snapshot_sha256": "c" * 64,
        "mapping_sha256": "d" * 64,
        "publication_proof_sha256": "e" * 64,
        "withdrawal_proof_sha256": "f" * 64,
        "public_review_id": "review_attendance_fixture",
        "publication_audit_event_id": "audit_attendance_fixture",
        "publication_event_id": "event_attendance_fixture",
        "publication_event_sha256": "1" * 64,
        "public_effect_sha256": "2" * 64,
        "record_count": 100,
    }


def test_attendance_withdrawal_request_is_strict_and_requires_every_confirmation() -> None:
    assert _payload().expected_record_count == 100
    with pytest.raises(ValidationError):
        _payload(confirm_complete_meeting=False)
    with pytest.raises(ValidationError):
        _payload(expected_record_count=0)
    with pytest.raises(ValidationError):
        _payload(reason_category="POLITICAL_CONVENIENCE")
    with pytest.raises(ValidationError):
        PoliticianAttendanceWithdrawalRequest.model_validate(
            {**_payload().model_dump(), "unexpected": True}
        )


def test_attendance_withdrawal_confirmation_rejects_every_changed_proof() -> None:
    PoliticianAttendanceWithdrawalRepository._confirm_payload(
        case_id="case_attendance_fixture",
        preview=_preview(),
        payload=_payload(),
    )
    mutations: dict[str, object] = {
        "case_revision": 5,
        "version_id": "changed_version",
        "version_sha256": "3" * 64,
        "snapshot_id": "changed_snapshot",
        "snapshot_sha256": "3" * 64,
        "mapping_sha256": "3" * 64,
        "publication_proof_sha256": "3" * 64,
        "withdrawal_proof_sha256": "3" * 64,
        "public_review_id": "changed_review",
        "publication_audit_event_id": "changed_audit",
        "publication_event_id": "changed_event",
        "publication_event_sha256": "3" * 64,
        "public_effect_sha256": "3" * 64,
        "record_count": 99,
    }
    for key, value in mutations.items():
        changed = deepcopy(_preview())
        changed[key] = value
        with pytest.raises(EditorialConflictError):
            PoliticianAttendanceWithdrawalRepository._confirm_payload(
                case_id="case_attendance_fixture",
                preview=changed,
                payload=_payload(),
            )
    changed_source = deepcopy(_preview())
    source = changed_source["source"]
    assert isinstance(source, dict)
    source["content_sha256"] = "3" * 64
    with pytest.raises(EditorialConflictError):
        PoliticianAttendanceWithdrawalRepository._confirm_payload(
            case_id="case_attendance_fixture",
            preview=changed_source,
            payload=_payload(),
        )


def test_attendance_withdrawal_effect_preserves_every_historical_row() -> None:
    effect = _publication_effect(100)
    assert effect["attendance_records_to_create"] == 100
    assert effect["people_to_create"] == 0
    assert effect["mandates_to_create"] == 0
