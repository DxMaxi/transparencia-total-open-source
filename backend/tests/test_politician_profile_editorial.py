import json

from app.models.editorial import validate_normalized_data
from app.repositories.politician_profile_editorial import (
    PoliticianProfileEditorialRepository,
    _periods,
)


def _candidate() -> dict[str, object]:
    return {
        "observation_id": "parliament_deputy_observation_123456789",
        "source_document_id": "source_document_123456789",
        "snapshot_id": "parliament_deputy_snapshot_123456789",
        "official_deputy_id": "123456789",
        "official_candidate_id": "987654321",
        "parliamentary_name": "Pessoa Deputada",
        "full_name": "Pessoa Deputada de Teste",
        "legislature": "XVII",
        "constituency": {"source_id": "111222333", "label": "Porto"},
        "parliamentary_groups": [
            {
                "source_id": "444555666",
                "short_name": "GP",
                "starts_at": "2025-06-03T00:00:00Z",
                "ends_at": None,
            }
        ],
        "mandate_situations": [
            {
                "description": "Efetivo",
                "starts_at": "2025-06-03T00:00:00Z",
                "ends_at": None,
            }
        ],
        "offices": [
            {
                "source_id": "777888999",
                "title": "Membro de comissão",
                "starts_at": "2025-06-10T00:00:00Z",
                "ends_at": None,
            }
        ],
        "observation_sha256": "a" * 64,
        "snapshot": {
            "parser_version": "parliament-historical-deputies-v1",
            "normalised_sha256": "b" * 64,
            "collected_at": "2026-08-24T05:00:00Z",
        },
        "source": {
            "url": "https://www.parlamento.pt/dados/deputados.json",
            "retrieved_at": "2026-08-24T05:00:00Z",
            "content_sha256": "c" * 64,
        },
        "archive": {"attestation_sha256": "d" * 64, "byte_size": 4096},
        "manifest_counts": {
            "deputies": 1,
            "group_periods": 1,
            "situation_periods": 1,
            "office_periods": 1,
        },
        "materialised_counts": {
            "deputies": 1,
            "group_periods": 1,
            "situation_periods": 1,
            "office_periods": 1,
        },
        "warnings": [
            "Uma observação parlamentar não prova o início, fim ou continuidade de um mandato."
        ],
    }


def test_profile_proposal_hashes_every_technical_identifier_and_preserves_source_proof() -> None:
    candidate = _candidate()
    normalized = PoliticianProfileEditorialRepository._normalized_proposal(candidate)
    validate_normalized_data(normalized)
    serialized = json.dumps(normalized, ensure_ascii=False)

    for raw_identifier in (
        candidate["observation_id"],
        candidate["source_document_id"],
        candidate["snapshot_id"],
        candidate["official_deputy_id"],
        candidate["official_candidate_id"],
        "111222333",
        "444555666",
        "777888999",
    ):
        assert str(raw_identifier) not in serialized

    assert normalized["identity_rule"] == "EXACT_AR_DEP_ID_ONLY"
    assert normalized["mandate_inference_allowed"] is False
    assert normalized["publication"] == {
        "state": "PRIVATE_PENDING_REVIEW",
        "automatic_publication": False,
        "human_review_required": True,
        "person_creation_performed": False,
        "mandate_creation_performed": False,
        "membership_creation_performed": False,
    }
    assert normalized["source_proof"]["content_sha256"] == "c" * 64
    assert normalized["source_proof"]["archive_attestation_sha256"] == "d" * 64


def test_period_parser_preserves_but_flags_an_inverted_official_interval() -> None:
    periods, inverted, missing = _periods(
        [
            {
                "source_id": "office-1",
                "title": "Cargo observado",
                "starts_at": "2026-02-01T00:00:00Z",
                "ends_at": "2026-01-01T00:00:00Z",
            }
        ],
        label_key="title",
        identifier_key="source_id",
    )

    assert periods[0]["starts_at"] == "2026-02-01T00:00:00Z"
    assert periods[0]["ends_at"] == "2026-01-01T00:00:00Z"
    assert inverted == 1
    assert missing == 0
