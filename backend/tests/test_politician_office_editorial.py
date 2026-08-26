import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.editorial import PoliticianOfficeEditorialProposalRequest, validate_normalized_data
from app.repositories.politician_office_editorial import PoliticianOfficeEditorialRepository


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "observation_id": "parliament_deputy_observation_alpha",
        "source_document_id": "source_document_alpha",
        "snapshot_id": "parliament_deputy_snapshot_alpha",
        "source_id": "dep-alpha",
        "parliamentary_name": "Pessoa Deputada",
        "full_name": "Pessoa Deputada de Teste",
        "constituency_source_id": "circle-porto",
        "constituency_label": "Porto",
        "period": {
            "source_id": "office-alpha",
            "title": "Membro de comissão",
            "starts_at": "2025-06-10T00:00:00Z",
            "ends_at": None,
        },
        "period_ordinal": 1,
        "legislature": "XVII",
        "parser_version": "parliament-historical-deputies-v1",
        "normalised_sha256": "a" * 64,
        "collected_at": datetime(2026, 8, 24, tzinfo=UTC),
        "manifest_deputy_count": 1,
        "manifest_group_period_count": 0,
        "manifest_situation_period_count": 0,
        "manifest_office_period_count": 1,
        "deputy_count": 1,
        "group_period_count": 0,
        "situation_period_count": 0,
        "office_period_count": 1,
        "source_title": "Atividade oficial dos deputados",
        "official_identifier": "AtividadeDeputadoXVII_json.txt",
        "source_url": "https://www.parlamento.pt/dados/deputados.json",
        "source_retrieved_at": datetime(2026, 8, 24, tzinfo=UTC),
        "source_sha256": "b" * 64,
        "source_mime_type": "application/json",
        "storage_backend": "B2_EU",
        "byte_size": 4096,
        "archived_at": datetime(2026, 8, 24, tzinfo=UTC),
        "attestation_sha256": "c" * 64,
        "person_id": "person-alpha",
        "membership_id": "membership-alpha",
        "person_publishable": True,
        "person_reviewed_at": datetime(2026, 8, 24, tzinfo=UTC),
        "case_id": None,
        "case_state": None,
        "case_revision": None,
        "case_origin": None,
    }
    row.update(overrides)
    return row


def _request(**overrides: object) -> PoliticianOfficeEditorialProposalRequest:
    payload: dict[str, object] = {
        "observation_id": "observation-alpha",
        "source_period_sha256": "d" * 64,
        "confirm_private_only": True,
        "confirm_exact_official_ids_only": True,
        "confirm_observed_period_requires_human_review": True,
        "confirm_no_mandate_or_party_inference": True,
    }
    payload.update(overrides)
    return PoliticianOfficeEditorialProposalRequest.model_validate(payload)


def test_office_request_is_strict_and_requires_every_confirmation() -> None:
    assert _request().confirm_private_only is True
    with pytest.raises(ValidationError):
        _request(confirm_exact_official_ids_only=False)
    with pytest.raises(ValidationError):
        _request(source_period_sha256="D" * 64)
    with pytest.raises(ValidationError):
        _request(unexpected=True)


def test_office_candidate_requires_exact_ids_period_circle_identity_and_manifest() -> None:
    candidate = PoliticianOfficeEditorialRepository._candidate(_row())

    assert candidate["proposal_eligible"] is True
    assert candidate["identity_publication_ready"] is True
    assert candidate["blocked_reasons"] == []
    assert candidate["public_projection_allowed"] is False
    assert candidate["mandate_inference_allowed"] is False
    assert candidate["party_inference_allowed"] is False
    assert len(str(candidate["source_period_sha256"])) == 64


def test_office_candidate_fails_closed_on_missing_or_contradictory_proof() -> None:
    candidate = PoliticianOfficeEditorialRepository._candidate(
        _row(
            constituency_source_id=None,
            person_publishable=False,
            period={
                "source_id": None,
                "title": "Membro de comissão",
                "starts_at": "2025-07-10T00:00:00Z",
                "ends_at": "2025-06-10T00:00:00Z",
            },
        )
    )

    assert candidate["proposal_eligible"] is False
    blockers = " ".join(candidate["blocked_reasons"])  # type: ignore[arg-type]
    assert "CarId" in blockers
    assert "data final antecede" in blockers
    assert "círculo" in blockers
    assert "revisão pública" in blockers


def test_office_proposal_hashes_ids_and_preserves_exact_official_period() -> None:
    candidate = PoliticianOfficeEditorialRepository._candidate(_row())
    normalized = PoliticianOfficeEditorialRepository._normalized_proposal(candidate)
    validate_normalized_data(normalized)
    serialized = json.dumps(normalized, ensure_ascii=False)

    for raw_identifier in (
        candidate["observation_id"],
        candidate["source_document_id"],
        candidate["snapshot_id"],
        candidate["official_deputy_id"],
        "circle-porto",
        "office-alpha",
    ):
        assert str(raw_identifier) not in serialized

    assert normalized["identity_rule"] == "EXACT_AR_DEP_ID_ONLY"
    assert normalized["office_rule"] == "EXACT_AR_CAR_ID_ONLY"
    assert normalized["period_semantics"] == "HUMAN_REVIEW_REQUIRED"
    assert normalized["public_projection_allowed"] is False
    assert normalized["mandate_inference_allowed"] is False
    assert normalized["party_inference_allowed"] is False
    assert (
        normalized["office_candidate"]["source_period_sha256"] == candidate["source_period_sha256"]
    )
    assert normalized["publication"]["office_creation_performed"] is False
    assert normalized["publication"]["mandate_creation_performed"] is False
