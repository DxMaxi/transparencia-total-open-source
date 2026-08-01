import json
import secrets
from datetime import UTC, datetime

from app.core.security import sha256_text
from app.models.api import RightOfReplyReceipt, RightOfReplyRequest


def build_right_of_reply_receipt(
    payload: RightOfReplyRequest,
    *,
    submitted_at: datetime | None = None,
    random_token: str | None = None,
) -> RightOfReplyReceipt:
    timestamp = submitted_at or datetime.now(UTC)
    statement_sha256 = sha256_text(payload.statement_text)
    token = (random_token or secrets.token_hex(6)).upper()
    public_reference = f"DR-{timestamp.year}-{token}"
    canonical = json.dumps(
        {
            "public_reference": public_reference,
            "target_type": payload.target_type,
            "target_id": payload.target_id,
            "original_record_sha256": payload.original_record_sha256,
            "claimant_public_name": payload.claimant_public_name,
            "claimant_role": payload.claimant_role,
            "statement_sha256": statement_sha256,
            "official_response_url": (
                str(payload.official_response_url) if payload.official_response_url else None
            ),
            "submitted_at": timestamp.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return RightOfReplyReceipt(
        public_reference=public_reference,
        target_type=payload.target_type,
        target_id=payload.target_id,
        statement_sha256=statement_sha256,
        audit_sha256=sha256_text(canonical),
        submitted_at=timestamp,
    )
