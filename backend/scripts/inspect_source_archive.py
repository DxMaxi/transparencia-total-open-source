"""Verifica em privado uma atestação e o respetivo objeto sem escrever dados."""

import argparse
import asyncio
import json
from typing import Any

from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository
from app.services.raw_archive import (
    ContentAddressedFileArchive,
    RawArchiveConfigurationError,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-document-id", required=True)
    return parser.parse_args()


async def inspect(source_document_id: str) -> dict[str, Any]:
    settings = get_settings()
    repository = PostgresRepository(settings)
    await repository.connect()
    try:
        report = await repository.inspect_source_archive_attestation(
            source_document_id=source_document_id,
        )
    finally:
        await repository.close()

    archive_metadata = report["archive"]
    if not isinstance(archive_metadata, dict):
        report["object_verification"] = {
            "status": "UNAVAILABLE",
            "detail": "Não existe atestação de arquivo para este SourceDocument.",
        }
        report["availability"] = "UNAVAILABLE"
        return report
    if archive_metadata["storage_backend"] != "FILESYSTEM":
        report["object_verification"] = {
            "status": "UNAVAILABLE",
            "detail": "O backend desta atestação não está disponível neste processo.",
        }
        report["availability"] = "UNAVAILABLE"
        return report

    try:
        archive = ContentAddressedFileArchive.from_settings(settings)
    except RawArchiveConfigurationError as exc:
        report["object_verification"] = {
            "status": "UNAVAILABLE",
            "detail": str(exc),
        }
        report["availability"] = "UNAVAILABLE"
        return report

    verification = archive.verify(
        storage_key=str(archive_metadata["storage_key"]),
        expected_sha256=str(archive_metadata["content_sha256"]),
        expected_byte_size=int(archive_metadata["byte_size"]),
    )
    report["object_verification"] = verification.model_dump(mode="json")
    report["availability"] = verification.status
    report["checks"]["archive_object_verified"] = verification.status == "VERIFIED"
    return report


async def run(args: argparse.Namespace) -> None:
    report = await inspect(args.source_document_id)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
