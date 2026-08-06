"""Inspeciona metadados DRE persistidos sem devolver o texto jurídico extraído."""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.repositories.dre_staging import DreStagingRepository


async def inspect(official_identifier: str | None) -> dict[str, object]:
    repository = DreStagingRepository(get_settings())
    await repository.connect()
    try:
        return await repository.inspect_dre_staging(
            official_identifier=official_identifier,
        )
    finally:
        await repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-identifier")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(inspect(args.official_identifier)),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
