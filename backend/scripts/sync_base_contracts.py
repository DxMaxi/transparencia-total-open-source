"""Recolhe contratos BASE e produz candidatos de ligação para revisão editorial.

Exemplo:
    python -m scripts.sync_base_contracts --year 2026 \
      --actors-file ../../transparencia-total-private/public-actors.json \
      --output ../../transparencia-total-private/base-2026-review.json

O ficheiro de atores é uma entrada privada. O resultado nunca inclui NIFs em texto simples.
"""

import argparse
import asyncio
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from pydantic import ValidationError

from app.core.config import Settings
from app.models.api import PublicActorMatchKey
from app.repositories.postgres import BASE_PERSISTENCE_DISABLED_MESSAGE
from app.services.base_gov import BaseGovCollector, ContractMatcher
from app.services.http import OfficialHttpClient

CODE_VERSION = "base-ingestion-v4"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _require_path_outside_repository(path: Path, *, label: str) -> None:
    if path.resolve().is_relative_to(REPOSITORY_ROOT):
        raise ValueError(
            f"{label} tem de ficar fora do repositório para evitar inclusão acidental no Git"
        )


def _write_private_review(path: Path, result: object) -> None:
    """Escreve o artefacto privado de forma atómica e com permissões restritas."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # O hard link publica o ficheiro completo sem substituir uma revisão anterior.
        # Falha atomicamente com FileExistsError se o destino já existir.
        os.link(temporary_path, path)
        temporary_path.unlink()
        os.chmod(path, 0o600)
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sincronizar contratos públicos do Portal BASE")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument(
        "--actors-file",
        type=Path,
        help="Entrada privada opcional para produzir candidatos de correspondência",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resource-url", help="Recurso oficial JSON/XML/ZIP já autorizado")
    parser.add_argument("--limit", type=int, help="Limite explícito para ensaios e amostras")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Recusado nesta versão; use apenas o ficheiro JSON privado para revisão",
    )
    parsed = parser.parse_args()
    if parsed.persist:
        parser.error(BASE_PERSISTENCE_DISABLED_MESSAGE)
    return parsed


async def run(args: argparse.Namespace) -> None:
    if args.persist:
        raise RuntimeError(BASE_PERSISTENCE_DISABLED_MESSAGE)

    _require_path_outside_repository(args.output, label="O ficheiro de revisão BASE")
    if args.actors_file:
        _require_path_outside_repository(args.actors_file, label="O ficheiro privado de atores")

    actors: list[PublicActorMatchKey] = []
    if args.actors_file:
        actor_payload = json.loads(args.actors_file.read_text(encoding="utf-8"))
        if not isinstance(actor_payload, list):
            raise ValueError("O ficheiro de atores deve conter uma lista JSON")
        try:
            actors = [PublicActorMatchKey.model_validate(item) for item in actor_payload]
        except ValidationError:
            raise ValueError(
                "O ficheiro de atores é inválido; use apenas digests HMAC-SHA-256 e prova oficial"
            ) from None

    settings = Settings.model_validate(
        {"base_resource_url": args.resource_url} if args.resource_url else {}
    )
    async with OfficialHttpClient(settings) as http:
        collection = await BaseGovCollector(settings, http).collect(args.year, limit=args.limit)

    pepper = (
        settings.protected_identifier_pepper.get_secret_value()
        if settings.protected_identifier_pepper is not None
        else None
    )
    matches = ContractMatcher(pepper=pepper).match(collection.contracts, actors)
    warnings = list(collection.warnings)
    if pepper is None and any(
        actor.protected_nif_digest is not None
        or any(
            association.protected_nipc_digest is not None
            for association in actor.official_associations
        )
        for actor in actors
    ):
        warnings.append(
            "PROTECTED_IDENTIFIER_PEPPER não configurado: correspondências por identificador "
            "protegido foram omitidas"
        )

    result = {
        "schema_version": "base-review-v3",
        "source": collection.dataset_resource.model_dump(mode="json"),
        "source_sha256": collection.document_sha256,
        "collected_at": collection.collected_at.isoformat(),
        "warnings": warnings,
        "contracts": [item.model_dump(mode="json") for item in collection.contracts],
        "match_candidates": [item.model_dump(mode="json") for item in matches],
        "publication_rule": (
            "Todos os candidatos ficam PENDING_REVIEW e não constituem prova "
            "de conflito ou ilícito."
        ),
    }
    _write_private_review(args.output, result)


def main() -> None:
    try:
        asyncio.run(run(arguments()))
    except ValidationError:
        raise SystemExit("Configuração inválida; nenhum valor protegido foi mostrado") from None
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
