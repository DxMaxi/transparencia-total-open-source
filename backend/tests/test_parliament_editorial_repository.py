import hashlib
import json

from app.models.editorial import ParliamentEditorialScope, validate_normalized_data
from app.repositories.parliament_editorial import ParliamentEditorialRepository


def test_normalized_proposal_hashes_technical_references_without_weakening_nif_guard() -> None:
    snapshot_id = "parliament_snapshot_506240538c837765b78a7f85"
    previous_snapshot_id = "parliament_snapshot_987654321abcdef012345678"
    source_document_id = "source_document_123456789abcdef012345678"
    candidate: dict[str, object] = {
        "snapshot_id": snapshot_id,
        "source_document_id": source_document_id,
        "legislature": "XVII",
        "parser_version": "parliament-open-data-v1",
        "normalised_sha256": "a" * 64,
        "collected_at": "2026-08-11T10:00:00Z",
        "previous_snapshot": {
            "id": previous_snapshot_id,
            "normalised_sha256": "b" * 64,
            "collected_at": "2026-08-10T10:00:00Z",
        },
        "source": {
            "url": "https://www.parlamento.pt/dados-oficiais.json",
            "retrieved_at": "2026-08-11T10:00:00Z",
            "content_sha256": "c" * 64,
        },
        "archive": {
            "attestation_sha256": "d" * 64,
            "byte_size": 2048,
        },
        "manifest_counts": {
            "sessions": 1,
            "initiatives": 2,
            "votes": 3,
            "vote_records": 4,
        },
        "coverage": {"unknown_actor_records": 1},
        "differences": {
            "status": "COMPARED_BY_EXACT_SOURCE_ID",
            "sessions": {"added": 0, "removed": 0, "changed": 1, "unchanged": 0},
            "initiatives": {"added": 1, "removed": 0, "changed": 0, "unchanged": 1},
            "votes": {"added": 1, "removed": 0, "changed": 1, "unchanged": 1},
        },
        "limitations": ["Dados indisponíveis permanecem explícitos."],
    }

    normalized = ParliamentEditorialRepository._normalized_proposal(
        candidate,
        ParliamentEditorialScope.ACTIVITY,
    )
    validate_normalized_data(normalized)
    serialized = json.dumps(normalized, ensure_ascii=False)

    assert snapshot_id not in serialized
    assert previous_snapshot_id not in serialized
    assert source_document_id not in serialized
    assert (
        normalized["snapshot"]["reference_sha256"]
        == hashlib.sha256(snapshot_id.encode("utf-8")).hexdigest()
    )
    assert (
        normalized["source_proof"]["source_document_reference_sha256"]
        == hashlib.sha256(source_document_id.encode("utf-8")).hexdigest()
    )
