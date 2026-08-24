"""Arquiva um catálogo parlamentar como inventário privado de staging.

Esta operação exige uma escolha explícita de catálogo e uma confirmação própria.
Não descarrega os recursos candidatos, não cria propostas editoriais e não publica.
"""

import argparse
import asyncio
import json

from app.core.config import Settings, get_settings
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.http import OfficialHttpClient
from app.services.parliament_source_catalogue import (
    ParliamentCatalogueKind,
    ParliamentSourceCatalogueCollector,
    ParliamentSourceCatalogueStager,
)


def validate_private_staging_operation(settings: Settings, *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError("A persistência exige --confirm-private-staging")
    if settings.environment != "staging":
        raise RuntimeError("ENVIRONMENT tem de ser staging para persistir o catálogo parlamentar")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")


async def sync(catalogue_kind: ParliamentCatalogueKind, *, confirmed: bool) -> dict[str, object]:
    settings = get_settings()
    validate_private_staging_operation(settings, confirmed=confirmed)

    async with OfficialHttpClient(settings) as http:
        collection = await ParliamentSourceCatalogueCollector(http).collect(catalogue_kind)

    repository = OfficialIndexStagingRepository(settings)
    await repository.connect()
    try:
        return await ParliamentSourceCatalogueStager(settings, repository).store(collection)
    finally:
        await repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Arquivar um catálogo parlamentar privado sem promoção editorial",
    )
    parser.add_argument(
        "catalogue",
        choices=[item.value.lower() for item in ParliamentCatalogueKind],
        help="Um único catálogo oficial por execução",
    )
    parser.add_argument(
        "--confirm-private-staging",
        action="store_true",
        help="Confirmar que o destino é staging privado e que não existe publicação",
    )
    args = parser.parse_args()
    result = asyncio.run(
        sync(
            ParliamentCatalogueKind(args.catalogue.upper()),
            confirmed=args.confirm_private_staging,
        )
    )
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
