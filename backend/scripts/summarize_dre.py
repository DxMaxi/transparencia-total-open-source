"""Gera, para revisão humana, um resumo estruturado de um URL oficial do DRE."""

import argparse
import asyncio

from app.core.config import get_settings
from app.services.ai_summarizer import get_summarizer
from app.services.dre import DreCollector
from app.services.http import OfficialHttpClient


async def summarize(source_url: str) -> str:
    settings = get_settings()
    async with OfficialHttpClient(settings) as http:
        document = await DreCollector(settings, http).fetch_document(source_url)
    result = await get_summarizer(settings).summarize(document)
    return result.model_dump_json(indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_url")
    args = parser.parse_args()
    print(asyncio.run(summarize(args.source_url)))


if __name__ == "__main__":
    main()
