"""Regista metadados mínimos de uma prova EPT já arquivada, apenas em privado.

O identificador oficial do titular é pedido sem eco e convertido imediatamente
para HMAC-SHA-256. Nunca é aceite na linha de comandos nem guardado em claro.
"""

import argparse
import asyncio
import json
from getpass import getpass

from pydantic import SecretStr

from app.core.config import get_settings
from app.models.ept_declaration import EptPublicInterestObservationInput
from app.repositories.ept_declaration_staging import EptDeclarationStagingRepository
from app.repositories.postgres import PostgresRepository


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_document_id")
    parser.add_argument("official_declaration_id")
    parser.add_argument("public_subject_name")
    parser.add_argument("--declared-at")
    parser.add_argument("--period-label")
    parser.add_argument("--actor", required=True, help="Pseudónimo interno do operador autorizado")
    parser.add_argument("--confirm-public-interest-register-only", action="store_true")
    parser.add_argument("--confirm-no-income-or-asset-content", action="store_true")
    parser.add_argument("--confirm-no-protected-identifiers-persisted", action="store_true")
    parser.add_argument("--confirm-private-only", action="store_true")
    args = parser.parse_args()
    required_confirmations = (
        args.confirm_public_interest_register_only,
        args.confirm_no_income_or_asset_content,
        args.confirm_no_protected_identifiers_persisted,
        args.confirm_private_only,
    )
    if not all(required_confirmations):
        parser.error("a operação exige as quatro confirmações explícitas de privacidade e âmbito")
    return args


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.protected_identifier_pepper is None:
        raise RuntimeError(
            "PROTECTED_IDENTIFIER_PEPPER não configurado; a base de dados não será consultada"
        )
    subject_identifier = SecretStr(
        getpass("Identificador oficial do titular (não será guardado em claro): ")
    )
    payload = EptPublicInterestObservationInput(
        source_document_id=args.source_document_id,
        official_declaration_id=args.official_declaration_id,
        official_subject_identifier=subject_identifier,
        public_subject_name=args.public_subject_name,
        declared_at=args.declared_at,
        period_label=args.period_label,
        confirm_public_interest_register_only=True,
        confirm_no_income_or_asset_content=True,
        confirm_no_protected_identifiers_persisted=True,
        confirm_private_only=True,
    )

    repository = PostgresRepository(settings)
    try:
        await repository.connect()
        if repository.pool is None:
            raise RuntimeError("Base de dados não configurada")
        result = await EptDeclarationStagingRepository(
            repository.pool,
            settings,
        ).stage_observation(payload=payload, actor_alias=args.actor)
    finally:
        await repository.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
