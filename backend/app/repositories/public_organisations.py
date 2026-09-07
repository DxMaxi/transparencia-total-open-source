"""Leitura explícita das fotografias V5.53, sem qualquer recuo para dados legados."""

from __future__ import annotations

import re
from typing import Any

import asyncpg


class PublicOrganisationRepository:
    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self.pool = pool

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        return self.pool

    async def list(self, *, limit: int, offset: int) -> dict[str, Any]:
        pool = self._require_pool()
        where = """o.id ~ '^base_public_org_[0-9a-f]{32}$'
          AND o.publication_status = 'PUBLISHED' AND o.verification_status = 'VERIFIED'
          AND o.current_publication_snapshot_id = s.id
          AND EXISTS (SELECT 1 FROM editorial_publication_events e
            WHERE e.case_id=s.editorial_case_id AND e.version_id=s.editorial_version_id
              AND e.target_type='BASE_PUBLIC_ORGANISATION' AND e.target_id=o.id
              AND e.action='PUBLISH')"""
        async with (
            pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            total = await connection.fetchval(
                f"""SELECT COUNT(*)::int FROM organisations o
                     JOIN base_public_organisation_publication_snapshots s
                       ON s.organisation_id=o.id
                     WHERE {where}"""
            )
            rows = await connection.fetch(
                f"""SELECT o.id,s.legal_name,s.kind::text,s.registry_record_id,
                            s.public_record_sha256,s.created_at AS published_at
                     FROM organisations o
                     JOIN base_public_organisation_publication_snapshots s
                       ON s.organisation_id=o.id
                     WHERE {where}
                     ORDER BY s.legal_name COLLATE "C",o.id COLLATE "C"
                     LIMIT $1 OFFSET $2""",
                limit,
                offset,
            )
        return {
            "items": [dict(row) for row in rows],
            "total": int(total),
            "limit": limit,
            "offset": offset,
        }

    async def get(self, *, public_id: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"base_public_org_[0-9a-f]{32}", public_id):
            return None
        pool = self._require_pool()
        async with (
            pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            row = await connection.fetchrow(
                """SELECT o.id,s.legal_name,s.kind::text,s.registry_record_id,s.official_url,
                      s.source_record_sha256,s.public_record_sha256,s.created_at AS published_at,
                      source.title AS source_title,source.url AS source_url,
                      source.retrieved_at,source.content_sha256
               FROM organisations o
               JOIN base_public_organisation_publication_snapshots s
                 ON s.id=o.current_publication_snapshot_id AND s.organisation_id=o.id
               JOIN source_documents source ON source.id=s.source_document_id
               WHERE o.id=$1 AND o.publication_status='PUBLISHED'
                 AND o.verification_status='VERIFIED' AND source.publisher='JUSTICE_REGISTRY'
                 AND EXISTS (SELECT 1 FROM editorial_publication_events e
                   WHERE e.case_id=s.editorial_case_id AND e.version_id=s.editorial_version_id
                     AND e.target_type='BASE_PUBLIC_ORGANISATION' AND e.target_id=o.id
                     AND e.action='PUBLISH')""",
                public_id,
            )
            if row is None:
                return None
            replies = await connection.fetch(
                """SELECT public_reference,original_record_sha256,
                          claimant_public_name,claimant_role,
                      statement_text,statement_sha256,official_response_url,submitted_at
               FROM rights_of_reply WHERE target_type='ORGANISATION' AND target_id=$1
                 AND original_record_sha256=$2 AND status='PUBLISHED'
               ORDER BY submitted_at,id""",
                public_id,
                row["public_record_sha256"],
            )
        return {
            "id": row["id"],
            "legal_name": row["legal_name"],
            "kind": row["kind"],
            "registry_record_id": row["registry_record_id"],
            "official_url": row["official_url"],
            "source_record_sha256": row["source_record_sha256"],
            "public_record_sha256": row["public_record_sha256"],
            "published_at": row["published_at"],
            "source": {
                "publisher": "IRN",
                "title": row["source_title"],
                "url": row["source_url"],
                "retrieved_at": row["retrieved_at"],
                "content_sha256": row["content_sha256"],
            },
            "replies": [dict(item) for item in replies],
        }

    async def history(self, *, public_id: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"base_public_org_[0-9a-f]{32}", public_id):
            return None
        pool = self._require_pool()
        async with (
            pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            exists = await connection.fetchval(
                """SELECT EXISTS(
                       SELECT 1 FROM base_public_organisation_publication_snapshots
                       WHERE organisation_id=$1
                   )""",
                public_id,
            )
            if not exists:
                return None
            rows = await connection.fetch(
                """SELECT e.target_id AS public_id,e.action::text,s.public_record_sha256,
                      s.source_record_sha256,e.rationale AS public_rationale,
                      e.actor_alias,e.created_at AS occurred_at
               FROM editorial_publication_events e
               JOIN base_public_organisation_publication_snapshots s
                 ON s.editorial_case_id=e.case_id AND s.editorial_version_id=e.version_id
                AND s.organisation_id=e.target_id
               WHERE e.target_type='BASE_PUBLIC_ORGANISATION' AND e.target_id=$1
               ORDER BY e.created_at,e.id""",
                public_id,
            )
            replies = await connection.fetch(
                """SELECT reply.public_reference,reply.original_record_sha256,
                          reply.claimant_public_name,reply.claimant_role,
                          reply.statement_text,reply.statement_sha256,
                          reply.official_response_url,reply.submitted_at
                   FROM rights_of_reply reply
                   JOIN base_public_organisation_publication_snapshots snapshot
                     ON snapshot.organisation_id=reply.target_id
                    AND snapshot.public_record_sha256=reply.original_record_sha256
                   WHERE reply.target_type='ORGANISATION' AND reply.target_id=$1
                     AND reply.status='PUBLISHED'
                   ORDER BY reply.submitted_at,reply.id""",
                public_id,
            )
        return {
            "public_id": public_id,
            "items": [dict(row) for row in rows],
            "replies": [dict(row) for row in replies],
        }
