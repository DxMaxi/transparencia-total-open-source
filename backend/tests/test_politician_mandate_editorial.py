import json
from datetime import UTC, datetime

from app.models.editorial import validate_normalized_data
from app.repositories.politician_mandate_editorial import (
    PoliticianMandateEditorialRepository,
)


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
            "description": "Efetivo",
            "starts_at": "2025-06-03T00:00:00Z",
            "ends_at": None,
        },
        "period_ordinal": 1,
        "legislature": "XVII",
        "parser_version": "parliament-historical-deputies-v1",
        "normalised_sha256": "a" * 64,
        "collected_at": datetime(2026, 8, 24, tzinfo=UTC),
        "manifest_deputy_count": 1,
        "manifest_group_period_count": 1,
        "manifest_situation_period_count": 1,
        "manifest_office_period_count": 0,
        "deputy_count": 1,
        "group_period_count": 1,
        "situation_period_count": 1,
        "office_period_count": 0,
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


def test_mandate_candidate_requires_exact_identity_dates_circle_and_manifest() -> None:
    candidate = PoliticianMandateEditorialRepository._candidate(_row())

    assert candidate["proposal_eligible"] is True
    assert candidate["identity_publication_ready"] is True
    assert candidate["blocked_reasons"] == []
    assert candidate["public_projection_allowed"] is False
    assert candidate["party_inference_allowed"] is False
    assert len(str(candidate["source_period_sha256"])) == 64


def test_mandate_candidate_fails_closed_on_missing_or_contradictory_proof() -> None:
    candidate = PoliticianMandateEditorialRepository._candidate(
        _row(
            constituency_source_id=None,
            person_publishable=False,
            period={
                "description": "Renunciou",
                "starts_at": "2025-07-03T00:00:00Z",
                "ends_at": "2025-06-03T00:00:00Z",
            },
        )
    )

    assert candidate["proposal_eligible"] is False
    blockers = " ".join(candidate["blocked_reasons"])  # type: ignore[arg-type]
    assert "exercício elegível" in blockers
    assert "data final antecede" in blockers
    assert "círculo" in blockers
    assert "revisão pública" in blockers


def test_mandate_proposal_hashes_internal_ids_and_preserves_exact_period_proof() -> None:
    candidate = PoliticianMandateEditorialRepository._candidate(_row())
    normalized = PoliticianMandateEditorialRepository._normalized_proposal(candidate)
    validate_normalized_data(normalized)
    serialized = json.dumps(normalized, ensure_ascii=False)

    for raw_identifier in (
        candidate["observation_id"],
        candidate["source_document_id"],
        candidate["snapshot_id"],
        candidate["official_deputy_id"],
        "circle-porto",
    ):
        assert str(raw_identifier) not in serialized

    assert normalized["identity_rule"] == "EXACT_AR_DEP_ID_ONLY"
    assert normalized["period_semantics"] == "HUMAN_REVIEW_REQUIRED"
    assert normalized["public_projection_allowed"] is False
    assert normalized["party_inference_allowed"] is False
    assert (
        normalized["mandate_candidate"]["source_period_sha256"] == candidate["source_period_sha256"]
    )
    assert normalized["publication"]["mandate_creation_performed"] is False
