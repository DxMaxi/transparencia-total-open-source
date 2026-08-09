"""Verifica manifesto, tamanho e SHA-256 antes de decifrar uma cópia."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.database_backup import (
    BackupEvidenceError,
    read_json_object,
    sha256_file,
    validate_backup_ciphertext,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ciphertext", type=Path, required=True)
    parser.add_argument("--object-key", required=True)
    parser.add_argument("--expected-ciphertext-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    observed_manifest_sha256 = sha256_file(args.manifest)
    if observed_manifest_sha256 != args.expected_manifest_sha256:
        raise BackupEvidenceError("SHA-256 do manifesto não corresponde à prova esperada")
    manifest = validate_backup_ciphertext(
        manifest=read_json_object(args.manifest),
        ciphertext_path=args.ciphertext,
        object_key=args.object_key,
        expected_ciphertext_sha256=args.expected_ciphertext_sha256,
    )
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "object_key": manifest["backup"]["object_key"],
                "ciphertext_sha256": manifest["backup"]["ciphertext_sha256"],
                "ciphertext_size_bytes": manifest["backup"]["ciphertext_size_bytes"],
                "manifest_file_sha256": observed_manifest_sha256,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
