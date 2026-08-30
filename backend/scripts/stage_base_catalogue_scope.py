"""Arquiva o catálogo anual do Portal BASE exclusivamente em staging privado."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.models.archive import PrivateRawDocument
from app.repositories.base_catalogue_staging import BaseCatalogueStagingRepository
from app.services.base_catalogue_scope import (
    extract_base_catalogue_scope,
    load_base_catalogue_manifest,
)
from app.services.http import OfficialHttpClient
from app.services.staging_target import validate_staging_target


def validate_private_staging_operation(settings: Settings, *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError("A operação exige --confirm-private-staging")
    if settings.environment != "staging":
        raise RuntimeError("ENVIRONMENT tem de ser staging")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL de staging não configurada")
    if settings.supabase_url is None:
        raise RuntimeError("SUPABASE_URL de staging não configurada")


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} não configurada")
    return value


async def stage(*, actor_alias: str, confirmed: bool) -> dict[str, object]:
    settings = get_settings()
    validate_private_staging_operation(settings, confirmed=confirmed)
    assert settings.database_url is not None
    assert settings.supabase_url is not None
    validate_staging_target(
        database_url=settings.database_url.get_secret_value(),
        supabase_url=str(settings.supabase_url),
        expected_project_ref=_required_environment("STAGING_SUPABASE_PROJECT_REF"),
        forbidden_project_refs=_required_environment("STAGING_FORBIDDEN_PROJECT_REFS"),
    )

    manifest = load_base_catalogue_manifest()
    async with OfficialHttpClient(settings) as http:
        response = await http.get(str(manifest.catalogue_api_url), max_bytes=5_000_000)
    if str(response.url).rstrip("/") != str(manifest.catalogue_api_url).rstrip("/"):
        raise RuntimeError("A URL final do catálogo BASE diverge do manifesto revisto")
    mime_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if mime_type not in {"application/json", "application/ld+json"}:
        raise RuntimeError("A fonte oficial do catálogo BASE não devolveu JSON")

    now = datetime.now(UTC)
    retrieved_at = now.replace(microsecond=(now.microsecond // 1_000) * 1_000)
    source_sha256 = hashlib.sha256(response.content).hexdigest()
    raw_document = PrivateRawDocument(
        source_url=manifest.catalogue_api_url,
        retrieved_at=retrieved_at,
        content_sha256=source_sha256,
        mime_type=mime_type,
        content=response.content,
    )
    scope = extract_base_catalogue_scope(
        catalogue_bytes=response.content,
        retrieved_at=retrieved_at,
        manifest=manifest,
    )

    repository = BaseCatalogueStagingRepository(settings)
    await repository.connect()
    try:
        schema_readiness = await repository.require_scope_schema()
        receipt = await repository.archive_raw_document(raw_document=raw_document)
        report = await repository.stage_scope(
            raw_document=raw_document,
            archive_receipt=receipt,
            manifest=manifest,
            scope=scope,
            staged_by_alias=actor_alias,
        )
        return {**report, "schema_readiness": schema_readiness}
    finally:
        await repository.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-private-staging", action="store_true")
    parser.add_argument(
        "--actor-alias",
        required=True,
        help="Identificador auditável do operador que iniciou a recolha privada.",
    )
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        report = asyncio.run(
            stage(
                actor_alias=str(args.actor_alias),
                confirmed=bool(args.confirm_private_staging),
            )
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
