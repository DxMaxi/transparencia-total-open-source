from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal

import asyncpg

PublicationScope = Literal["activity", "votes"]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ParliamentSnapshotPublicationRepository:
    """Revisão humana append-only das fotografias parlamentares privadas."""

    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self.pool = pool

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        return self.pool

    @staticmethod
    async def _snapshot(
        connection: asyncpg.Connection,
        *,
        legislature: str,
        lock: bool = False,
    ) -> dict[str, Any]:
        query = """
            SELECT snapshot.id, snapshot.source_document_id, snapshot.legislature,
                   snapshot.parser_version, snapshot.normalised_sha256,
                   snapshot.collected_at, snapshot.session_count,
                   snapshot.initiative_count, snapshot.vote_count,
                   snapshot.vote_record_count, source.url AS source_url,
                   source.content_sha256 AS source_sha256,
                   source.retrieved_at AS source_retrieved_at,
                   archive.id AS archive_attestation_id,
                   activity_review.publishable AS activity_publishable,
                   activity_review.reviewed_at AS activity_reviewed_at,
                   vote_review.publishable AS votes_publishable,
                   vote_review.reviewed_at AS votes_reviewed_at
            FROM parliament_activity_snapshots snapshot
            JOIN source_documents source ON source.id = snapshot.source_document_id
            LEFT JOIN LATERAL (
                SELECT attestation.id
                FROM source_archive_attestations attestation
                WHERE attestation.source_document_id = source.id
                  AND attestation.content_sha256 = source.content_sha256
                  AND attestation.retrieval_url = source.url
                ORDER BY attestation.archived_at DESC, attestation.id DESC
                LIMIT 1
            ) archive ON TRUE
            LEFT JOIN LATERAL (
                SELECT review.publishable, review.reviewed_at
                FROM data_publication_reviews review
                WHERE review.entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'
                  AND review.entity_id = snapshot.id
                  AND review.source_document_id = source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) activity_review ON TRUE
            LEFT JOIN LATERAL (
                SELECT review.publishable, review.reviewed_at
                FROM data_publication_reviews review
                WHERE review.entity_type = 'PARLIAMENT_VOTES_SNAPSHOT'
                  AND review.entity_id = snapshot.id
                  AND review.source_document_id = source.id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) vote_review ON TRUE
            WHERE snapshot.legislature = $1
              AND source.publisher = 'PARLIAMENT'
            ORDER BY snapshot.collected_at DESC, snapshot.created_at DESC, snapshot.id DESC
            LIMIT 1
        """
        if lock:
            query += " FOR UPDATE OF snapshot"
        row = await connection.fetchrow(query, legislature)
        if row is None:
            raise ValueError(f"Não existe fotografia parlamentar para {legislature}")

        actual = await connection.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM parliamentary_sessions
                 WHERE snapshot_id = $1) AS sessions,
                (SELECT COUNT(*) FROM parliamentary_initiatives
                 WHERE snapshot_id = $1) AS initiatives,
                (SELECT COUNT(*) FROM vote_events
                 WHERE snapshot_id = $1) AS votes,
                (SELECT COUNT(*) FROM vote_records record
                 JOIN vote_events event ON event.id = record.vote_event_id
                 WHERE event.snapshot_id = $1
                   AND record.source_document_id = $2) AS vote_records
            """,
            row["id"],
            row["source_document_id"],
        )
        if actual is None:
            raise RuntimeError("Não foi possível validar a fotografia parlamentar")
        expected_counts = {
            "sessions": int(row["session_count"]),
            "initiatives": int(row["initiative_count"]),
            "votes": int(row["vote_count"]),
            "vote_records": int(row["vote_record_count"]),
        }
        actual_counts = {key: int(actual[key]) for key in expected_counts}
        if actual_counts != expected_counts:
            raise ValueError(
                "A fotografia parlamentar diverge do manifesto imutável: "
                f"esperado={expected_counts}, observado={actual_counts}"
            )
        return {
            "snapshot_id": str(row["id"]),
            "source_document_id": str(row["source_document_id"]),
            "legislature": str(row["legislature"]),
            "parser_version": str(row["parser_version"]),
            "normalised_sha256": str(row["normalised_sha256"]),
            "collected_at": row["collected_at"],
            "source_url": str(row["source_url"]),
            "source_sha256": str(row["source_sha256"]),
            "source_retrieved_at": row["source_retrieved_at"],
            "archive_attested": row["archive_attestation_id"] is not None,
            "counts": expected_counts,
            "reviews": {
                "activity": {
                    "publishable": row["activity_publishable"],
                    "reviewed_at": row["activity_reviewed_at"],
                },
                "votes": {
                    "publishable": row["votes_publishable"],
                    "reviewed_at": row["votes_reviewed_at"],
                },
            },
            "publication_eligible": row["archive_attestation_id"] is not None,
            "publication_rule": (
                "A pré-visualização não publica. URL, SHA-256, hash normalizado e "
                "quatro contagens têm de ser confirmados por um revisor humano."
            ),
        }

    async def inspect(self, *, legislature: str) -> dict[str, Any]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            return await self._snapshot(connection, legislature=legislature)

    @staticmethod
    async def append_scope_decision(
        connection: asyncpg.Connection,
        *,
        scope: PublicationScope,
        snapshot_id: str,
        source_document_id: str,
        legislature: str,
        publishable: bool,
        source_sha256: str,
        normalised_sha256: str,
        counts: dict[str, int],
        reviewer_alias: str,
        rationale: str,
        before: dict[str, object],
        audit_context: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        """Acrescenta a porta pública V4 numa transação já aberta."""

        entity_types = {
            "activity": "PARLIAMENT_ACTIVITY_SNAPSHOT",
            "votes": "PARLIAMENT_VOTES_SNAPSHOT",
        }
        if scope not in entity_types:
            raise ValueError("Âmbito de revisão parlamentar inválido")
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
            raise ValueError("O SHA-256 da fonte é inválido")
        if not re.fullmatch(r"[0-9a-f]{64}", normalised_sha256):
            raise ValueError("O SHA-256 normalizado é inválido")
        if set(counts) != {"sessions", "initiatives", "votes", "vote_records"}:
            raise ValueError("As quatro contagens esperadas são obrigatórias")
        if any(value < 0 for value in counts.values()):
            raise ValueError("As contagens esperadas não podem ser negativas")
        alias = reviewer_alias.strip()
        reason = rationale.strip()
        if len(alias) < 3:
            raise ValueError("O pseudónimo do revisor é demasiado curto")
        if len(reason) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres")

        entity_type = entity_types[scope]
        publication_review_id = _new_id("publication_review")
        audit_event_id = _new_id("audit")
        after: dict[str, object] = {
            "publishable": publishable,
            "scope": scope,
            "legislature": legislature,
            "source_sha256": source_sha256,
            "normalised_sha256": normalised_sha256,
            "counts": dict(counts),
        }
        if audit_context is not None:
            after["editorial_link"] = audit_context

        reviewed_at = await connection.fetchval(
            """
            SELECT GREATEST(
                (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3),
                COALESCE(
                    $1::timestamp(3) + interval '1 millisecond',
                    '-infinity'::timestamp
                )
            )
            """,
            before.get("reviewed_at"),
        )
        if not isinstance(reviewed_at, datetime):
            raise RuntimeError("Não foi possível obter a data da revisão pública")

        await connection.execute(
            """
            INSERT INTO data_publication_reviews
                (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                 necessity_assessment, proportionality_test, publishable,
                 source_document_id, reviewed_by, reviewed_at)
            VALUES ($1, $2, $3,
                    'Informação factual necessária à fiscalização democrática',
                    'PUBLIC_INTEREST', 'PUBLIC_OFFICIAL',
                    'A fonte, o arquivo, o hash normalizado e as contagens foram revistos.',
                    'Publica apenas campos oficiais e mantém proveniência e limitações.',
                    $4, $5, $6, $7)
            """,
            publication_review_id,
            entity_type,
            snapshot_id,
            publishable,
            source_document_id,
            alias,
            reviewed_at,
        )
        await connection.execute(
            """
            INSERT INTO audit_events
                (id, entity_type, entity_id, action, actor_alias,
                 before_json, after_json, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9)
            """,
            audit_event_id,
            entity_type,
            snapshot_id,
            "PUBLISHED" if publishable else "WITHDRAWN",
            alias,
            json.dumps(before, default=str, ensure_ascii=False),
            json.dumps(after, ensure_ascii=False),
            reason,
            reviewed_at,
        )
        return {
            "scope": scope,
            **after,
            "publication_review_id": publication_review_id,
            "audit_event_id": audit_event_id,
            "reviewed_at": reviewed_at,
        }

    async def review(
        self,
        *,
        legislature: str,
        scopes: set[PublicationScope],
        publishable: bool,
        expected_source_sha256: str,
        expected_normalised_sha256: str,
        expected_counts: dict[str, int],
        reviewer_alias: str,
        rationale: str,
    ) -> dict[str, Any]:
        pool = self._require_pool()
        if not scopes or not scopes <= {"activity", "votes"}:
            raise ValueError("Âmbito de revisão parlamentar inválido")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256):
            raise ValueError("O SHA-256 da fonte é inválido")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_normalised_sha256):
            raise ValueError("O SHA-256 normalizado é inválido")
        if set(expected_counts) != {"sessions", "initiatives", "votes", "vote_records"}:
            raise ValueError("As quatro contagens esperadas são obrigatórias")
        if any(value < 0 for value in expected_counts.values()):
            raise ValueError("As contagens esperadas não podem ser negativas")
        if len(reviewer_alias.strip()) < 3:
            raise ValueError("O pseudónimo do revisor é demasiado curto")
        if len(rationale.strip()) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres")

        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"parliament-publication:{legislature}",
            )
            snapshot = await self._snapshot(
                connection,
                legislature=legislature,
                lock=True,
            )
            if snapshot["source_sha256"] != expected_source_sha256:
                raise ValueError("O SHA-256 da fonte não corresponde à fotografia mais recente")
            if snapshot["normalised_sha256"] != expected_normalised_sha256:
                raise ValueError("O SHA-256 normalizado não corresponde à fotografia mais recente")
            if snapshot["counts"] != expected_counts:
                raise ValueError("As contagens não correspondem à fotografia mais recente")
            if not snapshot["archive_attested"]:
                raise ValueError("A fonte não possui uma atestação de arquivo válida")
            if (
                publishable
                and "activity" in scopes
                and (expected_counts["sessions"] == 0 or expected_counts["initiatives"] == 0)
            ):
                raise ValueError(
                    "Sessões e iniciativas não podem ser publicadas com cobertura vazia"
                )
            if publishable and "votes" in scopes and expected_counts["votes"] == 0:
                raise ValueError("Votações não podem ser publicadas com cobertura vazia")

            decisions: list[dict[str, Any]] = []
            for scope in sorted(scopes):
                decisions.append(
                    await self.append_scope_decision(
                        connection,
                        scope=scope,
                        snapshot_id=snapshot["snapshot_id"],
                        source_document_id=snapshot["source_document_id"],
                        legislature=legislature,
                        publishable=publishable,
                        source_sha256=expected_source_sha256,
                        normalised_sha256=expected_normalised_sha256,
                        counts=expected_counts,
                        reviewer_alias=reviewer_alias,
                        rationale=rationale,
                        before=snapshot["reviews"][scope],
                    )
                )

        return {
            "snapshot_id": snapshot["snapshot_id"],
            "legislature": legislature,
            "source_url": snapshot["source_url"],
            "source_sha256": expected_source_sha256,
            "normalised_sha256": expected_normalised_sha256,
            "counts": expected_counts,
            "decisions": decisions,
            "publication_rule": "Cada decisão e evento de auditoria foi acrescentado ao histórico.",
        }
