"""Arquiva um único recurso parlamentar já provado pelo manifesto privado."""

import argparse
import asyncio
import json

from app.core.config import Settings, get_settings
from app.repositories.parliament_resource_archive import ParliamentResourceArchiveRepository
from app.repositories.parliament_resource_manifest import require_official_index_snapshot_id
from app.services.http import OfficialHttpClient
from app.services.parliament_resource_archive import (
    ParliamentResourceArchiveCollector,
    ParliamentResourceArchiveStager,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    require_parliament_url,
    require_supported_parliament_legislature,
)


def validate_private_archive_operation(settings: Settings, *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError("A persistência exige --confirm-private-staging")
    if settings.environment != "staging":
        raise RuntimeError("ENVIRONMENT tem de ser staging para arquivar o recurso parlamentar")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")


async def sync(
    *,
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
    resource_format: ParliamentResourceFormat,
    catalogue_snapshot_id: str,
    manifest_snapshot_id: str,
    resource_url: str,
    confirmed: bool,
) -> dict[str, object]:
    settings = get_settings()
    validate_private_archive_operation(settings, confirmed=confirmed)
    exact_legislature = require_supported_parliament_legislature(legislature)
    exact_catalogue_snapshot_id = require_official_index_snapshot_id(catalogue_snapshot_id)
    exact_manifest_snapshot_id = require_official_index_snapshot_id(manifest_snapshot_id)
    exact_resource_url = require_parliament_url(resource_url)

    repository = ParliamentResourceArchiveRepository(settings)
    await repository.connect()
    try:
        proof = await repository.require_resource_candidate(
            catalogue_snapshot_id=exact_catalogue_snapshot_id,
            manifest_snapshot_id=exact_manifest_snapshot_id,
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            resource_format=resource_format,
            resource_url=exact_resource_url,
        )
        async with OfficialHttpClient(settings) as http:
            collection = await ParliamentResourceArchiveCollector(
                http,
                max_bytes=settings.parlamento_votes_max_bytes,
            ).collect(proof)
        return await ParliamentResourceArchiveStager(settings, repository).store(collection)
    finally:
        await repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Arquivar um único recurso parlamentar privado, sem o interpretar",
    )
    parser.add_argument(
        "catalogue",
        choices=[item.value.lower() for item in ParliamentCatalogueKind],
    )
    parser.add_argument("legislature", help="Legislatura exata, por exemplo XVII")
    parser.add_argument(
        "resource_format",
        choices=[item.value.lower() for item in ParliamentResourceFormat],
    )
    parser.add_argument("--catalogue-snapshot-id", required=True)
    parser.add_argument("--manifest-snapshot-id", required=True)
    parser.add_argument("--resource-url", required=True)
    parser.add_argument(
        "--confirm-private-staging",
        action="store_true",
        help="Confirmar staging privado, sem normalização, revisão ou publicação",
    )
    args = parser.parse_args()
    result = asyncio.run(
        sync(
            catalogue_kind=ParliamentCatalogueKind(args.catalogue.upper()),
            legislature=args.legislature,
            resource_format=ParliamentResourceFormat(args.resource_format.upper()),
            catalogue_snapshot_id=args.catalogue_snapshot_id,
            manifest_snapshot_id=args.manifest_snapshot_id,
            resource_url=args.resource_url,
            confirmed=args.confirm_private_staging,
        )
    )
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
