"""Cria um manifesto privado a partir de uma pasta parlamentar já inventariada."""

import argparse
import asyncio
import json

from app.core.config import Settings, get_settings
from app.repositories.parliament_resource_manifest import (
    ParliamentResourceManifestRepository,
    require_official_index_snapshot_id,
)
from app.services.http import OfficialHttpClient
from app.services.parliament_resource_manifest import (
    ParliamentResourceManifestCollector,
    ParliamentResourceManifestStager,
)
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    require_parliament_url,
    require_supported_parliament_legislature,
)


def validate_private_manifest_operation(settings: Settings, *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError("A persistência exige --confirm-private-staging")
    if settings.environment != "staging":
        raise RuntimeError("ENVIRONMENT tem de ser staging para persistir o manifesto parlamentar")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")


async def sync(
    *,
    catalogue_kind: ParliamentCatalogueKind,
    legislature: str,
    catalogue_snapshot_id: str,
    candidate_url: str,
    confirmed: bool,
) -> dict[str, object]:
    settings = get_settings()
    validate_private_manifest_operation(settings, confirmed=confirmed)
    exact_legislature = require_supported_parliament_legislature(legislature)
    exact_snapshot_id = require_official_index_snapshot_id(catalogue_snapshot_id)
    exact_candidate_url = require_parliament_url(candidate_url)

    repository = ParliamentResourceManifestRepository(settings)
    await repository.connect()
    try:
        await repository.require_catalogue_candidate(
            snapshot_id=exact_snapshot_id,
            catalogue_kind=catalogue_kind,
            legislature=exact_legislature,
            candidate_url=exact_candidate_url,
        )
        async with OfficialHttpClient(settings) as http:
            collection = await ParliamentResourceManifestCollector(http).collect(
                catalogue_kind=catalogue_kind,
                legislature=exact_legislature,
                parent_catalogue_snapshot_id=exact_snapshot_id,
                candidate_url=exact_candidate_url,
            )
        return await ParliamentResourceManifestStager(settings, repository).store(collection)
    finally:
        await repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Arquivar o manifesto privado de uma única pasta parlamentar",
    )
    parser.add_argument(
        "catalogue",
        choices=[item.value.lower() for item in ParliamentCatalogueKind],
    )
    parser.add_argument("legislature", help="Legislatura exata, por exemplo XVII")
    parser.add_argument("--catalogue-snapshot-id", required=True)
    parser.add_argument("--candidate-url", required=True)
    parser.add_argument(
        "--confirm-private-staging",
        action="store_true",
        help="Confirmar staging privado, sem descarga dos recursos nem publicação",
    )
    args = parser.parse_args()
    result = asyncio.run(
        sync(
            catalogue_kind=ParliamentCatalogueKind(args.catalogue.upper()),
            legislature=args.legislature,
            catalogue_snapshot_id=args.catalogue_snapshot_id,
            candidate_url=args.candidate_url,
            confirmed=args.confirm_private_staging,
        )
    )
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
