"""Constrói o manifesto de uma cópia PostgreSQL já cifrada com age."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from app.services.database_backup import (
    build_backup_manifest,
    canonical_json_sha256,
    read_json_object,
    write_json_object,
)


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ciphertext", type=Path, required=True)
    parser.add_argument("--object-key", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--completed-at", required=True)
    parser.add_argument("--retain-until", required=True)
    parser.add_argument("--age-recipient", required=True)
    parser.add_argument("--age-version", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    parser.add_argument("--postgres-client", required=True)
    parser.add_argument("--inventory-before", type=Path, required=True)
    parser.add_argument("--inventory-after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_backup_manifest(
        ciphertext_path=args.ciphertext,
        object_key=args.object_key,
        started_at=_instant(args.started_at),
        completed_at=_instant(args.completed_at),
        retain_until=_instant(args.retain_until),
        age_recipient=args.age_recipient,
        age_version=args.age_version,
        git_sha=args.git_sha,
        repository=args.repository,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        postgres_client=args.postgres_client,
        inventory_before=read_json_object(args.inventory_before),
        inventory_after=read_json_object(args.inventory_after),
    )
    write_json_object(args.output, manifest)
    print(
        "Manifesto criado: "
        f"ciphertext_sha256={manifest['backup']['ciphertext_sha256']} "
        f"manifest_sha256={canonical_json_sha256(manifest)}"
    )


if __name__ == "__main__":
    main()
