import pytest
from pydantic import ValidationError

from app.models.editorial import (
    AiDreRegenerationRequest,
    EditorialCaseCreateRequest,
    EditorialCorrectionRequest,
    EditorialDecisionRequest,
    ParliamentEditorialProposalRequest,
    ParliamentEditorialPublicationRequest,
    PoliticianProfileEditorialProposalRequest,
    PoliticianProfileSnapshotPublicationRequest,
)


def _case_payload(normalized_data: dict[str, object]) -> dict[str, object]:
    return {
        "kind": "PUBLIC_CONTRACT",
        "subject_type": "BASE_CONTRACT",
        "subject_id": "contrato-123",
        "source_document_id": "source_123",
        "normalized_data": normalized_data,
        "confirm_private_only": True,
    }


@pytest.mark.parametrize(
    "normalized_data",
    [
        {"nif": "123456789"},
        {"entidade": {"tax_id": "123456789"}},
        {"entidade": {"taxId": "123456789"}},
        {"numeroContribuinte": "123456789"},
        {"texto": "NIF 123 456 789"},
        {"identificador": 123456789},
        {"identificador": 123456789.0},
    ],
)
def test_editorial_payload_rejects_clear_protected_identifiers(
    normalized_data: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="NIF|NIPC"):
        EditorialCaseCreateRequest.model_validate(_case_payload(normalized_data))


def test_editorial_payload_accepts_only_labelled_hmac_digest() -> None:
    digest = "a" * 64
    payload = EditorialCaseCreateRequest.model_validate(
        _case_payload(
            {
                "titulo": "Contrato oficial",
                "protected_nipc_digest": digest,
                "dados_indisponiveis": ["prazo de execução"],
            }
        )
    )
    assert payload.normalized_data["protected_nipc_digest"] == digest


def test_editorial_case_requires_explicit_private_confirmation() -> None:
    data = _case_payload({"titulo": "Proposta"})
    data["confirm_private_only"] = False
    with pytest.raises(ValidationError):
        EditorialCaseCreateRequest.model_validate(data)


def test_correction_requires_object_and_meaningful_rationale() -> None:
    with pytest.raises(ValidationError):
        EditorialCorrectionRequest.model_validate(
            {
                "expected_revision": 2,
                "rationale": "curta",
                "normalized_data": {"titulo": "Versão dois"},
            }
        )


def test_identifiers_and_rationales_reject_whitespace_only_values() -> None:
    case_data = _case_payload({"titulo": "Proposta"})
    case_data["subject_id"] = "   "
    with pytest.raises(ValidationError, match="identificador"):
        EditorialCaseCreateRequest.model_validate(case_data)

    with pytest.raises(ValidationError, match="fundamentação"):
        EditorialDecisionRequest.model_validate({"expected_revision": 1, "rationale": " " * 20})


def test_parliament_proposal_accepts_only_scope_and_explicit_safety_confirmations() -> None:
    payload = ParliamentEditorialProposalRequest.model_validate(
        {
            "snapshot_id": "parliament_snapshot_123abc",
            "scope": "votes",
            "confirm_private_only": True,
            "confirm_no_individual_inference": True,
        }
    )
    assert payload.scope.value == "votes"

    for field in ("confirm_private_only", "confirm_no_individual_inference"):
        invalid = payload.model_dump()
        invalid[field] = False
        with pytest.raises(ValidationError):
            ParliamentEditorialProposalRequest.model_validate(invalid)

    with pytest.raises(ValidationError):
        ParliamentEditorialProposalRequest.model_validate(
            {
                **payload.model_dump(),
                "normalized_data": {"ator": "valor fornecido pelo browser"},
            }
        )


def test_politician_profile_proposal_accepts_only_an_observation_and_three_confirmations() -> None:
    payload = PoliticianProfileEditorialProposalRequest.model_validate(
        {
            "observation_id": "parliament_deputy_observation_123abc",
            "confirm_private_only": True,
            "confirm_exact_official_id_only": True,
            "confirm_no_mandate_inference": True,
        }
    )
    assert payload.observation_id == "parliament_deputy_observation_123abc"

    for field in (
        "confirm_private_only",
        "confirm_exact_official_id_only",
        "confirm_no_mandate_inference",
    ):
        invalid = payload.model_dump()
        invalid[field] = False
        with pytest.raises(ValidationError):
            PoliticianProfileEditorialProposalRequest.model_validate(invalid)

    with pytest.raises(ValidationError):
        PoliticianProfileEditorialProposalRequest.model_validate(
            {**payload.model_dump(), "normalized_data": {"name": "browser-controlled"}}
        )


def test_parliament_publication_requires_exact_proofs_and_three_confirmations() -> None:
    request = ParliamentEditorialPublicationRequest.model_validate(
        {
            "expected_revision": 3,
            "rationale": "Fonte e âmbito confirmados novamente antes da publicação.",
            "confirmed_scope": "activity",
            "expected_snapshot_id": "parliament_snapshot_123abc",
            "expected_source_sha256": "a" * 64,
            "expected_snapshot_sha256": "b" * 64,
            "expected_editorial_sha256": "c" * 64,
            "expected_publication_proof_sha256": "d" * 64,
            "confirm_source_reviewed": True,
            "confirm_no_individual_inference": True,
            "confirm_publication": True,
        }
    )
    assert request.confirmed_scope.value == "activity"

    for field in (
        "confirm_source_reviewed",
        "confirm_no_individual_inference",
        "confirm_publication",
    ):
        invalid = request.model_dump()
        invalid[field] = False
        with pytest.raises(ValidationError):
            ParliamentEditorialPublicationRequest.model_validate(invalid)

    invalid_hash = request.model_dump()
    invalid_hash["expected_source_sha256"] = "não-é-um-hash"
    with pytest.raises(ValidationError):
        ParliamentEditorialPublicationRequest.model_validate(invalid_hash)


def test_profile_snapshot_publication_requires_all_exact_proofs_and_confirmations() -> None:
    payload = {
        "expected_snapshot_id": "parliament_deputy_snapshot_123abc",
        "expected_source_sha256": "a" * 64,
        "expected_snapshot_sha256": "b" * 64,
        "expected_readiness_proof_sha256": "c" * 64,
        "expected_publication_proof_sha256": "d" * 64,
        "expected_deputy_count": 230,
        "rationale": "Fonte, fotografia e todas as decisões foram confirmadas novamente.",
        "public_rationale": "Fotografia parlamentar integral revista e publicada com prova.",
        "confirm_source_reviewed": True,
        "confirm_complete_snapshot": True,
        "confirm_exact_official_id_only": True,
        "confirm_no_mandate_inference": True,
        "confirm_no_party_inference": True,
        "confirm_publication": True,
    }
    request = PoliticianProfileSnapshotPublicationRequest.model_validate(payload)
    assert request.expected_deputy_count == 230

    for field in (
        "confirm_source_reviewed",
        "confirm_complete_snapshot",
        "confirm_exact_official_id_only",
        "confirm_no_mandate_inference",
        "confirm_no_party_inference",
        "confirm_publication",
    ):
        with pytest.raises(ValidationError):
            PoliticianProfileSnapshotPublicationRequest.model_validate({**payload, field: False})


def test_ai_regeneration_binds_the_reviewed_version_and_all_private_confirmations() -> None:
    payload = {
        "expected_revision": 2,
        "expected_current_version_sha256": "a" * 64,
        "rationale": "Nova proposta necessária para clarificar uma incerteza documentada.",
        "confirm_private_only": True,
        "confirm_archived_source_only": True,
        "confirm_ai_not_source": True,
        "confirm_new_immutable_version": True,
    }
    request = AiDreRegenerationRequest.model_validate(payload)
    assert request.expected_current_version_sha256 == "a" * 64

    for field in (
        "confirm_private_only",
        "confirm_archived_source_only",
        "confirm_ai_not_source",
        "confirm_new_immutable_version",
    ):
        invalid = {**payload, field: False}
        with pytest.raises(ValidationError):
            AiDreRegenerationRequest.model_validate(invalid)

    with pytest.raises(ValidationError):
        AiDreRegenerationRequest.model_validate(
            {**payload, "expected_current_version_sha256": "not-a-digest"}
        )
