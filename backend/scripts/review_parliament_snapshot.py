"""Pré-visualiza e publica uma fotografia parlamentar após revisão humana explícita.

Primeiro execute sem ``--publish`` para obter a contagem e o SHA-256 atuais. A
publicação exige repetir ambos os valores e confirmar que a fonte foi revista.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legislature", default="XVII")
    parser.add_argument("--output", type=Path, help="Guardar a pré-visualização completa em JSON")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--source-sha256")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--reviewer", help="Pseudónimo público do revisor")
    parser.add_argument("--rationale", help="Fundamentação factual da decisão")
    parser.add_argument(
        "--confirm-source-reviewed",
        action="store_true",
        help="Confirmação explícita obrigatória para publicar",
    )
    args = parser.parse_args()
    if args.publish:
        required = {
            "--source-sha256": args.source_sha256,
            "--expected-count": args.expected_count,
            "--reviewer": args.reviewer,
            "--rationale": args.rationale,
        }
        missing = [flag for flag, value in required.items() if value in {None, ""}]
        if missing:
            parser.error("--publish exige " + ", ".join(missing))
        if not args.confirm_source_reviewed:
            parser.error("--publish exige --confirm-source-reviewed")
    return args


def _serialisable_preview(snapshot: dict[str, object]) -> dict[str, object]:
    people = snapshot["people"]
    assert isinstance(people, list)
    candidate_count = snapshot["candidate_count"]
    already_published = snapshot["already_published"]
    assert isinstance(candidate_count, int)
    assert isinstance(already_published, int)
    return {
        **snapshot,
        "pending_publication": candidate_count - already_published,
        "people": people,
        "publication_rule": (
            "A pré-visualização não publica dados. Compare a fonte, o SHA-256 e a contagem "
            "antes de confirmar a decisão."
        ),
    }


async def run(args: argparse.Namespace) -> None:
    repository = PostgresRepository(get_settings())
    await repository.connect()
    try:
        snapshot = await repository.inspect_parliament_people_publication(
            legislature=args.legislature,
        )
        preview = _serialisable_preview(snapshot)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(preview, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        if not args.publish:
            summary = {key: value for key, value in preview.items() if key != "people"}
            people = preview["people"]
            assert isinstance(people, list)
            summary["sample"] = people[:10]
            print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
            return

        result = await repository.publish_parliament_people_snapshot(
            legislature=args.legislature,
            expected_source_sha256=args.source_sha256,
            expected_count=args.expected_count,
            reviewer_alias=args.reviewer,
            rationale=args.rationale,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        await repository.close()


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
