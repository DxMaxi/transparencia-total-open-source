import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.editorial import (
    PoliticianAttendanceEditorialProposalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialSourceError
from app.repositories.politician_attendance_editorial import (
    PoliticianAttendanceEditorialRepository,
)


def _candidate_row(*, actual_records: int = 100, unknown: int = 1) -> dict[str, object]:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    return {
        "id": "parliament_attendance_snapshot_fixture",
        "source_document_id": "source_attendance_fixture",
        "legislature": "XVII",
        "official_meeting_id": "376838",
        "meeting_date": date(2026, 7, 17),
        "meeting_type": "Ordinária",
        "session_number": "111",
        "parser_version": "parliament-attendance-html-v1",
        "normalised_sha256": "a" * 64,
        "collected_at": now,
        "record_count": 100,
        "present_count": 97,
        "justified_absence_count": 1,
        "unjustified_absence_count": 1,
        "unknown_count": unknown,
        "source_title": "Presenças à reunião plenária",
        "official_identifier": "AR-PLENARY-XVII-376838",
        "source_url": (
            "https://www.parlamento.pt/DeputadoGP/Paginas/DetalheReuniaoPlenaria.aspx?BID=376838"
        ),
        "source_retrieved_at": now,
        "source_sha256": "b" * 64,
        "source_mime_type": "text/html",
        "storage_backend": "POSTGRES",
        "byte_size": 12345,
        "archived_at": now,
        "attestation_sha256": "c" * 64,
        "actual_record_count": actual_records,
        "actual_present_count": 97,
        "actual_justified_absence_count": 1,
        "actual_unjustified_absence_count": 1,
        "actual_unknown_count": unknown,
        "identity_count": 90,
        "reviewed_identity_count": 89,
        "exact_mandate_count": 80,
        "reviewed_mandate_count": 79,
        "case_id": None,
        "case_state": None,
        "case_revision": None,
        "case_origin": None,
        "total_count": 1,
    }


def _observation(index: int) -> dict[str, object]:
    return {
        "official_deputy_id": str(7000 + index),
        "parliamentary_name": f"Pessoa Deputada {index:03d}",
        "parliamentary_group_label": "G1",
        "status": "PRESENT" if index else "UNKNOWN",
        "source_status_label": "Presença (P)" if index else "Estado (X)",
        "source_status_code": "P" if index else "X",
        "absence_reason": None,
        "source_record_sha256": f"{index:064x}"[-64:],
    }


def _actor() -> StaffSession:
    return StaffSession(
        staff_id="staff_fixture",
        auth_user_id=uuid4(),
        public_alias="revisor-fixture",
        role=StaffRole.REVIEWER,
        assurance_level="aal1",
        mfa_required=False,
    )


@pytest.mark.asyncio
async def test_candidate_is_whole_meeting_and_exposes_publication_blockers() -> None:
    pool = AsyncMock()
    pool.fetch.return_value = [_candidate_row()]
    repository = PoliticianAttendanceEditorialRepository(pool)

    result = await repository.list_candidates(
        legislature="XVII",
        limit=10,
        offset=0,
    )

    assert result["total"] == 1
    candidate = result["items"][0]
    assert candidate["proposal_eligible"] is True
    assert candidate["publication_ready"] is False
    assert candidate["selective_processing_allowed"] is False
    assert candidate["name_matching_allowed"] is False
    assert candidate["manifest_counts"]["records"] == 100
    assert len(candidate["publication_blockers"]) == 5
    assert "fotografia integral" in result["selection_rule"]


@pytest.mark.asyncio
async def test_proposal_hashes_ids_and_never_creates_public_rows() -> None:
    pool = AsyncMock()
    pool.fetch.side_effect = [
        [_candidate_row()],
        [_observation(index) for index in range(100)],
    ]
    repository = PoliticianAttendanceEditorialRepository(pool)
    repository.editorial = AsyncMock()
    repository.editorial.create_ingestion_case.return_value = (
        {
            "id": "case_attendance_fixture",
            "subject_type": "PARLIAMENT_ATTENDANCE_SNAPSHOT",
            "current_state": "PENDING",
        },
        True,
    )
    payload = PoliticianAttendanceEditorialProposalRequest(
        snapshot_id="parliament_attendance_snapshot_fixture",
        confirm_private_only=True,
        confirm_complete_meeting=True,
        confirm_exact_official_ids_only=True,
        confirm_no_name_matching=True,
        confirm_absence_is_not_noncompliance=True,
        confirm_no_selective_processing=True,
    )

    result = await repository.create_proposal(payload=payload, actor=_actor())

    assert result["publication_performed"] is False
    assert result["session_created"] is False
    assert result["attendance_records_created"] == 0
    assert result["selective_processing_allowed"] is False
    call = repository.editorial.create_ingestion_case.await_args.kwargs
    assert call["subject_type"] == "PARLIAMENT_ATTENDANCE_SNAPSHOT"
    normalized = call["normalized_data"]
    serialized = json.dumps(normalized, ensure_ascii=False)
    assert "official_meeting_id_reference_sha256" in serialized
    assert "DetalheReuniaoPlenaria.aspx?BID=376838" in serialized
    assert "7000" not in serialized
    assert normalized["identity_rule"] == "EXACT_AR_BID_ONLY"
    assert normalized["selection_rule"] == "WHOLE_MEETING_ONLY"
    assert normalized["absence_rule"] == "SOURCE_STATUS_IS_NOT_AUTOMATIC_NONCOMPLIANCE"
    assert normalized["publication"]["attendance_records_created"] == 0
    assert len(normalized["records"]) == 100


@pytest.mark.asyncio
async def test_proposal_rejects_manifest_divergence() -> None:
    pool = AsyncMock()
    pool.fetch.return_value = [_candidate_row(actual_records=99)]
    repository = PoliticianAttendanceEditorialRepository(pool)

    payload = PoliticianAttendanceEditorialProposalRequest(
        snapshot_id="parliament_attendance_snapshot_fixture",
        confirm_private_only=True,
        confirm_complete_meeting=True,
        confirm_exact_official_ids_only=True,
        confirm_no_name_matching=True,
        confirm_absence_is_not_noncompliance=True,
        confirm_no_selective_processing=True,
    )
    with pytest.raises(EditorialSourceError, match="contagens materializadas"):
        await repository.create_proposal(payload=payload, actor=_actor())


def test_attendance_proposal_requires_every_safety_confirmation() -> None:
    with pytest.raises(ValidationError):
        PoliticianAttendanceEditorialProposalRequest(
            snapshot_id="parliament_attendance_snapshot_fixture",
            confirm_private_only=True,
            confirm_complete_meeting=True,
            confirm_exact_official_ids_only=True,
            confirm_no_name_matching=True,
            confirm_absence_is_not_noncompliance=True,
            confirm_no_selective_processing=False,
        )
