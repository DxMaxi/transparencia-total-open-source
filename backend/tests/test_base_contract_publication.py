from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.editorial import (
    BaseContractPublicationRequest,
    BaseContractWithdrawalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.base_contract_publication import (
    BaseContractPublicationRepository,
    _publication_event_sha256,
)
from app.repositories.editorial import EditorialConflictError


def _publication_payload() -> dict[str, object]:
    return {
        "expected_revision": 3,
        "expected_case_id": "case_base_1",
        "expected_version_id": "version_base_1",
        "expected_version_sha256": "1" * 64,
        "expected_contract_snapshot_id": "snapshot_base_1",
        "expected_public_contract_id": "base_contract_1",
        "expected_official_contract_id_sha256": "2" * 64,
        "expected_source_sha256": "3" * 64,
        "expected_source_record_sha256": "4" * 64,
        "expected_publication_proof_sha256": "5" * 64,
        "rationale": "Fundamentação interna completa para publicar o contrato revisto.",
        "public_rationale": "Contrato factual publicado após revisão da fonte oficial.",
        "confirm_source_reviewed": True,
        "confirm_exact_official_contract_id": True,
        "confirm_no_party_publication": True,
        "confirm_no_identity_or_name_matching": True,
        "confirm_no_organisation_match_or_relationship_creation": True,
        "confirm_append_only_publication": True,
        "confirm_publication": True,
    }


@pytest.mark.parametrize(
    "confirmation",
    [
        "confirm_source_reviewed",
        "confirm_exact_official_contract_id",
        "confirm_no_party_publication",
        "confirm_no_identity_or_name_matching",
        "confirm_no_organisation_match_or_relationship_creation",
        "confirm_append_only_publication",
        "confirm_publication",
    ],
)
def test_base_publication_request_requires_every_explicit_safety_confirmation(
    confirmation: str,
) -> None:
    unsafe = _publication_payload()
    unsafe[confirmation] = False
    with pytest.raises(ValidationError):
        BaseContractPublicationRequest.model_validate(unsafe)


def test_base_publication_request_rejects_unexpected_publication_fields() -> None:
    extra = _publication_payload()
    extra["party_ids"] = ["party_1"]
    with pytest.raises(ValidationError):
        BaseContractPublicationRequest.model_validate(extra)


def _withdrawal_payload() -> dict[str, object]:
    return {
        "expected_revision": 4,
        "expected_case_id": "case_base_1",
        "expected_version_id": "version_base_1",
        "expected_version_sha256": "1" * 64,
        "expected_public_contract_id": "base_contract_1",
        "expected_publication_snapshot_id": "publication_snapshot_1",
        "expected_source_sha256": "2" * 64,
        "expected_source_record_sha256": "3" * 64,
        "expected_publication_proof_sha256": "4" * 64,
        "expected_withdrawal_proof_sha256": "5" * 64,
        "expected_public_review_id": "review_1",
        "expected_publication_audit_event_id": "audit_1",
        "expected_publication_event_id": "event_1",
        "expected_publication_event_sha256": "6" * 64,
        "expected_public_effect_sha256": "7" * 64,
        "reason_category": "OFFICIAL_SOURCE_CORRECTION",
        "rationale": "Fundamentação interna completa para retirar sem apagar o histórico.",
        "public_rationale": "Contrato retirado enquanto a correção oficial é verificada.",
        "confirm_no_selective_removal": True,
        "confirm_public_effect_reviewed": True,
        "confirm_history_and_right_of_reply_preserved": True,
        "confirm_withdrawal": True,
    }


@pytest.mark.parametrize(
    "confirmation",
    [
        "confirm_no_selective_removal",
        "confirm_public_effect_reviewed",
        "confirm_history_and_right_of_reply_preserved",
        "confirm_withdrawal",
    ],
)
def test_base_withdrawal_requires_every_preservation_confirmation(
    confirmation: str,
) -> None:
    payload = _withdrawal_payload()
    payload[confirmation] = False
    with pytest.raises(ValidationError):
        BaseContractWithdrawalRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("request_type", "payload_factory"),
    [
        (BaseContractPublicationRequest, _publication_payload),
        (BaseContractWithdrawalRequest, _withdrawal_payload),
    ],
)
@pytest.mark.parametrize("field", ["rationale", "public_rationale"])
@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Fundamentação indevida que expõe o NIF 123 456 789 no histórico.",
        "Fundamentação indevida que expõe um HMAC-SHA256 protegido no histórico.",
    ],
)
def test_base_publication_narratives_reject_protected_identifiers(
    request_type: type[BaseContractPublicationRequest] | type[BaseContractWithdrawalRequest],
    payload_factory: object,
    field: str,
    unsafe_text: str,
) -> None:
    assert callable(payload_factory)
    payload = payload_factory()
    payload[field] = unsafe_text
    with pytest.raises(ValidationError, match="NIF/NIPC|HMAC"):
        request_type.model_validate(payload)


def test_base_publication_event_hash_binds_target_action_actor_and_time() -> None:
    values = {
        "event_id": "event_1",
        "case_id": "case_1",
        "version_id": "version_1",
        "action": "PUBLISH",
        "target_id": "base_contract_1",
        "rationale": "Contrato factual publicado após revisão humana da fonte oficial.",
        "actor_id": "staff_1",
        "actor_alias": "revisor-publico",
        "created_at": datetime(2026, 9, 1, 10, 30),
    }
    digest = _publication_event_sha256(**values)
    assert len(digest) == 64
    assert _publication_event_sha256(**values) == digest
    mutations = {
        "event_id": "event_2",
        "case_id": "case_2",
        "version_id": "version_2",
        "action": "WITHDRAW",
        "target_id": "base_contract_2",
        "rationale": "Outra fundamentação pública factual e suficientemente longa.",
        "actor_id": "staff_2",
        "actor_alias": "outro-revisor",
        "created_at": datetime(2026, 9, 1, 10, 31),
    }
    for field, value in mutations.items():
        assert _publication_event_sha256(**{**values, field: value}) != digest


def test_base_publication_repository_requires_admin_and_mfa() -> None:
    reviewer = StaffSession(
        staff_id="staff_1",
        auth_user_id=uuid4(),
        public_alias="revisor-publico",
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )
    with pytest.raises(EditorialConflictError, match="administrador"):
        BaseContractPublicationRepository._require_admin(
            reviewer,
            action="publicação",
        )

    admin_without_mfa = reviewer.model_copy(
        update={"role": StaffRole.ADMIN, "assurance_level": "aal1", "mfa_required": True}
    )
    with pytest.raises(EditorialConflictError, match="multifator"):
        BaseContractPublicationRepository._require_admin(
            admin_without_mfa,
            action="publicação",
        )
