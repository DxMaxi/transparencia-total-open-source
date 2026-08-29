import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.models.ept_declaration import (
    EptLegalAssessmentOutcome,
    EptLegalAssessmentRecordRequest,
)
from app.repositories.ept_declaration_publication import (
    EptDeclarationPublicationGateRepository,
    _identity_link_proof,
    _legal_assessment_proof,
    _publication_proof,
    _sha256_json,
)


def _core() -> dict[str, object]:
    normalized = {
        "schema_version": "ept-public-interest-editorial-v1",
        "candidate": {
            "official_declaration_id": "EPT-42",
            "source_record_sha256": "b" * 64,
            "declaration_type": "INTEREST_REGISTER",
        },
        "source_proof": {
            "content_sha256": "a" * 64,
            "official_identifier": "EPT-42",
            "url": "https://entidadetransparencia.pt/registos/EPT-42",
        },
        "legal_scope": {
            "scope": "PUBLIC_INTEREST_REGISTER_ONLY",
            "legal_control_is_not_automated": True,
        },
        "identity": {
            "status": "UNLINKED_PRIVATE",
            "name_matching_allowed": False,
            "fuzzy_matching_allowed": False,
        },
        "publication": {"public_projection_allowed": False},
    }
    return {
        "case_id": "case-ept",
        "case_kind": "POLITICIAN_PROFILE",
        "subject_type": "EPT_PUBLIC_INTEREST_OBSERVATION",
        "subject_id": "observation-ept",
        "case_state": "APPROVED",
        "case_revision": 3,
        "version_id": "version-ept",
        "version_sha256": _sha256_json(normalized),
        "normalized_json": normalized,
        "observation_id": "observation-ept",
        "official_declaration_id": "EPT-42",
        "declaration_type": "INTEREST_REGISTER",
        "declared_at": datetime(2026, 8, 1, tzinfo=UTC),
        "period_label": "2026",
        "public_access_scope": "PUBLIC_INTEREST_REGISTER",
        "legal_review_status": "REQUIRES_INDEPENDENT_LEGAL_REVIEW",
        "identity_link_status": "UNLINKED_PRIVATE",
        "source_record_sha256": "b" * 64,
        "official_subject_digest": "c" * 64,
        "source_id": "source-ept",
        "source_publisher": "TRANSPARENCY_ENTITY",
        "source_kind": "DECLARATION",
        "source_official_identifier": "EPT-42",
        "source_url": "https://entidadetransparencia.pt/registos/EPT-42",
        "source_retrieved_at": datetime(2026, 8, 1, tzinfo=UTC),
        "source_sha256": "a" * 64,
        "archive_id": "archive-ept",
        "archive_attestation_sha256": "d" * 64,
        "database_now": datetime(2026, 8, 29),
    }


def _legal() -> dict[str, object]:
    return {
        "id": "legal-ept",
        "observation_id": "observation-ept",
        "case_id": "case-ept",
        "assessment_scope": "PUBLIC_INTEREST_METADATA_ONLY",
        "outcome": "PERMITS_PUBLIC_INTEREST_METADATA_ONLY",
        "assessment_document_sha256": "e" * 64,
        "assessment_document_storage_backend": "BACKBLAZE_B2_ENCRYPTED",
        "assessment_document_byte_size": 1200,
        "assessment_document_mime_type": "application/pdf",
        "assessor_reference_sha256": "f" * 64,
        "qualification_evidence_sha256": "1" * 64,
        "conflict_check_sha256": "2" * 64,
        "assessed_at": datetime(2026, 8, 20, tzinfo=UTC),
        "valid_until": None,
        "recorded_by_id": "staff-admin",
        "recorded_by_alias": "administrador-publico",
        "created_at": datetime(2026, 8, 20, tzinfo=UTC),
    }


def _identity() -> dict[str, object]:
    return {
        "id": "identity-ept",
        "observation_id": "observation-ept",
        "case_id": "case-ept",
        "person_id": "person-ept",
        "evidence_document_id": "person-source",
        "official_subject_digest": "c" * 64,
        "person_source_id": "AR-100",
        "evidence_sha256": "3" * 64,
        "link_proof_sha256": _identity_link_proof(
            case_id="case-ept",
            observation_id="observation-ept",
            subject_digest="c" * 64,
            person_id="person-ept",
            person_source_id="AR-100",
            evidence_document_id="person-source",
            evidence_sha256="3" * 64,
        ),
    }


def test_core_gate_accepts_only_closed_ept_contract() -> None:
    assert EptDeclarationPublicationGateRepository._core_blockers(_core()) == []

    changed = _core()
    changed["source_url"] = "https://example.org/registo/EPT-42"
    changed["identity_link_status"] = "LINKED_BY_NAME"
    blockers = EptDeclarationPublicationGateRepository._core_blockers(changed)
    codes = {item["code"] for item in blockers}
    assert {"SOURCE_INVALID", "OBSERVATION_SCOPE_INVALID"}.issubset(codes)


def test_proofs_are_deterministic_and_exclude_raw_identifier() -> None:
    core = _core()
    legal = _legal()
    identity = _identity()
    proof = _publication_proof(
        core=core,
        legal=legal,
        identity=identity,
        declaration_id="ept-declaration",
    )
    assert proof == _publication_proof(
        core=core,
        legal=legal,
        identity=identity,
        declaration_id="ept-declaration",
    )
    assert len(proof) == 64
    assert len(_legal_assessment_proof(legal)) == 64
    assert "123456789" not in json.dumps({"proof": proof, "identity": identity})


def test_legal_assessment_request_rejects_invalid_period_and_plain_backend() -> None:
    now = datetime.now(UTC)
    base = {
        "expected_case_id": "case-ept",
        "expected_revision": 3,
        "expected_version_id": "version-ept",
        "expected_version_sha256": "a" * 64,
        "expected_observation_id": "observation-ept",
        "expected_source_sha256": "b" * 64,
        "expected_source_record_sha256": "c" * 64,
        "outcome": EptLegalAssessmentOutcome.PERMITS_PUBLIC_INTEREST_METADATA_ONLY,
        "assessment_document_sha256": "d" * 64,
        "assessment_document_storage_backend": "BACKBLAZE_B2_ENCRYPTED",
        "assessment_document_storage_key": "legal/parecer.pdf.age",
        "assessment_document_byte_size": 1000,
        "assessment_document_mime_type": "application/pdf",
        "assessor_reference_sha256": "e" * 64,
        "qualification_evidence_sha256": "f" * 64,
        "conflict_check_sha256": "1" * 64,
        "assessed_at": now,
        "valid_until": now - timedelta(days=1),
        "recording_rationale": "Registo conferido com o documento privado cifrado.",
        "confirm_external_human_assessment": True,
        "confirm_independent_assessor": True,
        "confirm_qualification_and_conflicts_checked": True,
        "confirm_public_interest_metadata_only": True,
        "confirm_document_encrypted_and_private": True,
        "confirm_system_did_not_issue_legal_opinion": True,
    }
    with pytest.raises(ValidationError, match="validade"):
        EptLegalAssessmentRecordRequest.model_validate(base)

    base["valid_until"] = now + timedelta(days=1)
    base["assessment_document_storage_backend"] = "LOCAL_PLAIN"
    with pytest.raises(ValidationError):
        EptLegalAssessmentRecordRequest.model_validate(base)
