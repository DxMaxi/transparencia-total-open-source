"""Valida um restauro isolado e produz uma atestação sem dados ou segredos."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from app.services.database_backup import (
    build_restore_attestation,
    read_json_object,
    sha256_file,
    write_json_object,
)


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ciphertext", type=Path, required=True)
    parser.add_argument("--object-key", required=True)
    parser.add_argument("--restored-inventory", type=Path, required=True)
    parser.add_argument("--archive-report", type=Path, required=True)
    parser.add_argument("--operational-report", type=Path, required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--completed-at", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--expected-ciphertext-sha256", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    attestation = build_restore_attestation(
        manifest=read_json_object(args.manifest),
        ciphertext_path=args.ciphertext,
        object_key=args.object_key,
        restored_inventory=read_json_object(args.restored_inventory),
        archive_report=read_json_object(args.archive_report),
        operational_report=read_json_object(args.operational_report),
        started_at=_instant(args.started_at),
        completed_at=_instant(args.completed_at),
        repository=args.repository,
        workflow_run_id=args.workflow_run_id,
        expected_ciphertext_sha256=args.expected_ciphertext_sha256,
        expected_manifest_sha256=args.expected_manifest_sha256,
        manifest_file_sha256=sha256_file(args.manifest),
    )
    write_json_object(args.output, attestation)
    print(
        f"Restauro {attestation['outcome']}: attestation_sha256={attestation['attestation_sha256']}"
    )


if __name__ == "__main__":
    main()
