"""Pré-visualiza, publica ou retira uma fotografia parlamentar revista.

Execute primeiro sem ação para obter os dois hashes e as quatro contagens. Uma
decisão exige repetir todos esses valores e confirmar a revisão da fonte.
"""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.repositories.parliament_publication import (
    ParliamentSnapshotPublicationRepository,
    PublicationScope,
)
from app.repositories.postgres import PostgresRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legislature", default="XVII")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--publish", action="store_true")
    action.add_argument("--withdraw", action="store_true")
    parser.add_argument("--scope", choices=("all", "activity", "votes"), default="all")
    parser.add_argument("--source-sha256")
    parser.add_argument("--normalised-sha256")
    parser.add_argument("--expected-sessions", type=int)
    parser.add_argument("--expected-initiatives", type=int)
    parser.add_argument("--expected-votes", type=int)
    parser.add_argument("--expected-vote-records", type=int)
    parser.add_argument("--reviewer", help="Pseudónimo público do revisor")
    parser.add_argument("--rationale", help="Fundamentação factual da decisão")
    parser.add_argument("--confirm-source-reviewed", action="store_true")
    args = parser.parse_args()
    if args.publish or args.withdraw:
        required = {
            "--source-sha256": args.source_sha256,
            "--normalised-sha256": args.normalised_sha256,
            "--expected-sessions": args.expected_sessions,
            "--expected-initiatives": args.expected_initiatives,
            "--expected-votes": args.expected_votes,
            "--expected-vote-records": args.expected_vote_records,
            "--reviewer": args.reviewer,
            "--rationale": args.rationale,
        }
        missing = [flag for flag, value in required.items() if value is None or value == ""]
        if missing:
            parser.error("a decisão exige " + ", ".join(missing))
        if not args.confirm_source_reviewed:
            parser.error("a decisão exige --confirm-source-reviewed")
    return args


async def run(args: argparse.Namespace) -> dict[str, object]:
    repository = PostgresRepository(get_settings())
    await repository.connect()
    try:
        publication = ParliamentSnapshotPublicationRepository(repository.pool)
        if not args.publish and not args.withdraw:
            return await publication.inspect(legislature=args.legislature)

        scopes: set[PublicationScope] = (
            {"activity", "votes"} if args.scope == "all" else {args.scope}
        )
        return await publication.review(
            legislature=args.legislature,
            scopes=scopes,
            publishable=args.publish,
            expected_source_sha256=args.source_sha256,
            expected_normalised_sha256=args.normalised_sha256,
            expected_counts={
                "sessions": args.expected_sessions,
                "initiatives": args.expected_initiatives,
                "votes": args.expected_votes,
                "vote_records": args.expected_vote_records,
            },
            reviewer_alias=args.reviewer,
            rationale=args.rationale,
        )
    finally:
        await repository.close()


def main() -> None:
    print(json.dumps(asyncio.run(run(arguments())), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
