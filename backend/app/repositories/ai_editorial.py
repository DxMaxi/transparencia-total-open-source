"""Leituras privadas e fail-closed para propostas editoriais geradas por IA."""

import hashlib
import json
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from pydantic import HttpUrl

from app.core.security import require_official_url, sha256_text
from app.models.api import LegalDocument
from app.models.archive import RawArchiveReceipt
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.postgres import _archive_attestation_sha256, _millisecond_utc

_GENERATION_LOCK_KEY = "transparencia-total:ai-editorial-generation:v1"


@dataclass(frozen=True)
class AiDreSnapshot:
    snapshot_id: str
    source_document_id: str
    official_identifier: str | None
    title: str
    source_url: str
    source_content_sha256: str
    normalised_text_sha256: str
    extracted_text: str
    source_characters: int
    retrieved_at: datetime
    published_at: datetime | None
    collected_at: datetime
    parser_version: str
    archive_attestation_id: str
    archive_attestation_sha256: str
    archive_storage_backend: str
    archive_byte_size: int
    archive_archived_at: datetime

    def legal_document(self) -> LegalDocument:
        return LegalDocument(
            title=self.title,
            source_url=self.source_url,
            official_identifier=self.official_identifier,
            published_at=self.published_at,
            text=self.extracted_text,
            content_sha256=self.source_content_sha256,
            normalised_text_sha256=self.normalised_text_sha256,
        )


class AiEditorialRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    @asynccontextmanager
    async def generation_guard(self) -> AsyncIterator[None]:
        """Serializa pedidos de IA entre todas as instâncias da API.

        O bloqueio é deliberadamente fail-closed: não põe pedidos caros em fila
        nem depende de memória local do processo.
        """

        async with self.pool.acquire() as connection:
            acquired = await connection.fetchval(
                "SELECT pg_try_advisory_lock(hashtextextended($1, 0))",
                _GENERATION_LOCK_KEY,
            )
            if not acquired:
                raise EditorialConflictError(
                    "Já existe uma geração editorial de IA em curso; não foi chamado outro modelo"
                )
            try:
                yield
            finally:
                await connection.fetchval(
                    "SELECT pg_advisory_unlock(hashtextextended($1, 0))",
                    _GENERATION_LOCK_KEY,
                )

    async def load_dre_snapshot(self, snapshot_id: str) -> AiDreSnapshot:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT snapshot.id AS snapshot_id, snapshot.official_identifier,
                       snapshot.title, snapshot.published_at, snapshot.collected_at,
                       snapshot.parser_version,
                       snapshot.normalised_text_sha256, snapshot.extracted_text,
                       snapshot.text_length, source.id AS source_document_id,
                       source.url AS source_url, source.retrieved_at,
                       source.content_sha256 AS source_content_sha256,
                       archive.id AS archive_attestation_id,
                       archive.storage_backend, archive.storage_key,
                       archive.content_sha256 AS archive_content_sha256,
                       archive.byte_size, archive.mime_type AS archive_mime_type,
                       archive.retrieval_url, archive.retrieved_at AS archive_retrieved_at,
                       archive.archived_at, archive.archived_by,
                       archive.attestation_sha256
                FROM dre_document_snapshots snapshot
                JOIN source_documents source ON source.id = snapshot.source_document_id
                JOIN sync_runs run ON run.id = snapshot.sync_run_id
                JOIN LATERAL (
                    SELECT candidate.id, candidate.storage_backend,
                           candidate.storage_key, candidate.content_sha256,
                           candidate.byte_size, candidate.mime_type,
                           candidate.retrieval_url, candidate.retrieved_at,
                           candidate.archived_at, candidate.archived_by,
                           candidate.attestation_sha256
                    FROM source_archive_attestations candidate
                    WHERE candidate.source_document_id = source.id
                      AND candidate.content_sha256 = source.content_sha256
                      AND candidate.retrieval_url = source.url
                      AND candidate.retrieved_at = source.retrieved_at
                    ORDER BY candidate.archived_at DESC, candidate.id DESC
                    LIMIT 1
                ) archive ON TRUE
                WHERE snapshot.id = $1
                  AND source.publisher = 'DRE'
                  AND source.kind IN ('LAW', 'REGULATION')
                  AND source.url LIKE 'https://%'
                  AND run.status = 'SUCCEEDED'
                  AND run.finished_at IS NOT NULL
                """,
                snapshot_id,
            )
        if row is None:
            raise EditorialSourceError(
                "O snapshot DRE não existe, não terminou ou não possui arquivo oficial atestado"
            )

        return _snapshot_from_row(row)

    async def list_dre_snapshots(
        self,
        *,
        query: str | None,
        limit: int,
    ) -> tuple[list[AiDreSnapshot], int]:
        """Lista apenas candidatos DRE que passam novamente as provas criptográficas."""

        search = query.strip() if query else None
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            search = f"%{escaped}%"
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT snapshot.id AS snapshot_id, snapshot.official_identifier,
                       snapshot.title, snapshot.published_at, snapshot.collected_at,
                       snapshot.parser_version, snapshot.normalised_text_sha256,
                       snapshot.extracted_text, snapshot.text_length,
                       source.id AS source_document_id, source.url AS source_url,
                       source.retrieved_at,
                       source.content_sha256 AS source_content_sha256,
                       archive.id AS archive_attestation_id,
                       archive.storage_backend, archive.storage_key,
                       archive.content_sha256 AS archive_content_sha256,
                       archive.byte_size, archive.mime_type AS archive_mime_type,
                       archive.retrieval_url, archive.retrieved_at AS archive_retrieved_at,
                       archive.archived_at, archive.archived_by,
                       archive.attestation_sha256
                FROM dre_document_snapshots snapshot
                JOIN source_documents source ON source.id = snapshot.source_document_id
                JOIN sync_runs run ON run.id = snapshot.sync_run_id
                JOIN LATERAL (
                    SELECT candidate.id, candidate.storage_backend,
                           candidate.storage_key, candidate.content_sha256,
                           candidate.byte_size, candidate.mime_type,
                           candidate.retrieval_url, candidate.retrieved_at,
                           candidate.archived_at, candidate.archived_by,
                           candidate.attestation_sha256
                    FROM source_archive_attestations candidate
                    WHERE candidate.source_document_id = source.id
                      AND candidate.content_sha256 = source.content_sha256
                      AND candidate.retrieval_url = source.url
                      AND candidate.retrieved_at = source.retrieved_at
                    ORDER BY candidate.archived_at DESC, candidate.id DESC
                    LIMIT 1
                ) archive ON TRUE
                WHERE source.publisher = 'DRE'
                  AND source.kind IN ('LAW', 'REGULATION')
                  AND source.url LIKE 'https://%'
                  AND run.status = 'SUCCEEDED'
                  AND run.finished_at IS NOT NULL
                  AND (
                      $1::text IS NULL
                      OR snapshot.title ILIKE $1 ESCAPE '\\'
                      OR COALESCE(snapshot.official_identifier, '') ILIKE $1 ESCAPE '\\'
                  )
                ORDER BY snapshot.published_at DESC NULLS LAST,
                         snapshot.collected_at DESC, snapshot.id DESC
                LIMIT $2
                """,
                search,
                limit,
            )

        snapshots: list[AiDreSnapshot] = []
        invalid_count = 0
        for row in rows:
            try:
                snapshots.append(_snapshot_from_row(row))
            except EditorialSourceError:
                invalid_count += 1
        return snapshots, invalid_count

    async def list_existing_proposals(
        self,
        *,
        subject_ids: list[str],
    ) -> dict[str, dict[str, object]]:
        if not subject_ids:
            return {}
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT c.id, c.subject_id, c.current_state, c.revision, c.updated_at,
                       version.version_number, version.normalized_sha256
                FROM editorial_cases c
                JOIN editorial_versions version ON version.id = c.current_version_id
                WHERE c.kind = 'AI_EXPLANATION'
                  AND c.subject_type = 'DRE_DOCUMENT_SNAPSHOT'
                  AND c.origin = 'AI'
                  AND c.subject_id = ANY($1::text[])
                """,
                subject_ids,
            )
        return {
            str(row["subject_id"]): {
                "id": str(row["id"]),
                "state": str(row["current_state"]),
                "revision": int(row["revision"]),
                "version_number": int(row["version_number"]),
                "normalized_sha256": str(row["normalized_sha256"]),
                "updated_at": _aware(row["updated_at"]),
            }
            for row in rows
        }

    async def load_ai_case_snapshot(
        self,
        case_id: str,
    ) -> tuple[dict[str, object], AiDreSnapshot]:
        """Reconstrói a ligação exata caso -> versão -> snapshot, sem aproximações."""

        case = await self.editorial.get_case(case_id)
        if (
            case.get("kind") != "AI_EXPLANATION"
            or case.get("subject_type") != "DRE_DOCUMENT_SNAPSHOT"
            or case.get("origin") != "AI"
        ):
            raise EditorialConflictError("O processo não pertence ao circuito editorial DRE de IA")

        versions = case.get("versions")
        if not isinstance(versions, list):
            raise EditorialSourceError("O processo de IA não contém uma versão verificável")
        current = next(
            (
                version
                for version in versions
                if isinstance(version, dict) and version.get("is_current")
            ),
            None,
        )
        normalized = current.get("normalized_data") if isinstance(current, dict) else None
        source_manifest = normalized.get("source") if isinstance(normalized, dict) else None
        snapshot_reference = (
            source_manifest.get("snapshot_reference_sha256")
            if isinstance(source_manifest, dict)
            else None
        )
        if not isinstance(snapshot_reference, str) or not re.fullmatch(
            r"[0-9a-f]{64}", snapshot_reference
        ):
            raise EditorialSourceError("A versão atual não conserva a referência do snapshot DRE")

        source = case.get("source")
        source_document_id = source.get("id") if isinstance(source, dict) else None
        if not isinstance(source_document_id, str):
            raise EditorialSourceError("A fonte do processo de IA é inválida")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id
                FROM dre_document_snapshots
                WHERE source_document_id = $1
                ORDER BY collected_at DESC, id DESC
                """,
                source_document_id,
            )
        matching_ids = [
            str(row["id"])
            for row in rows
            if hashlib.sha256(str(row["id"]).encode("utf-8")).hexdigest() == snapshot_reference
        ]
        if len(matching_ids) != 1:
            raise EditorialSourceError("A referência da versão não resolve um snapshot DRE único")

        snapshot = await self.load_dre_snapshot(matching_ids[0])
        checks = (
            snapshot.source_document_id == source_document_id,
            isinstance(source, dict)
            and source.get("content_sha256") == snapshot.source_content_sha256,
            isinstance(source_manifest, dict)
            and source_manifest.get("content_sha256") == snapshot.source_content_sha256,
            isinstance(source_manifest, dict)
            and source_manifest.get("normalised_text_sha256") == snapshot.normalised_text_sha256,
            isinstance(source_manifest, dict)
            and source_manifest.get("archive_attestation_sha256")
            == snapshot.archive_attestation_sha256,
        )
        if not all(checks):
            raise EditorialSourceError(
                "A versão atual e a prova oficial do snapshot DRE deixaram de coincidir"
            )
        return case, snapshot

    async def find_existing_proposal(
        self,
        *,
        subject_id: str,
        source_document_id: str,
    ) -> dict[str, object] | None:
        async with self.pool.acquire() as connection:
            case_id = await connection.fetchval(
                """
                SELECT id
                FROM editorial_cases
                WHERE kind = 'AI_EXPLANATION'
                  AND subject_type = 'DRE_DOCUMENT_SNAPSHOT'
                  AND subject_id = $1
                  AND source_document_id = $2
                  AND origin = 'AI'
                """,
                subject_id,
                source_document_id,
            )
        if case_id is None:
            return None
        return await self.editorial.get_case(str(case_id))

    async def count_ai_generation_attempts_today(self) -> int:
        async with self.pool.acquire() as connection:
            count = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM audit_events
                WHERE entity_type = 'AI_GENERATION_ATTEMPT'
                  AND action = 'REQUESTED'
                  AND created_at >= date_trunc('day', timezone('UTC', NOW()))
                """
            )
        return int(count)

    async def record_generation_event(
        self,
        *,
        attempt_id: str,
        action: str,
        actor_alias: str,
        metadata: dict[str, object],
    ) -> None:
        if action not in {"REQUESTED", "SUCCEEDED", "FAILED"}:
            raise ValueError("Evento de geração de IA inválido")
        await self.pool.execute(
            """
            INSERT INTO audit_events
                (id, entity_type, entity_id, action, actor_alias,
                 before_json, after_json, reason, created_at)
            VALUES ($1, 'AI_GENERATION_ATTEMPT', $2, $3, $4,
                    NULL, $5::jsonb, $6, timezone('UTC', NOW()))
            """,
            f"audit_ai_{uuid.uuid4().hex}",
            attempt_id,
            action,
            actor_alias,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            "Evento técnico privado do circuito editorial responsável de IA.",
        )


def _snapshot_from_row(row: asyncpg.Record) -> AiDreSnapshot:
    text = str(row["extracted_text"])
    try:
        source_url = require_official_url(str(row["source_url"]))
    except ValueError as exc:
        raise EditorialSourceError("O URL oficial do snapshot DRE é inválido") from exc
    source_hash = str(row["source_content_sha256"])
    normalised_hash = str(row["normalised_text_sha256"])
    retrieved_at = _aware(row["archive_retrieved_at"])
    archived_at = _aware(row["archived_at"])
    try:
        receipt = RawArchiveReceipt(
            storage_backend=str(row["storage_backend"]),
            storage_key=str(row["storage_key"]),
            content_sha256=str(row["archive_content_sha256"]),
            byte_size=int(row["byte_size"]),
            mime_type=row["archive_mime_type"],
            source_url=HttpUrl(source_url),
            retrieved_at=retrieved_at,
            recorded_at=archived_at,
            object_created=False,
        )
        expected_attestation_sha256 = _archive_attestation_sha256(
            source_document_id=str(row["source_document_id"]),
            receipt=receipt,
            archived_at=_millisecond_utc(archived_at),
            archived_by=str(row["archived_by"]),
        )
    except (TypeError, ValueError) as exc:
        raise EditorialSourceError("A atestação privada do snapshot DRE é inválida") from exc
    checks = (
        len(text) == int(row["text_length"]),
        sha256_text(text) == normalised_hash,
        str(row["archive_content_sha256"]) == source_hash,
        str(row["retrieval_url"]) == str(row["source_url"]),
        row["archive_retrieved_at"] == row["retrieved_at"],
        bool(re.fullmatch(r"[0-9a-f]{64}", source_hash)),
        bool(re.fullmatch(r"[0-9a-f]{64}", normalised_hash)),
        expected_attestation_sha256 == str(row["attestation_sha256"]),
    )
    if not text.strip() or not all(checks):
        raise EditorialSourceError(
            "O snapshot DRE ou a respetiva atestação falhou a verificação criptográfica"
        )

    return AiDreSnapshot(
        snapshot_id=str(row["snapshot_id"]),
        source_document_id=str(row["source_document_id"]),
        official_identifier=row["official_identifier"],
        title=str(row["title"]),
        source_url=source_url,
        source_content_sha256=source_hash,
        normalised_text_sha256=normalised_hash,
        extracted_text=text,
        source_characters=len(text),
        retrieved_at=_aware(row["retrieved_at"]),
        published_at=(_aware(row["published_at"]) if row["published_at"] is not None else None),
        collected_at=_aware(row["collected_at"]),
        parser_version=str(row["parser_version"]),
        archive_attestation_id=str(row["archive_attestation_id"]),
        archive_attestation_sha256=str(row["attestation_sha256"]),
        archive_storage_backend=str(row["storage_backend"]),
        archive_byte_size=int(row["byte_size"]),
        archive_archived_at=archived_at,
    )


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def ai_subject_id(
    *,
    snapshot_id: str,
    provider: str,
    model: str,
    prompt_sha256: str,
) -> str:
    canonical = "\n".join((snapshot_id, provider, model, prompt_sha256))
    return f"dre_ai_{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
