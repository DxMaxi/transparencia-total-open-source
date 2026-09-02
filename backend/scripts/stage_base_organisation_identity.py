"""Prepara uma identidade IRN privada em staging, sem aprovação nem publicação.

O NIPC é pedido sem eco, nunca aceite como argumento, e persiste exclusivamente
como HMAC-SHA-256 com pepper duradouro. A fonte individual tem de estar arquivada.
"""

import argparse
import asyncio
import json
import os
import warnings
from getpass import GetPassWarning, getpass

from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.models.base_organisation import BaseOrganisationIdentityObservationInput
from app.repositories.base_organisation_staging import BaseOrganisationStagingRepository
from app.repositories.postgres import PostgresRepository
from app.services.staging_target import validate_staging_target


def validate_private_staging_operation(settings: Settings, *, confirmed: bool) -> None:
    """Todas as verificações de destino e pepper precedem getpass e a ligação."""

    if not confirmed or settings.environment != "staging":
        raise RuntimeError("É necessária confirmação explícita do ambiente staging")
    if settings.database_url is None or settings.supabase_url is None:
        raise RuntimeError("O destino de staging não está configurado")
    if settings.protected_identifier_pepper is None:
        raise RuntimeError("O pepper duradouro não está configurado")
    validate_staging_target(
        database_url=settings.database_url.get_secret_value(),
        supabase_url=str(settings.supabase_url),
        expected_project_ref=os.environ.get("STAGING_SUPABASE_PROJECT_REF", ""),
        forbidden_project_refs=os.environ.get("STAGING_FORBIDDEN_PROJECT_REFS", ""),
    )


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        # argparse inclui argumentos desconhecidos na mensagem, possivelmente um NIPC.
        self.exit(
            2,
            "Argumentos inválidos. Consulte --help; identificadores fiscais só são "
            "aceites no pedido privado sem eco.\n",
        )


def _parser() -> argparse.ArgumentParser:
    parser = _PrivateArgumentParser(description=__doc__)
    parser.add_argument("source_document_id")
    parser.add_argument("registry_record_id")
    parser.add_argument("legal_name")
    parser.add_argument(
        "--kind",
        required=True,
        choices=[
            "PUBLIC_BODY",
            "COMPANY",
            "NON_PROFIT",
            "EUROPEAN_BODY",
            "OTHER",
        ],
    )
    parser.add_argument("--actor-alias", required=True)
    parser.add_argument("--confirm-private-staging", action="store_true")
    parser.add_argument("--confirm-independent-official-source", action="store_true")
    parser.add_argument("--confirm-identifier-hmac-only", action="store_true")
    parser.add_argument("--confirm-private-identity-only", action="store_true")
    parser.add_argument("--confirm-no-publication", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    settings = get_settings()
    validate_private_staging_operation(settings, confirmed=args.confirm_private_staging)
    if not all(
        (
            args.confirm_independent_official_source,
            args.confirm_identifier_hmac_only,
            args.confirm_private_identity_only,
            args.confirm_no_publication,
        )
    ):
        raise RuntimeError("Faltam confirmações explícitas de âmbito e privacidade")
    with warnings.catch_warnings():
        # Sem terminal seguro, abortar em vez de recorrer a uma entrada com eco.
        warnings.simplefilter("error", GetPassWarning)
        private_identifier = SecretStr(getpass("NIPC da prova oficial (entrada sem eco): "))
    payload = BaseOrganisationIdentityObservationInput(
        source_document_id=args.source_document_id,
        registry_record_id=args.registry_record_id,
        legal_name=args.legal_name,
        kind=args.kind,
        fiscal_identifier=private_identifier,
        confirm_independent_official_source=True,
        confirm_identifier_hmac_only=True,
        confirm_private_identity_only=True,
        confirm_no_publication=True,
    )
    repository = PostgresRepository(settings)
    try:
        await repository.connect()
        if repository.pool is None:
            raise RuntimeError("Base de dados de staging indisponível")
        return await BaseOrganisationStagingRepository(
            repository.pool,
            settings,
        ).stage_observation(payload=payload, actor_alias=args.actor_alias)
    finally:
        await repository.close()


def main() -> None:
    args = _parser().parse_args()
    try:
        result = asyncio.run(run(args))
    except Exception:
        # A entrada privada e detalhes do driver nunca aparecem num traceback CLI.
        raise SystemExit(
            "Operação privada não concluída. Verifique destino, confirmações, formato "
            "da identidade e prova oficial arquivada; nenhum detalhe sensível é apresentado."
        ) from None
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
