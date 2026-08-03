"""Inspeciona metadados de um snapshot BASE sem devolver nomes ou HMAC.

Exemplo:
    python -m scripts.inspect_base_staging --year 2026

O comando é exclusivamente de leitura. Não cria candidatos, revisão ou publicação.
"""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    return parser.parse_args()


async def run(year: int) -> dict[str, object]:
    repository = PostgresRepository(get_settings())
    await repository.connect()
    try:
        return await repository.inspect_base_staging(year=year)
    finally:
        await repository.close()


def main() -> None:
    report = asyncio.run(run(arguments().year))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
