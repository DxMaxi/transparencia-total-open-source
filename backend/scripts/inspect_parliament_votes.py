"""Inspeciona em privado uma fotografia de votações persistida em staging.

Este comando é exclusivamente de leitura. Não cria decisões de revisão, não
associa rótulos a pessoas ou partidos e não publica qualquer registo.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legislature", default="XVII")
    parser.add_argument(
        "--output",
        type=Path,
        help="Guardar o relatório privado completo em JSON",
    )
    return parser.parse_args()


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    availability = dict(report["normalised_position_availability"])
    events = availability.pop("events")
    assert isinstance(events, list)
    availability["sample"] = events[:10]
    return {
        **report,
        "normalised_position_availability": availability,
    }


async def run(args: argparse.Namespace) -> None:
    repository = PostgresRepository(get_settings())
    await repository.connect()
    try:
        report = await repository.inspect_parliament_votes_staging(
            legislature=args.legislature,
        )
    finally:
        await repository.close()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2, default=str))


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
