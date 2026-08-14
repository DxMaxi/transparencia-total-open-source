from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.security import sha256_text
from app.models.api import RightOfReplyRequest
from app.services.right_of_reply import build_right_of_reply_receipt


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "target_type": "POLITICIAN_PROFILE",
        "target_id": "perfil-123",
        "original_record_sha256": "a" * 64,
        "claimant_public_name": "Pessoa Respondente",
        "claimant_role": "Representante legal",
        "statement_text": "Esta é uma declaração pública suficientemente detalhada.",
        "official_response_url": "https://example.org/resposta",
        "legitimacy_confirmed": True,
    }
    payload.update(overrides)
    return payload


def test_right_of_reply_accepts_only_the_public_target_vocabulary() -> None:
    request = RightOfReplyRequest.model_validate(valid_payload())
    assert request.target_type == "POLITICIAN_PROFILE"

    with pytest.raises(ValidationError):
        RightOfReplyRequest.model_validate(valid_payload(target_type="ARBITRARY_RECORD"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("legitimacy_confirmed", False),
        ("official_response_url", "http://example.org/resposta"),
        ("official_response_url", "https://user:secret@example.org/resposta"),
        ("statement_text", " " * 40),
    ],
)
def test_right_of_reply_rejects_unsafe_or_incomplete_input(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        RightOfReplyRequest.model_validate(valid_payload(**{field: value}))


def test_right_of_reply_allows_an_omitted_official_url() -> None:
    request = RightOfReplyRequest.model_validate(
        valid_payload(official_response_url=None),
    )
    assert request.official_response_url is None


def test_right_of_reply_receipt_is_deterministic_for_a_fixed_submission() -> None:
    request = RightOfReplyRequest.model_validate(valid_payload())
    submitted_at = datetime(2026, 8, 14, 1, 30, tzinfo=UTC)

    receipt = build_right_of_reply_receipt(
        request,
        submitted_at=submitted_at,
        random_token="abc123",
    )

    assert receipt.public_reference == "DR-2026-ABC123"
    assert receipt.statement_sha256 == sha256_text(request.statement_text)
    assert len(receipt.audit_sha256) == 64
    assert receipt.submitted_at == submitted_at
    assert receipt.status == "RECEIVED"
