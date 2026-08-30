"""Persistência privada e append-only do âmbito anual dos contratos BASE."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.models.archive import PrivateRawDocument, RawArchiveReceipt
from app.models.base_catalogue import (
    BaseCatalogueScopeManifest,
    BaseCatalogueTemporalScope,
)
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.base_catalogue_scope import verify_base_catalogue_scope

BASE_SCOPE_MIGRATION = "20260830090000_v5_base_temporal_scope"
BASE_SCOPE_TABLES = frozenset(
    {
        "base_contract_catalogue_scopes",
        "base_contract_catalogue_resources",
    }
)
BASE_SCOPE_TRIGGERS = frozenset(
    {
        "base_contract_catalogue_scope_validate_insert",
        "base_contract_catalogue_scope_validate_completion",
        "base_contract_catalogue_resource_validate_completion",
        "base_contract_catalogue_scopes_append_only",
        "base_contract_catalogue_resources_append_only",
    }
)


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _database_timestamp(value: datetime) -> datetime:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.replace(tzinfo=None)


class BaseCatalogueStagingRepository(OfficialIndexStagingRepository):
    """Guarda apenas a fotografia do catálogo; não recolhe nem publica contratos."""

    async def require_scope_schema(self) -> dict[str, object]:
        if self.pool is None:
            raise RuntimeError("Base de dados de staging não configurada")
        async with (
            self.pool.acquire() as connection,
            connection.transaction(readonly=True, isolation="repeatable_read"),
        ):
            migrations_table_exists = bool(
                await connection.fetchval(
                    """SELECT to_regclass('public.\"_prisma_migrations\"') IS NOT NULL"""
                )
            )
            migration_applied = (
                bool(
                    await connection.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM public."_prisma_migrations"
                            WHERE migration_name = $1
                              AND finished_at IS NOT NULL
                              AND rolled_back_at IS NULL
                        )
                        """,
                        BASE_SCOPE_MIGRATION,
                    )
                )
                if migrations_table_exists
                else False
            )
            table_rows = await connection.fetch(
                """
                SELECT relation.relname, relation.relrowsecurity
                FROM pg_class AS relation
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'public'
                  AND relation.relkind IN ('r', 'p')
                  AND relation.relname = ANY($1::text[])
                """,
                sorted(BASE_SCOPE_TABLES),
            )
            tables = {str(row["relname"]) for row in table_rows}
            rls_tables = {str(row["relname"]) for row in table_rows if bool(row["relrowsecurity"])}
            trigger_rows = await connection.fetch(
                """
                SELECT trigger_record.tgname
                FROM pg_trigger AS trigger_record
                JOIN pg_class AS relation ON relation.oid = trigger_record.tgrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'public'
                  AND relation.relname = ANY($1::text[])
                  AND NOT trigger_record.tgisinternal
                  AND trigger_record.tgenabled = 'O'
                """,
                sorted(BASE_SCOPE_TABLES),
            )
            triggers = {str(row["tgname"]) for row in trigger_rows}

        failed: list[str] = []
        if not migration_applied:
            failed.append(f"migração {BASE_SCOPE_MIGRATION}")
        missing_tables = sorted(BASE_SCOPE_TABLES - tables)
        missing_rls = sorted(BASE_SCOPE_TABLES - rls_tables)
        missing_triggers = sorted(BASE_SCOPE_TRIGGERS - triggers)
        if missing_tables:
            failed.append(f"tabelas {', '.join(missing_tables)}")
        if missing_rls:
            failed.append(f"RLS {', '.join(missing_rls)}")
        if missing_triggers:
            failed.append(f"triggers {', '.join(missing_triggers)}")
        if failed:
            raise RuntimeError(
                "O esquema privado do âmbito BASE não está pronto: " + "; ".join(failed)
            )
        return {
            "ready": True,
            "migration": BASE_SCOPE_MIGRATION,
            "tables": sorted(tables),
            "rls_tables": sorted(rls_tables),
            "triggers": sorted(triggers),
        }

    async def stage_scope(
        self,
        *,
        raw_document: PrivateRawDocument,
        archive_receipt: RawArchiveReceipt,
        manifest: BaseCatalogueScopeManifest,
        scope: BaseCatalogueTemporalScope,
        staged_by_alias: str,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError("O âmbito BASE só pode ser persistido em staging privado")
        if self.pool is None:
            raise RuntimeError("Base de dados de staging não configurada")
        await self.require_scope_schema()
        actor_alias = staged_by_alias.strip()
        if len(actor_alias) < 3 or len(actor_alias) > 120:
            raise ValueError("O pseudónimo do processo de staging é inválido")
        if (
            archive_receipt.content_sha256 != raw_document.content_sha256
            or archive_receipt.byte_size != len(raw_document.content)
            or str(archive_receipt.source_url) != str(raw_document.source_url)
            or scope.source_sha256 != raw_document.content_sha256
            or scope.source_byte_size != len(raw_document.content)
            or str(scope.catalogue_url) != str(raw_document.source_url)
        ):
            raise ValueError("O âmbito BASE não coincide com o catálogo oficial arquivado")
        verify_base_catalogue_scope(scope=scope, manifest=manifest)

        scope_id = _stable_id(
            "base_scope",
            f"{scope.source_sha256}:{scope.parser_version}:{scope.scope_sha256}",
        )
        sync_id = await self._start_sync_run(
            source_name=manifest.source_name,
            dataset_url=str(raw_document.source_url),
            code_version=manifest.parser_version,
        )
        scope_created = False
        attestation_created = False
        source_document_id: str | None = None
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base-contracts-catalogue:{scope.source_sha256}:{scope.parser_version}",
                )
                source_document_id = await self._ensure_source_document(
                    connection,
                    publisher="BASE_GOV",
                    kind="OPEN_DATASET",
                    title=scope.dataset_title,
                    url=str(raw_document.source_url),
                    retrieved_at=raw_document.retrieved_at,
                    content_sha256=raw_document.content_sha256,
                    mime_type=raw_document.mime_type,
                    parser_version=scope.parser_version,
                )
                attestation = await self._attest_source_archive(
                    connection,
                    source_document_id=source_document_id,
                    receipt=archive_receipt,
                    archived_by=actor_alias,
                )
                attestation_created = bool(attestation["created"])
                source_retrieved_at = await connection.fetchval(
                    "SELECT retrieved_at FROM source_documents WHERE id = $1",
                    source_document_id,
                )
                inserted = await connection.fetchrow(
                    """
                    INSERT INTO base_contract_catalogue_scopes
                        (id, source_document_id, sync_run_id, dataset_id, dataset_title,
                         producer_id, producer_name, licence_code, update_frequency,
                         public_dataset_url, parser_version, policy_version, first_year,
                         closed_through_year, rolling_year, source_sha256, scope_sha256,
                         source_byte_size, resource_count, retrieved_at, created_at)
                    VALUES
                        ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                         $14, $15, $16, $17, $18, $19, $20, NOW())
                    ON CONFLICT (source_document_id, parser_version) DO NOTHING
                    RETURNING id
                    """,
                    scope_id,
                    source_document_id,
                    sync_id,
                    scope.dataset_id,
                    scope.dataset_title,
                    scope.producer_id,
                    scope.producer_name,
                    scope.licence_code,
                    scope.update_frequency,
                    str(scope.public_dataset_url),
                    scope.parser_version,
                    scope.policy_version,
                    scope.first_year,
                    scope.closed_through_year,
                    scope.rolling_year,
                    scope.source_sha256,
                    scope.scope_sha256,
                    scope.source_byte_size,
                    scope.resource_count,
                    source_retrieved_at,
                )
                scope_created = inserted is not None
                if scope_created:
                    await connection.executemany(
                        """
                        INSERT INTO base_contract_catalogue_resources
                            (id, scope_id, ordinal, source_resource_id, resource_year,
                             coverage_state, resource_title, resource_format,
                             versioned_url, stable_url, source_modified_at, byte_size,
                             metadata_sha256, created_at)
                        VALUES
                            ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                             $13, NOW())
                        """,
                        [
                            (
                                _stable_id(
                                    "base_scope_resource",
                                    f"{scope_id}:{resource.source_resource_id}",
                                ),
                                scope_id,
                                resource.ordinal,
                                resource.source_resource_id,
                                resource.resource_year,
                                resource.coverage_state.value,
                                resource.title,
                                resource.resource_format,
                                str(resource.versioned_url),
                                str(resource.stable_url),
                                _database_timestamp(resource.source_modified_at),
                                resource.byte_size,
                                resource.metadata_sha256,
                            )
                            for resource in scope.resources
                        ],
                    )
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'BASE_CONTRACT_CATALOGUE_SCOPE', $2,
                                'STAGED_PRIVATE_SCOPE', $3, NULL, $4::jsonb, $5, NOW())
                        """,
                        _stable_id("audit", f"{scope_id}:staged"),
                        scope_id,
                        actor_alias,
                        json.dumps(
                            {
                                "dataset_id": scope.dataset_id,
                                "source_sha256": scope.source_sha256,
                                "scope_sha256": scope.scope_sha256,
                                "first_year": scope.first_year,
                                "closed_through_year": scope.closed_through_year,
                                "rolling_year": scope.rolling_year,
                                "resource_count": scope.resource_count,
                                "publication_eligible": False,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "Âmbito temporal oficial preservado em privado; não recolhe, "
                        "revê ou publica contratos.",
                    )
                else:
                    existing = await connection.fetchrow(
                        """
                        SELECT id, dataset_id, producer_id, parser_version, policy_version,
                               first_year, closed_through_year, rolling_year, source_sha256,
                               scope_sha256, source_byte_size, resource_count
                        FROM base_contract_catalogue_scopes
                        WHERE source_document_id = $1 AND parser_version = $2
                        """,
                        source_document_id,
                        scope.parser_version,
                    )
                    if existing is None or any(
                        (
                            str(existing["id"]) != scope_id,
                            str(existing["dataset_id"]) != scope.dataset_id,
                            str(existing["producer_id"]) != scope.producer_id,
                            str(existing["parser_version"]) != scope.parser_version,
                            str(existing["policy_version"]) != scope.policy_version,
                            int(existing["first_year"]) != scope.first_year,
                            int(existing["closed_through_year"]) != scope.closed_through_year,
                            int(existing["rolling_year"]) != scope.rolling_year,
                            str(existing["source_sha256"]) != scope.source_sha256,
                            str(existing["scope_sha256"]) != scope.scope_sha256,
                            int(existing["source_byte_size"]) != scope.source_byte_size,
                            int(existing["resource_count"]) != scope.resource_count,
                        )
                    ):
                        raise ValueError("O âmbito BASE existente diverge da mesma fonte e parser")
                    observed_resources = await connection.fetchval(
                        """
                        SELECT count(*)
                        FROM base_contract_catalogue_resources
                        WHERE scope_id = $1
                        """,
                        scope_id,
                    )
                    if int(observed_resources) != scope.resource_count:
                        raise ValueError("Os recursos do âmbito BASE existente estão incompletos")

            await self._finish_sync_run(
                sync_id,
                status_value="SUCCEEDED",
                records_read=scope.resource_count,
                records_written=(scope.resource_count + 1) if scope_created else 0,
                warnings=[
                    f"{scope.rolling_year} é ano corrente provisório; ausência não equivale "
                    "a ausência de contratos."
                ],
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=scope.resource_count,
                records_written=0,
                warnings=[],
                error_message=str(exc),
            )
            raise

        return {
            "source_document_id": source_document_id,
            "scope_id": scope_id,
            "source_sha256": scope.source_sha256,
            "scope_sha256": scope.scope_sha256,
            "first_year": scope.first_year,
            "closed_through_year": scope.closed_through_year,
            "rolling_year": scope.rolling_year,
            "resource_count": scope.resource_count,
            "scope_created": scope_created,
            "attestation_created": attestation_created,
            "publication_eligible": False,
        }
