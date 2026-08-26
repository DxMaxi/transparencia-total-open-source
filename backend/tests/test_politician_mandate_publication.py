from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.editorial import PoliticianMandatePublicationRequest
from app.repositories.editorial import EditorialConflictError
from app.repositories.politician_mandate_publication import (
    PoliticianMandatePublicationRepository,
    _subject_parts,
)


def _preview() -> dict[str, object]:
    return {
        "case_id": "case_alpha",
        "version_id": "version_alpha",
        "version_sha256": "a" * 64,
        "source_period_sha256": "b" * 64,
        "source": {"content_sha256": "c" * 64},
        "publication_proof_sha256": "d" * 64,
    }


def _payload(**overrides: object) -> PoliticianMandatePublicationRequest:
    values: dict[str, object] = {
        "expected_case_id": "case_alpha",
        "expected_version_id": "version_alpha",
        "expected_version_sha256": "a" * 64,
        "expected_source_sha256": "c" * 64,
        "expected_period_sha256": "b" * 64,
        "expected_publication_proof_sha256": "d" * 64,
        "rationale": "A fonte e o intervalo foram novamente confirmados pelo administrador.",
        "public_rationale": "Mandato confirmado no documento parlamentar oficial arquivado.",
        "confirm_source_reviewed": True,
        "confirm_human_period_interpretation": True,
        "confirm_exact_official_id_only": True,
        "confirm_no_party_inference": True,
        "confirm_append_only_publication": True,
        "confirm_publication": True,
    }
    values.update(overrides)
    return PoliticianMandatePublicationRequest.model_validate(values)


def test_mandate_publication_request_is_strict_and_requires_every_confirmation() -> None:
    valid = _payload()
    assert valid.confirm_publication is True
    assert valid.rationale.startswith("A fonte")

    with pytest.raises(ValidationError):
        _payload(confirm_human_period_interpretation=False)
    with pytest.raises(ValidationError):
        _payload(expected_period_sha256="A" * 64)
    with pytest.raises(ValidationError):
        _payload(unexpected=True)


def test_mandate_subject_reference_requires_one_exact_observation_and_ordinal() -> None:
    assert _subject_parts("parliament_deputy_observation_alpha:3") == (
        "parliament_deputy_observation_alpha",
        3,
    )
    with pytest.raises(Exception, match="referência editorial"):
        _subject_parts("parliament_deputy_observation_alpha")
    with pytest.raises(Exception, match="posição do intervalo"):
        _subject_parts("parliament_deputy_observation_alpha:10001")


def test_mandate_publication_confirmation_rejects_any_changed_proof() -> None:
    payload = _payload()
    PoliticianMandatePublicationRepository._confirm_payload(
        case_id="case_alpha",
        preview=_preview(),
        payload=payload,
    )

    for field, changed in (
        ("expected_version_id", "version_beta"),
        ("expected_version_sha256", "e" * 64),
        ("expected_source_sha256", "e" * 64),
        ("expected_period_sha256", "e" * 64),
        ("expected_publication_proof_sha256", "e" * 64),
    ):
        with pytest.raises(EditorialConflictError):
            PoliticianMandatePublicationRepository._confirm_payload(
                case_id="case_alpha",
                preview=_preview(),
                payload=_payload(**{field: changed}),
            )


def test_mandate_publication_dates_remain_explicit_utc_values() -> None:
    starts_at = datetime(2025, 6, 3, tzinfo=UTC)
    assert starts_at.isoformat().endswith("+00:00")
