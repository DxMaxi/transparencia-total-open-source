"""Persistência privada do catálogo de candidatos do Programa do Governo."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from app.models.archive import PrivateRawDocument, RawArchiveReceipt
from app.models.government_programme import (
    GovernmentProgrammeCatalogue,
    GovernmentProgrammeCatalogueManifest,
)
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.government_programme_catalogue import (
    verify_government_programme_catalogue,
)

CATALOGUE_MIGRATION = "20260829183000_v5_government_programme_catalogue_staging"
CATALOGUE_TABLES = frozenset(
    {
        "government_programme_snapshots",
        "government_promise_catalogue_coverage",
        "government_promise_candidates",
    }
)
CATALOGUE_TRIGGERS = frozenset(
    {
        "government_programme_snapshot_validate_insert",
        "government_programme_catalogue_validate_completion",
        "government_programme_snapshots_append_only",
        "government_promise_coverage_append_only",
        "government_promise_candidates_append_only",
    }
)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _new_deterministic_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def _database_timestamp(value: datetime) -> datetime:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.replace(tzinfo=None)


class GovernmentProgrammeStagingRepository(OfficialIndexStagingRepository):
    """Guarda fotografia e candidatos sem criar qualquer projeção pública."""

    async def require_catalogue_schema(self) -> dict[str, object]:
        """Confirma a migração e as barreiras privadas antes de qualquer escrita."""

        if self.pool is None:
            raise RuntimeError("Base de dados de staging não configurada")
        async with (
            self.pool.acquire() as connection,
            connection.transaction(
                readonly=True,
                isolation="repeatable_read",
            ),
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
                        CATALOGUE_MIGRATION,
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
                sorted(CATALOGUE_TABLES),
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
                sorted(CATALOGUE_TABLES),
            )
            triggers = {str(row["tgname"]) for row in trigger_rows}

        missing_tables = sorted(CATALOGUE_TABLES - tables)
        missing_rls = sorted(CATALOGUE_TABLES - rls_tables)
        missing_triggers = sorted(CATALOGUE_TRIGGERS - triggers)
        failed_checks: list[str] = []
        if not migration_applied:
            failed_checks.append(f"migração {CATALOGUE_MIGRATION}")
        if missing_tables:
            failed_checks.append(f"tabelas {', '.join(missing_tables)}")
        if missing_rls:
            failed_checks.append(f"RLS {', '.join(missing_rls)}")
        if missing_triggers:
            failed_checks.append(f"triggers {', '.join(missing_triggers)}")
        if failed_checks:
            raise RuntimeError(
                "O esquema privado do catálogo não está pronto: " + "; ".join(failed_checks)
            )
        return {
            "ready": True,
            "migration": CATALOGUE_MIGRATION,
            "tables": sorted(tables),
            "rls_tables": sorted(rls_tables),
            "triggers": sorted(triggers),
        }

    async def stage_catalogue(
        self,
        *,
        raw_document: PrivateRawDocument,
        archive_receipt: RawArchiveReceipt,
        manifest: GovernmentProgrammeCatalogueManifest,
        catalogue: GovernmentProgrammeCatalogue,
        staged_by_alias: str,
    ) -> dict[str, object]:
        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError("O catálogo do programa só pode ser persistido em staging privado")
        if self.pool is None:
            raise RuntimeError("Base de dados de staging não configurada")
        await self.require_catalogue_schema()
        actor_alias = staged_by_alias.strip()
        if len(actor_alias) < 3 or len(actor_alias) > 120:
            raise ValueError("O pseudónimo do processo de staging é inválido")
        if (
            archive_receipt.content_sha256 != raw_document.content_sha256
            or archive_receipt.byte_size != len(raw_document.content)
            or str(archive_receipt.source_url) != str(raw_document.source_url)
            or catalogue.source_sha256 != raw_document.content_sha256
            or catalogue.source_byte_size != len(raw_document.content)
        ):
            raise ValueError("O catálogo não coincide com os bytes oficiais previamente arquivados")
        if (
            len(catalogue.candidates) != manifest.expected_candidate_count
            or len(catalogue.coverage) != len(manifest.blocks)
            or catalogue.catalogue_sha256 != manifest.expected_catalogue_sha256
        ):
            raise ValueError("O catálogo extraído não coincide com o manifesto revisto")
        verify_government_programme_catalogue(catalogue=catalogue, manifest=manifest)

        snapshot_id = _new_deterministic_id(
            "government_programme_snapshot",
            (
                f"{catalogue.source_sha256}:{manifest.methodology_version}:"
                f"{catalogue.catalogue_sha256}"
            ),
        )
        source_document_id: str | None = None
        attestation_created = False
        snapshot_created = False
        sync_id = await self._start_sync_run(
            source_name="GOVERNMENT_PROGRAMME_XXV_CATALOGUE_PRIVATE",
            dataset_url=str(raw_document.source_url),
            code_version=manifest.parser_version,
        )

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    (
                        f"government-programme-catalogue:{manifest.government_number}:"
                        f"{catalogue.source_sha256}"
                    ),
                )
                source_document_id = await self._ensure_source_document(
                    connection,
                    publisher="OTHER_OFFICIAL",
                    kind="GOVERNMENT_PROGRAMME",
                    title=manifest.title,
                    url=str(raw_document.source_url),
                    retrieved_at=raw_document.retrieved_at,
                    content_sha256=raw_document.content_sha256,
                    mime_type=raw_document.mime_type,
                    parser_version=manifest.parser_version,
                )
                attestation = await self._attest_source_archive(
                    connection,
                    source_document_id=source_document_id,
                    receipt=archive_receipt,
                    archived_by=f"staging:{actor_alias}",
                )
                attestation_created = bool(attestation["created"])
                existing = await connection.fetchrow(
                    """
                    SELECT id, source_content_sha256, layout_manifest_sha256,
                           catalogue_sha256, candidate_count, coverage_block_count,
                           publication_performed
                    FROM government_programme_snapshots
                    WHERE source_document_id = $1 AND methodology_version = $2
                    """,
                    source_document_id,
                    manifest.methodology_version,
                )
                snapshot_created = existing is None
                if existing is not None:
                    observed = (
                        str(existing["id"]),
                        str(existing["source_content_sha256"]),
                        str(existing["layout_manifest_sha256"]),
                        str(existing["catalogue_sha256"]),
                        int(existing["candidate_count"]),
                        int(existing["coverage_block_count"]),
                        bool(existing["publication_performed"]),
                    )
                    expected = (
                        snapshot_id,
                        catalogue.source_sha256,
                        catalogue.layout_manifest_sha256,
                        catalogue.catalogue_sha256,
                        len(catalogue.candidates),
                        len(catalogue.coverage),
                        False,
                    )
                    if observed != expected:
                        raise ValueError(
                            "A fotografia existente diverge do mesmo PDF e metodologia"
                        )
                    coverage_rows = await connection.fetch(
                        """
                        SELECT block_id, part, area, section_path, start_page, end_page,
                               start_anchor, end_anchor, candidate_count, block_sha256
                        FROM government_promise_catalogue_coverage
                        WHERE snapshot_id = $1
                        ORDER BY block_id
                        """,
                        snapshot_id,
                    )
                    observed_coverage = [
                        (
                            str(row["block_id"]),
                            str(row["part"]),
                            str(row["area"]),
                            str(row["section_path"]),
                            int(row["start_page"]),
                            int(row["end_page"]),
                            str(row["start_anchor"]),
                            str(row["end_anchor"]) if row["end_anchor"] is not None else None,
                            int(row["candidate_count"]),
                            str(row["block_sha256"]),
                        )
                        for row in coverage_rows
                    ]
                    expected_coverage = sorted(
                        [
                            (
                                item.block_id,
                                item.part,
                                item.area,
                                item.section_path,
                                item.start_page,
                                item.end_page,
                                item.start_anchor,
                                item.end_anchor,
                                item.candidate_count,
                                item.block_sha256,
                            )
                            for item in catalogue.coverage
                        ],
                        key=lambda item: item[0],
                    )
                    candidate_rows = await connection.fetch(
                        """
                        SELECT candidate_key, block_id, ordinal, parent_ordinal,
                               hierarchy_level, source_marker, area, section_path,
                               programme_page_start, programme_page_end, statement_text,
                               statement_sha256, source_locator_sha256
                        FROM government_promise_candidates
                        WHERE snapshot_id = $1
                        ORDER BY block_id, ordinal
                        """,
                        snapshot_id,
                    )
                    observed_candidates = [
                        (
                            str(row["candidate_key"]),
                            str(row["block_id"]),
                            int(row["ordinal"]),
                            int(row["parent_ordinal"])
                            if row["parent_ordinal"] is not None
                            else None,
                            int(row["hierarchy_level"]),
                            str(row["source_marker"]),
                            str(row["area"]),
                            str(row["section_path"]),
                            int(row["programme_page_start"]),
                            int(row["programme_page_end"]),
                            str(row["statement_text"]),
                            str(row["statement_sha256"]),
                            str(row["source_locator_sha256"]),
                        )
                        for row in candidate_rows
                    ]
                    expected_candidates = sorted(
                        [
                            (
                                item.candidate_key,
                                item.block_id,
                                item.ordinal,
                                item.parent_ordinal,
                                item.hierarchy_level,
                                item.source_marker,
                                item.area,
                                item.section_path,
                                item.programme_page_start,
                                item.programme_page_end,
                                item.statement_text,
                                item.statement_sha256,
                                item.source_locator_sha256,
                            )
                            for item in catalogue.candidates
                        ],
                        key=lambda item: (item[1], item[2]),
                    )
                    if (
                        observed_coverage != expected_coverage
                        or observed_candidates != expected_candidates
                    ):
                        raise ValueError(
                            "Os registos privados existentes divergem do catálogo validado"
                        )
                else:
                    observed_at = _database_timestamp(raw_document.retrieved_at)
                    await connection.execute(
                        """
                        INSERT INTO government_programme_snapshots
                            (id, government_number, title, source_document_id,
                             source_content_sha256, source_byte_size, source_page_count,
                             methodology_version, parser_version,
                             layout_manifest_sha256, catalogue_sha256,
                             candidate_count, coverage_block_count, catalogue_state,
                             publication_performed, observed_at, staged_by_alias, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                                $12, $13, 'PRIVATE_PENDING_REVIEW', FALSE, $14, $15, NOW())
                        """,
                        snapshot_id,
                        manifest.government_number,
                        manifest.title,
                        source_document_id,
                        catalogue.source_sha256,
                        catalogue.source_byte_size,
                        catalogue.source_page_count,
                        manifest.methodology_version,
                        manifest.parser_version,
                        catalogue.layout_manifest_sha256,
                        catalogue.catalogue_sha256,
                        len(catalogue.candidates),
                        len(catalogue.coverage),
                        observed_at,
                        actor_alias,
                    )
                    await connection.executemany(
                        """
                        INSERT INTO government_promise_catalogue_coverage
                            (id, snapshot_id, block_id, part, area, section_path,
                             start_page, end_page, start_anchor, end_anchor,
                             extraction_state, candidate_count, block_sha256, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                                'EXTRACTED', $11, $12, NOW())
                        """,
                        [
                            (
                                _new_deterministic_id(
                                    "government_programme_coverage",
                                    f"{snapshot_id}:{item.block_id}",
                                ),
                                snapshot_id,
                                item.block_id,
                                item.part,
                                item.area,
                                item.section_path,
                                item.start_page,
                                item.end_page,
                                item.start_anchor,
                                item.end_anchor,
                                item.candidate_count,
                                item.block_sha256,
                            )
                            for item in catalogue.coverage
                        ],
                    )
                    await connection.executemany(
                        """
                        INSERT INTO government_promise_candidates
                            (id, snapshot_id, candidate_key, block_id, ordinal,
                             parent_ordinal, hierarchy_level, source_marker, area,
                             section_path, programme_page_start, programme_page_end,
                             statement_text, statement_sha256, source_locator_sha256,
                             identification_basis, criterion_state, review_state,
                             publication_state, publication_performed, observed_at,
                             created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                                $12, $13, $14, $15,
                                'EXPLICIT_ENUMERATED_PROGRAMME_ITEM',
                                'REQUIRES_HUMAN_DEFINITION', 'PENDING',
                                'PRIVATE_NOT_PUBLISHED', FALSE, $16, NOW())
                        """,
                        [
                            (
                                _new_deterministic_id(
                                    "government_promise_candidate",
                                    f"{snapshot_id}:{item.candidate_key}",
                                ),
                                snapshot_id,
                                item.candidate_key,
                                item.block_id,
                                item.ordinal,
                                item.parent_ordinal,
                                item.hierarchy_level,
                                item.source_marker,
                                item.area,
                                item.section_path,
                                item.programme_page_start,
                                item.programme_page_end,
                                item.statement_text,
                                item.statement_sha256,
                                item.source_locator_sha256,
                                observed_at,
                            )
                            for item in catalogue.candidates
                        ],
                    )
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'GOVERNMENT_PROGRAMME_CATALOGUE', $2,
                                'STAGED_PRIVATE', $3, NULL, $4::jsonb, $5, NOW())
                        """,
                        _new_deterministic_id("audit", f"{snapshot_id}:staged"),
                        snapshot_id,
                        actor_alias,
                        _canonical_json(
                            {
                                "source_document_id": source_document_id,
                                "source_content_sha256": catalogue.source_sha256,
                                "layout_manifest_sha256": catalogue.layout_manifest_sha256,
                                "catalogue_sha256": catalogue.catalogue_sha256,
                                "candidate_count": len(catalogue.candidates),
                                "coverage_block_count": len(catalogue.coverage),
                                "catalogue_state": "PRIVATE_PENDING_REVIEW",
                                "criteria_defined": False,
                                "human_review_performed": False,
                                "publication_performed": False,
                            }
                        ),
                        (
                            "Itens explicitamente enumerados preservados como candidatos "
                            "privados; sem critério automático, revisão ou publicação."
                        ),
                    )

            await self._finish_sync_run(
                sync_id,
                status_value="SUCCEEDED",
                records_read=len(catalogue.candidates),
                records_written=len(catalogue.candidates) if snapshot_created else 0,
                warnings=[
                    "Cada item permanece PENDING e exige critério e revisão humana explícitos."
                ],
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=len(catalogue.candidates),
                records_written=0,
                warnings=[],
                error_message=str(exc),
            )
            raise

        if source_document_id is None:
            raise RuntimeError("O documento-fonte não foi associado ao catálogo privado")
        return {
            "status": "STAGED_PRIVATE_PENDING_REVIEW",
            "snapshot_id": snapshot_id,
            "source_document_id": source_document_id,
            "source_sha256": catalogue.source_sha256,
            "catalogue_sha256": catalogue.catalogue_sha256,
            "candidate_count": len(catalogue.candidates),
            "coverage_block_count": len(catalogue.coverage),
            "snapshot_created": snapshot_created,
            "archive_attestation_created": attestation_created,
            "criteria_defined": False,
            "human_review_performed": False,
            "publication_performed": False,
            "public_promises_created": 0,
            "promise_reviews_created": 0,
        }
