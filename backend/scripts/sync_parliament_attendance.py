"""Recolhe uma reunião plenária exata apenas para staging privado."""

import argparse
import asyncio
import json

from app.core.config import Settings, get_settings
from app.repositories.parliament_attendance import ParliamentAttendanceRepository
from app.services.http import OfficialHttpClient
from app.services.parliament_attendance import (
    ParliamentAttendanceCollector,
    ParliamentAttendanceStager,
    require_attendance_url,
)
from app.services.parliament_source_catalogue import require_supported_parliament_legislature


def validate_private_attendance_operation(settings: Settings, *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError("A persistência exige --confirm-private-staging")
    if settings.environment != "staging":
        raise RuntimeError("ENVIRONMENT tem de ser staging para guardar presenças")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")


async def sync(*, legislature: str, meeting_url: str, confirmed: bool) -> dict[str, object]:
    settings = get_settings()
    validate_private_attendance_operation(settings, confirmed=confirmed)
    exact_legislature = require_supported_parliament_legislature(legislature)
    exact_url = require_attendance_url(meeting_url).url

    repository = ParliamentAttendanceRepository(settings)
    await repository.connect()
    try:
        async with OfficialHttpClient(settings) as http:
            dataset = await ParliamentAttendanceCollector(http).collect(
                legislature=exact_legislature,
                meeting_url=exact_url,
            )
        return await ParliamentAttendanceStager(settings, repository).store(dataset)
    finally:
        await repository.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Arquivar e normalizar uma reunião de presenças, sem criar revisão ou publicação"
        )
    )
    parser.add_argument("legislature", help="Legislatura exata, por exemplo XVII")
    parser.add_argument("--meeting-url", required=True, help="URL oficial com um único BID")
    parser.add_argument(
        "--confirm-private-staging",
        action="store_true",
        help="Confirmar staging privado, sem revisão ou publicação",
    )
    args = parser.parse_args()
    result = asyncio.run(
        sync(
            legislature=args.legislature,
            meeting_url=args.meeting_url,
            confirmed=args.confirm_private_staging,
        )
    )
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
