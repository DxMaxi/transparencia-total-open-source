"""Recolhe uma fotografia normalizada da fonte oficial da Assembleia da República.

Exemplos:
  python -m scripts.sync_parliament deputies --legislature XVII
  python -m scripts.sync_parliament votes --legislature XVII --output snapshot.json
"""

import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.http import OfficialHttpClient
from app.services.parlamento import ParlamentoCollector

CODE_VERSION = "parliament-ingestion-v12"


async def collect(
    kind: str,
    legislature: str,
    *,
    persist: bool = False,
) -> tuple[str, dict[str, int] | None]:
    settings = get_settings()
    if persist and kind == "votes":
        raise ValueError(
            "Use python -m scripts.sync_parliament_activity para persistir votações versionadas."
        )
    async with OfficialHttpClient(settings) as http:
        collector = ParlamentoCollector(settings, http)
        dataset = (
            await collector.collect_deputies(legislature)
            if kind == "deputies"
            else await collector.collect_votes(legislature)
        )
    persistence = None
    if persist:
        if dataset.raw_document is None:
            raise RuntimeError(
                "A fonte parlamentar não conservou os bytes necessários para o arquivo"
            )
        repository = OfficialIndexStagingRepository(settings)
        await repository.connect()
        try:
            archive_receipt = await repository.archive_raw_document(
                raw_document=dataset.raw_document
            )
            persistence = await repository.store_parliament_dataset(
                dataset,
                kind=kind,
                code_version=CODE_VERSION,
                archive_receipt=archive_receipt,
            )
        finally:
            await repository.close()
    return dataset.model_dump_json(indent=2), persistence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("deputies", "votes"))
    parser.add_argument("--legislature", default="XVII")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Guardar em staging PostgreSQL; não publica registos automaticamente",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result, persistence = asyncio.run(collect(args.kind, args.legislature, persist=args.persist))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temporary.write_text(result, encoding="utf-8")
        temporary.replace(args.output)
        print(f"Snapshot guardado em {args.output}")
    else:
        print(result)
    if persistence is not None:
        print(
            "Persistência concluída em staging: "
            f"{persistence['records_written']} escritas / "
            f"{persistence['records_read']} lidas; "
            f"{persistence['archive_attestations_written']} atestações de arquivo acrescentadas; "
            "publicação continua pendente."
        )


if __name__ == "__main__":
    main()
