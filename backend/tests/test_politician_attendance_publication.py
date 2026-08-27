from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.models.editorial import PoliticianAttendancePublicationRequest
from app.repositories.editorial import EditorialConflictError, EditorialSourceError
from app.repositories.politician_attendance_publication import (
    PoliticianAttendancePublicationRepository,
    _attendance_mapping_sha256,
    _status_projection,
)


def _payload(**overrides: object) -> PoliticianAttendancePublicationRequest:
    values: dict[str, object] = {
        "expected_case_id": "case_attendance_fixture",
        "expected_version_id": "version_attendance_fixture",
        "expected_version_sha256": "a" * 64,
        "expected_source_sha256": "b" * 64,
        "expected_snapshot_sha256": "c" * 64,
        "expected_mapping_sha256": "d" * 64,
        "expected_publication_proof_sha256": "e" * 64,
        "expected_record_count": 3,
        "rationale": "A reunião integral e toda a prova oficial foram revistas por pessoa.",
        "public_rationale": "Reunião integral publicada após revisão humana da fonte oficial.",
        "confirm_source_reviewed": True,
        "confirm_complete_meeting": True,
        "confirm_exact_official_ids_and_mandates_only": True,
        "confirm_all_statuses_reviewed": True,
        "confirm_absence_is_not_noncompliance": True,
        "confirm_append_only_publication": True,
        "confirm_publication": True,
    }
    values.update(overrides)
    return PoliticianAttendancePublicationRequest.model_validate(values)


def _preview() -> dict[str, object]:
    return {
        "case_id": "case_attendance_fixture",
        "version_id": "version_attendance_fixture",
        "version_sha256": "a" * 64,
        "source": {"content_sha256": "b" * 64},
        "snapshot_sha256": "c" * 64,
        "mapping_sha256": "d" * 64,
        "publication_proof_sha256": "e" * 64,
        "public_effect": {"attendance_records_to_create": 3},
    }


def _mapping(index: int, status: str) -> dict[str, object]:
    return {
        "observation_id": f"observation_{index}",
        "official_deputy_id": f"deputy_{index}",
        "person_id": f"person_{index}",
        "mandate_id": f"mandate_{index}",
        "source_record_sha256": f"{index + 1:064x}",
        "status": status,
        "absence_reason": "Missão parlamentar" if status == "JUSTIFIED_ABSENCE" else None,
    }


def test_attendance_publication_request_is_strict_and_requires_every_confirmation() -> None:
    assert _payload().expected_record_count == 3
    with pytest.raises(ValidationError):
        _payload(confirm_complete_meeting=False)
    with pytest.raises(ValidationError):
        _payload(expected_record_count=0)
    with pytest.raises(ValidationError):
        PoliticianAttendancePublicationRequest.model_validate(
            {**_payload().model_dump(), "unexpected": True}
        )


def test_attendance_publication_confirmation_rejects_every_changed_proof() -> None:
    PoliticianAttendancePublicationRepository._confirm_payload(
        case_id="case_attendance_fixture",
        preview=_preview(),
        payload=_payload(),
    )
    mutations = {
        "version_id": "changed_version",
        "version_sha256": "f" * 64,
        "snapshot_sha256": "f" * 64,
        "mapping_sha256": "f" * 64,
        "publication_proof_sha256": "f" * 64,
    }
    for key, value in mutations.items():
        changed = deepcopy(_preview())
        changed[key] = value
        with pytest.raises(EditorialConflictError):
            PoliticianAttendancePublicationRepository._confirm_payload(
                case_id="case_attendance_fixture",
                preview=changed,
                payload=_payload(),
            )
    changed_source = deepcopy(_preview())
    source = changed_source["source"]
    assert isinstance(source, dict)
    source["content_sha256"] = "f" * 64
    with pytest.raises(EditorialConflictError):
        PoliticianAttendancePublicationRepository._confirm_payload(
            case_id="case_attendance_fixture",
            preview=changed_source,
            payload=_payload(),
        )


def test_mapping_proof_is_order_independent_and_excludes_raw_identifiers() -> None:
    rows = [
        _mapping(0, "PRESENT"),
        _mapping(1, "JUSTIFIED_ABSENCE"),
        _mapping(2, "UNJUSTIFIED_ABSENCE"),
    ]
    digest = _attendance_mapping_sha256(rows)
    assert digest == _attendance_mapping_sha256(list(reversed(rows)))
    assert len(digest) == 64
    assert all(identifier not in digest for identifier in ("deputy_0", "person_0", "mandate_0"))


def test_status_projection_preserves_source_semantics_and_rejects_unknown() -> None:
    assert _status_projection("PRESENT") == (True, None)
    assert _status_projection("JUSTIFIED_ABSENCE") == (False, True)
    assert _status_projection("UNJUSTIFIED_ABSENCE") == (False, False)
    with pytest.raises(EditorialSourceError, match="estado não publicável"):
        _status_projection("UNKNOWN")
