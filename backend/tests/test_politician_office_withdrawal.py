import pytest
from pydantic import ValidationError

from app.models.editorial import PoliticianOfficeWithdrawalRequest
from app.repositories.editorial import EditorialConflictError
from app.repositories.politician_office_withdrawal import (
    PoliticianOfficeWithdrawalRepository,
)


def _preview() -> dict[str, object]:
    return {
        "case_id": "case_alpha",
        "case_revision": 4,
        "version_id": "version_alpha",
        "version_sha256": "a" * 64,
        "office_id": "office_alpha",
        "source": {"content_sha256": "b" * 64},
        "source_period_sha256": "c" * 64,
        "publication_proof_sha256": "d" * 64,
        "withdrawal_proof_sha256": "e" * 64,
        "public_review_id": "review_alpha",
        "publication_audit_event_id": "audit_alpha",
        "publication_event_id": "event_alpha",
        "publication_event_sha256": "f" * 64,
        "public_effect_sha256": "1" * 64,
    }


def _payload(**overrides: object) -> PoliticianOfficeWithdrawalRequest:
    values: dict[str, object] = {
        "expected_case_id": "case_alpha",
        "expected_revision": 4,
        "expected_version_id": "version_alpha",
        "expected_version_sha256": "a" * 64,
        "expected_office_id": "office_alpha",
        "expected_source_sha256": "b" * 64,
        "expected_period_sha256": "c" * 64,
        "expected_publication_proof_sha256": "d" * 64,
        "expected_withdrawal_proof_sha256": "e" * 64,
        "expected_public_review_id": "review_alpha",
        "expected_publication_audit_event_id": "audit_alpha",
        "expected_publication_event_id": "event_alpha",
        "expected_publication_event_sha256": "f" * 64,
        "expected_public_effect_sha256": "1" * 64,
        "rationale": "A fonte oficial corrigiu o cargo anteriormente publicado.",
        "public_rationale": "Cargo retirado após correção documentada da fonte oficial.",
        "reason_category": "OFFICIAL_SOURCE_CORRECTION",
        "confirm_source_and_publication_reviewed": True,
        "confirm_exact_office": True,
        "confirm_public_effect_reviewed": True,
        "confirm_office_and_history_preserved": True,
        "confirm_no_selective_identity_or_mandate_change": True,
        "confirm_withdrawal": True,
    }
    values.update(overrides)
    return PoliticianOfficeWithdrawalRequest.model_validate(values)


def test_office_withdrawal_request_is_strict_and_requires_all_confirmations() -> None:
    valid = _payload()
    assert valid.confirm_withdrawal is True
    assert valid.rationale.startswith("A fonte")

    with pytest.raises(ValidationError):
        _payload(confirm_office_and_history_preserved=False)
    with pytest.raises(ValidationError):
        _payload(expected_withdrawal_proof_sha256="E" * 64)
    with pytest.raises(ValidationError):
        _payload(unexpected=True)


def test_office_withdrawal_confirmation_rejects_every_stale_proof() -> None:
    PoliticianOfficeWithdrawalRepository._confirm_payload(
        case_id="case_alpha",
        preview=_preview(),
        payload=_payload(),
    )

    for field, changed in (
        ("expected_revision", 5),
        ("expected_version_id", "version_beta"),
        ("expected_version_sha256", "2" * 64),
        ("expected_office_id", "office_beta"),
        ("expected_source_sha256", "2" * 64),
        ("expected_period_sha256", "2" * 64),
        ("expected_publication_proof_sha256", "2" * 64),
        ("expected_withdrawal_proof_sha256", "2" * 64),
        ("expected_public_review_id", "review_beta"),
        ("expected_publication_audit_event_id", "audit_beta"),
        ("expected_publication_event_id", "event_beta"),
        ("expected_publication_event_sha256", "2" * 64),
        ("expected_public_effect_sha256", "2" * 64),
    ):
        with pytest.raises(EditorialConflictError):
            PoliticianOfficeWithdrawalRepository._confirm_payload(
                case_id="case_alpha",
                preview=_preview(),
                payload=_payload(**{field: changed}),
            )
