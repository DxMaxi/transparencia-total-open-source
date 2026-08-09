"""Autoriza uma Application Key B2 e confirma o seu âmbito mínimo antes de a usar."""

from __future__ import annotations

import argparse
import json
import os

from app.services.b2_credentials import (
    KEY_CAPABILITIES_BY_ROLE,
    B2CredentialScopeError,
    authorize_b2_application_key,
    validate_b2_application_key_scope,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=sorted(KEY_CAPABILITIES_BY_ROLE), required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--s3-endpoint", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    application_key_id = os.environ.get("B2_KEY_ID", "")
    application_key = os.environ.get("B2_APPLICATION_KEY", "")
    if not application_key_id or not application_key:
        raise B2CredentialScopeError(
            "B2_KEY_ID e B2_APPLICATION_KEY são obrigatórias apenas no ambiente"
        )

    authorization = authorize_b2_application_key(
        application_key_id=application_key_id,
        application_key=application_key,
    )
    scope = validate_b2_application_key_scope(
        authorization,
        role=args.role,
        expected_bucket=args.bucket,
        expected_prefix=args.prefix,
        expected_s3_endpoint=args.s3_endpoint,
    )
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "role": scope["role"],
                "bucket_restriction": "VERIFIED",
                "name_prefix": scope["name_prefix"],
                "capabilities": scope["capabilities"],
                "eu_endpoint": "VERIFIED",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
