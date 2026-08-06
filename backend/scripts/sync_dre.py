"""Recolhe um diploma DRE, arquiva os bytes e persiste apenas em staging privado."""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.repositories.dre_staging import DreStagingRepository
from app.services.dre import DreCollector
from app.services.http import OfficialHttpClient
from app.services.raw_archive import ContentAddressedFileArchive


async def sync(source_url: str, *, code_version: str, confirm_staging: bool) -> dict[str, object]:
    settings = get_settings()
    if not confirm_staging:
        raise RuntimeError("A persistência DRE exige --confirm-staging")
    if settings.environment not in {"test", "staging"}:
        raise RuntimeError("ENVIRONMENT tem de ser test ou staging para persistir DRE")

    async with OfficialHttpClient(settings) as http:
        document = await DreCollector(settings, http).fetch_document(source_url)
    if document.raw_document is None:
        raise RuntimeError("O coletor DRE não devolveu os bytes privados oficiais")

    archive = ContentAddressedFileArchive.from_settings(settings)
    receipt = archive.archive(document.raw_document)
    verification = archive.verify(
        storage_key=receipt.storage_key,
        expected_sha256=receipt.content_sha256,
        expected_byte_size=receipt.byte_size,
    )
    if verification.status != "VERIFIED":
        raise RuntimeError(f"O arquivo DRE não ficou verificável: {verification.detail}")

    repository = DreStagingRepository(settings)
    await repository.connect()
    try:
        result = await repository.store_dre_document(
            document,
            code_version=code_version,
            archive_receipt=receipt,
        )
    finally:
        await repository.close()

    return {
        **result,
        "source_url": str(document.source_url),
        "content_sha256": document.content_sha256,
        "normalised_text_sha256": document.normalised_text_sha256,
        "official_identifier": document.official_identifier,
        "text_length": len(document.text),
        "archive_storage_key": receipt.storage_key,
        "archive_status": verification.status,
        "publishable": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_url")
    parser.add_argument("--code-version", required=True)
    parser.add_argument("--confirm-staging", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                sync(
                    args.source_url,
                    code_version=args.code_version,
                    confirm_staging=args.confirm_staging,
                )
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
