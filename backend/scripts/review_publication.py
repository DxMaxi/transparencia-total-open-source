"""Publica ou retira um registo após revisão humana explícita e auditável.

Exemplo:
  python -m scripts.review_publication PERSON person_id --publish \
    --reviewer "revisor-01" --rationale "Fonte e identidade confirmadas" \
    --confirm-source-reviewed
"""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "entity_type",
        choices=(
            "PERSON",
            "MANDATE",
            "ASSET_DECLARATION",
            "PROMISE",
            "PUBLIC_CONTRACT",
            "INTEREST_ENTITY",
            "INTEREST_RELATIONSHIP",
        ),
    )
    parser.add_argument("entity_id")
    decision = parser.add_mutually_exclusive_group(required=True)
    decision.add_argument("--publish", action="store_true")
    decision.add_argument("--withdraw", action="store_true")
    parser.add_argument("--reviewer", required=True, help="Pseudónimo público do revisor")
    parser.add_argument("--rationale", required=True, help="Fundamentação factual da decisão")
    parser.add_argument(
        "--confirm-source-reviewed",
        action="store_true",
        help="Confirmação explícita obrigatória para publicar",
    )
    parser.add_argument(
        "--confirm-legal-basis-reviewed",
        action="store_true",
        help=("Confirmação adicional obrigatória para publicar metadados de uma declaração"),
    )
    args = parser.parse_args()
    if args.publish and not args.confirm_source_reviewed:
        parser.error("--publish exige --confirm-source-reviewed")
    if (
        args.publish
        and args.entity_type == "ASSET_DECLARATION"
        and not args.confirm_legal_basis_reviewed
    ):
        parser.error("publicar ASSET_DECLARATION exige --confirm-legal-basis-reviewed")
    if args.publish and args.entity_type == "ASSET_DECLARATION":
        parser.error(
            "ASSET_DECLARATION já não pode ser publicada pelo comando genérico; "
            "use a porta editorial EPT específica depois de ela estar juridicamente ativada"
        )
    return args


async def run(args: argparse.Namespace) -> None:
    repository = PostgresRepository(get_settings())
    await repository.connect()
    try:
        result = await repository.review_publication(
            entity_type=args.entity_type,
            entity_id=args.entity_id,
            publish=args.publish,
            reviewer_alias=args.reviewer,
            rationale=args.rationale,
            legal_basis_confirmed=args.confirm_legal_basis_reviewed,
        )
    finally:
        await repository.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
