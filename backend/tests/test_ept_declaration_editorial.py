import hashlib
import json
from datetime import UTC, datetime

from app.models.editorial import validate_normalized_data
from app.repositories.ept_declaration_editorial import EptDeclarationEditorialRepository


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _row(**overrides: object) -> dict[str, object]:
    retrieved_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    row: dict[str, object] = {
        "observation_id": "ept_interest_alpha",
        "official_declaration_id": "DU-42",
        "official_subject_digest": "d" * 64,
        "public_subject_name": "Pessoa Titular",
        "declaration_type": "INTEREST_REGISTER",
        "declared_at": datetime(2026, 7, 1, tzinfo=UTC),
        "period_label": "2026",
        "public_access_scope": "PUBLIC_INTEREST_REGISTER",
        "legal_review_status": "REQUIRES_INDEPENDENT_LEGAL_REVIEW",
        "identity_link_status": "UNLINKED_PRIVATE",
        "source_document_id": "source-ept-alpha",
        "observed_at": retrieved_at,
        "source_title": "Registo público de interesses",
        "source_official_identifier": "DU-42",
        "source_url": "https://entidadetransparencia.pt/registo/DU-42",
        "source_retrieved_at": retrieved_at,
        "source_sha256": "a" * 64,
        "source_mime_type": "application/pdf",
        "storage_backend": "B2_EU",
        "byte_size": 4096,
        "archived_at": retrieved_at,
        "attestation_sha256": "b" * 64,
        "case_id": None,
        "case_state": None,
        "case_revision": None,
        "case_origin": None,
    }
    source_record = {
        "schema_version": "ept-public-interest-observation-v1",
        "official_declaration_id": row["official_declaration_id"],
        "official_subject_digest": row["official_subject_digest"],
        "public_subject_name": row["public_subject_name"],
        "declaration_type": row["declaration_type"],
        "declared_at": "2026-07-01T00:00:00Z",
        "period_label": row["period_label"],
        "public_access_scope": row["public_access_scope"],
        "legal_review_status": row["legal_review_status"],
        "identity_link_status": row["identity_link_status"],
        "source_document_id": row["source_document_id"],
        "source_content_sha256": row["source_sha256"],
    }
    row["source_record_sha256"] = hashlib.sha256(
        _canonical(source_record).encode("utf-8")
    ).hexdigest()
    row.update(overrides)
    return row


def test_candidate_is_private_unlinked_and_eligible_for_review() -> None:
    candidate = EptDeclarationEditorialRepository._candidate(_row())

    assert candidate["proposal_eligible"] is True
    assert candidate["blocked_reasons"] == []
    assert candidate["public_projection_allowed"] is False
    assert candidate["person_link_allowed"] is False
    assert candidate["name_matching_allowed"] is False
    assert candidate["income_or_asset_content_present"] is False
    assert "official_subject_digest" not in candidate


def test_candidate_rejects_portal_or_scope_drift() -> None:
    candidate = EptDeclarationEditorialRepository._candidate(
        _row(
            source_url="https://entidadetransparencia.pt/",
            public_access_scope="CONTROLLED_ASSET_ACCESS",
        )
    )

    assert candidate["proposal_eligible"] is False
    blockers = " ".join(candidate["blocked_reasons"])  # type: ignore[arg-type]
    assert "âmbito público" in blockers
    assert "domínio oficial autorizado" in blockers
    assert "hash da observação" in blockers


def test_candidate_rejects_non_ept_https_domain() -> None:
    candidate = EptDeclarationEditorialRepository._candidate(
        _row(source_url="https://example.org/registo/DU-42")
    )

    assert candidate["proposal_eligible"] is False
    assert "domínio oficial autorizado" in " ".join(  # type: ignore[arg-type]
        candidate["blocked_reasons"]
    )


def test_normalized_proposal_contains_no_hmac_or_publication_side_effect() -> None:
    candidate = EptDeclarationEditorialRepository._candidate(_row())
    normalized = EptDeclarationEditorialRepository._normalized_proposal(candidate)
    validate_normalized_data(normalized)
    serialized = json.dumps(normalized, ensure_ascii=False)

    assert "d" * 64 not in serialized
    assert "source-ept-alpha" not in serialized
    assert normalized["legal_scope"]["scope"] == "PUBLIC_INTEREST_REGISTER_ONLY"  # type: ignore[index]
    assert normalized["identity"]["status"] == "UNLINKED_PRIVATE"  # type: ignore[index]
    assert normalized["publication"]["public_projection_allowed"] is False  # type: ignore[index]
    assert normalized["publication"]["data_publication_review_created"] is False  # type: ignore[index]
