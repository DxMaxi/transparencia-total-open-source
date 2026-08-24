"""Normaliza privadamente um único arquivo JSON de iniciativas parlamentares."""

import argparse
import asyncio
import json

from app.core.config import Settings, get_settings
from app.repositories.parliament_resource_manifest import require_official_index_snapshot_id
from app.repositories.parliament_resource_normalization import (
    ParliamentResourceNormalizationRepository,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_resource_normalization import (
    ParliamentResourceNormalizationStager,
    ParliamentResourceNormalizer,
)
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    require_parliament_url,
    require_supported_parliament_legislature,
)


def validate_private_normalization_operation(settings: Settings, *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError("A persistência exige --confirm-private-staging")
    if settings.environment != "staging":
        raise RuntimeError("ENVIRONMENT tem de ser staging para normalizar o recurso parlamentar")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")


async def sync(
    *,
    legislature: str,
    catalogue_snapshot_id: str,
    manifest_snapshot_id: str,
    archive_snapshot_id: str,
    resource_url: str,
    confirmed: bool,
) -> dict[str, object]:
    settings = get_settings()
    validate_private_normalization_operation(settings, confirmed=confirmed)
    exact_legislature = require_supported_parliament_legislature(legislature)
    exact_catalogue_snapshot_id = require_official_index_snapshot_id(catalogue_snapshot_id)
    exact_manifest_snapshot_id = require_official_index_snapshot_id(manifest_snapshot_id)
    exact_archive_snapshot_id = require_official_index_snapshot_id(archive_snapshot_id)
    exact_resource_url = require_parliament_url(resource_url)

    repository = ParliamentResourceNormalizationRepository(settings)
    await repository.connect()
    try:
        proof = await repository.require_archived_resource(
            catalogue_snapshot_id=exact_catalogue_snapshot_id,
            manifest_snapshot_id=exact_manifest_snapshot_id,
            archive_snapshot_id=exact_archive_snapshot_id,
            catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
            legislature=exact_legislature,
            resource_format=ParliamentResourceFormat.JSON,
            resource_url=exact_resource_url,
        )
        collection = ParliamentResourceNormalizer().normalise(proof)
        return await ParliamentResourceNormalizationStager(settings, repository).store(collection)
    finally:
        await repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalizar um único arquivo JSON de iniciativas, sem criar revisão",
    )
    parser.add_argument("legislature", help="Legislatura exata, por exemplo XVII")
    parser.add_argument("--catalogue-snapshot-id", required=True)
    parser.add_argument("--manifest-snapshot-id", required=True)
    parser.add_argument("--archive-snapshot-id", required=True)
    parser.add_argument("--resource-url", required=True)
    parser.add_argument(
        "--confirm-private-staging",
        action="store_true",
        help="Confirmar staging privado, sem revisão ou publicação",
    )
    args = parser.parse_args()
    result = asyncio.run(
        sync(
            legislature=args.legislature,
            catalogue_snapshot_id=args.catalogue_snapshot_id,
            manifest_snapshot_id=args.manifest_snapshot_id,
            archive_snapshot_id=args.archive_snapshot_id,
            resource_url=args.resource_url,
            confirmed=args.confirm_private_staging,
        )
    )
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
