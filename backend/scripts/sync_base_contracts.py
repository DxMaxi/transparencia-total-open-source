"""Recolhe contratos BASE e produz candidatos de ligação para revisão editorial.

Exemplo:
    python -m scripts.sync_base_contracts --year 2026 \
      --actors-file ../data/private/public-actors.json \
      --output ../data/base-2026-review.json

O ficheiro de atores é uma entrada privada. O resultado nunca inclui NIFs em texto simples.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.models.api import PublicActorMatchKey
from app.repositories.postgres import PostgresRepository
from app.services.base_gov import BaseGovCollector, ContractMatcher
from app.services.http import OfficialHttpClient

CODE_VERSION = "base-ingestion-v3"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sincronizar contratos públicos do Portal BASE")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument(
        "--actors-file",
        type=Path,
        help="Entrada privada opcional para produzir candidatos de correspondência",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resource-url", help="Recurso oficial JSON/XML/ZIP já autorizado")
    parser.add_argument("--limit", type=int, help="Limite explícito para ensaios e amostras")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Guardar contratos e entidades em staging; não publica relações",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    actors: list[PublicActorMatchKey] = []
    if args.actors_file:
        actor_payload = json.loads(args.actors_file.read_text(encoding="utf-8"))
        if not isinstance(actor_payload, list):
            raise ValueError("O ficheiro de atores deve conter uma lista JSON")
        actors = [PublicActorMatchKey.model_validate(item) for item in actor_payload]

    settings = Settings.model_validate(
        {"base_resource_url": args.resource_url} if args.resource_url else {}
    )
    async with OfficialHttpClient(settings) as http:
        collection = await BaseGovCollector(settings, http).collect(args.year, limit=args.limit)

    pepper = (
        settings.protected_identifier_pepper.get_secret_value()
        if settings.protected_identifier_pepper is not None
        else None
    )
    matches = ContractMatcher(pepper=pepper).match(collection.contracts, actors)
    warnings = list(collection.warnings)
    if pepper is None and any(actor.protected_nif is not None for actor in actors):
        warnings.append(
            "PROTECTED_IDENTIFIER_PEPPER não configurado: correspondências por NIF foram omitidas"
        )

    result = {
        "schema_version": "base-review-v2",
        "source": collection.dataset_resource.model_dump(mode="json"),
        "source_sha256": collection.document_sha256,
        "collected_at": collection.collected_at.isoformat(),
        "warnings": warnings,
        "contracts": [item.model_dump(mode="json") for item in collection.contracts],
        "match_candidates": [item.model_dump(mode="json") for item in matches],
        "publication_rule": (
            "Todos os candidatos ficam PENDING_REVIEW e não constituem prova "
            "de conflito ou ilícito."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.persist:
        repository = PostgresRepository(settings)
        await repository.connect()
        try:
            persistence = await repository.store_base_collection(
                collection,
                code_version=CODE_VERSION,
            )
        finally:
            await repository.close()
        print(
            "Persistência concluída em staging: "
            f"{persistence['records_written']} escritas / "
            f"{persistence['records_read']} contratos lidos; publicação continua pendente."
        )


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
