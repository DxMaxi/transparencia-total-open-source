import pytest
from pydantic import ValidationError

from app.models.editorial import (
    EditorialCaseCreateRequest,
    EditorialCorrectionRequest,
    EditorialDecisionRequest,
    ParliamentEditorialProposalRequest,
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
