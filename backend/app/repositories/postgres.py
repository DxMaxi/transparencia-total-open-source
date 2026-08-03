import hashlib
import json
import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import require_official_url
from app.models.api import (
    BaseContractCollection,
    ParliamentDataset,
    PushSubscriptionRequest,
    RightOfReplyReceipt,
    RightOfReplyRequest,
)
from app.models.archive import RawArchiveReceipt

logger = logging.getLogger(__name__)

PUBLICATION_RULE = (
    "Apenas registos aprovados segundo a regra explícita do respetivo conjunto; "
    "a ingestão nunca equivale a publicação."
)

BASE_PERSISTENCE_DISABLED_MESSAGE = (
    "A persistência BASE está bloqueada nesta versão: estão disponíveis apenas a "
    "pré-visualização e o ficheiro JSON privado para revisão. A persistência só poderá "
    "ser reativada com carga em lote append-only e atestação explícita de staging."
)

_PUBLISHER_CODES = {
    "PARLIAMENT": "AR",
    "DRE": "DRE",
    "TRANSPARENCY_ENTITY": "EPT",
    "BASE_GOV": "BASE",
    "COURT_OF_AUDIT": "TCONTAS",
    "EUROPEAN_PARLIAMENT": "PE",
    "PUBLIC_PROSECUTOR": "MP",
    "COURT": "TRIBUNAL",
    "MEDIA": "MEDIA",
    "SNS": "SNS",
    "MUNICIPALITY": "MUNICIPIO",
    "OTHER_OFFICIAL": "OFICIAL",
}

_PUBLISHER_LABELS = {
    "PARLIAMENT": "Assembleia da República — fonte oficial",
    "DRE": "Diário da República — diploma oficial",
    "TRANSPARENCY_ENTITY": "Entidade para a Transparência — fonte oficial",
    "BASE_GOV": "Portal BASE — contrato público",
    "COURT_OF_AUDIT": "Tribunal de Contas — fonte oficial",
    "EUROPEAN_PARLIAMENT": "Parlamento Europeu — fonte oficial",
    "PUBLIC_PROSECUTOR": "Ministério Público — fonte oficial",
    "COURT": "Tribunal — fonte oficial",
    "MEDIA": "Órgão de comunicação — documento publicado",
    "SNS": "Serviço Nacional de Saúde — fonte oficial",
    "MUNICIPALITY": "Município — fonte oficial",
    "OTHER_OFFICIAL": "Fonte oficial",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _normalise_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def _slug(value: str, source_id: str) -> str:
    base = _normalise_name(value).replace(" ", "-") or "pessoa"
    suffix = re.sub(r"[^a-zA-Z0-9]+", "-", source_id).strip("-").lower()
    return f"{base[:70]}-{suffix[:24]}"


def _source_from_row(row: Any, prefix: str = "source_") -> dict[str, Any]:
    publisher = str(row[f"{prefix}publisher"])
    return {
        "publisher": _PUBLISHER_CODES.get(publisher, "AR"),
        "label": _PUBLISHER_LABELS.get(publisher, "Fonte oficial"),
        "url": row[f"{prefix}url"],
        "retrieved_at": row[f"{prefix}retrieved_at"],
        "content_sha256": row[f"{prefix}sha256"],
    }


def _warning_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return 1 if value else 0


def _database_timestamp(value: datetime | None) -> datetime | None:
    """Normaliza datas para as colunas PostgreSQL TIMESTAMP(3) geridas pelo Prisma."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc_database_timestamp(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _millisecond_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("A atestação de arquivo exige datas com fuso horário")
    utc_value = value.astimezone(UTC)
    return utc_value.replace(microsecond=(utc_value.microsecond // 1000) * 1000)


def _archive_attestation_sha256(
    *,
    source_document_id: str,
    receipt: RawArchiveReceipt,
    archived_at: datetime,
    archived_by: str,
) -> str:
    canonical = json.dumps(
        {
            "source_document_id": source_document_id,
            "storage_backend": receipt.storage_backend,
            "storage_key": receipt.storage_key,
            "content_sha256": receipt.content_sha256,
            "byte_size": receipt.byte_size,
            "mime_type": receipt.mime_type,
            "retrieval_url": str(receipt.source_url),
            "retrieved_at": _millisecond_utc(receipt.retrieved_at).isoformat(),
            "archived_at": archived_at.isoformat(),
            "archived_by": archived_by,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PostgresRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self.settings.database_url is None:
            logger.warning("database_not_configured")
            return
        self.pool = await asyncpg.create_pool(
            self.settings.database_url.get_secret_value(),
            min_size=1,
            max_size=5,
            command_timeout=20,
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    @property
    def configured(self) -> bool:
        return self.pool is not None

    async def save_push_subscription(self, payload: PushSubscriptionRequest) -> str:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        body = payload.subscription.model_dump(mode="json")
        endpoint = str(payload.subscription.endpoint)
        subscription_id = hashlib.sha256(endpoint.encode()).hexdigest()
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO push_subscriptions
                    (id, endpoint, p256dh, auth, districts, municipalities,
                     is_active, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, true, NOW(), NOW())
                ON CONFLICT (endpoint) DO UPDATE SET
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    districts = EXCLUDED.districts,
                    municipalities = EXCLUDED.municipalities,
                    is_active = true,
                    updated_at = NOW()
                """,
                subscription_id,
                endpoint,
                body["keys"]["p256dh"],
                body["keys"]["auth"],
                json.dumps(payload.districts),
                json.dumps(payload.municipalities),
            )
        return subscription_id

    async def list_active_push_subscriptions(
        self,
        *,
        district: str | None = None,
        municipality: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.pool is None:
            return []
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, endpoint, p256dh, auth
                FROM push_subscriptions
                WHERE is_active = true
                  AND ($1::text IS NULL OR districts ? $1)
                  AND ($2::text IS NULL OR municipalities ? $2)
                """,
                district,
                municipality,
            )
        return [dict(row) for row in rows]

    async def save_right_of_reply(
        self,
        payload: RightOfReplyRequest,
        receipt: RightOfReplyReceipt,
    ) -> None:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """
                INSERT INTO rights_of_reply
                    (id, public_reference, target_type, target_id,
                     original_record_sha256, claimant_public_name, claimant_role,
                     statement_text, statement_sha256, official_response_url,
                     status, submitted_at, audit_sha256)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        'RECEIVED', $11, $12)
                """,
                receipt.audit_sha256[:25],
                receipt.public_reference,
                payload.target_type,
                payload.target_id,
                payload.original_record_sha256,
                payload.claimant_public_name,
                payload.claimant_role,
                payload.statement_text,
                receipt.statement_sha256,
                str(payload.official_response_url) if payload.official_response_url else None,
                _database_timestamp(receipt.submitted_at),
                receipt.audit_sha256,
            )
            await connection.execute(
                """
                INSERT INTO audit_events
                    (id, entity_type, entity_id, action, actor_alias,
                     before_json, after_json, reason, created_at)
                VALUES ($1, 'RIGHT_OF_REPLY', $2, 'RECEIVED', 'public-intake',
                        NULL, $3::jsonb, $4, $5)
                """,
                f"audit-{receipt.audit_sha256[:19]}",
                receipt.public_reference,
                json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False),
                "Submissão preservada; publicação depende de verificação humana",
                _database_timestamp(receipt.submitted_at),
            )

    async def get_public_data_status(self) -> dict[str, Any]:
        empty_counts = {
            "politicians": 0,
            "promises": 0,
            "contracts": 0,
            "relationships": 0,
            "news": 0,
            "citizen_alerts": 0,
        }
        canonical_sources = (
            "PARLIAMENT_DEPUTIES",
            "PARLIAMENT_VOTES",
            "BASE_CONTRACTS",
            "DRE",
            "TRANSPARENCY_ENTITY",
            "LOCAL_SNS",
        )
        if self.pool is None:
            return {
                "mode": "UNAVAILABLE",
                "database_configured": False,
                "counts": empty_counts,
                "sources": [
                    {"source_name": source, "status": "NEVER"} for source in canonical_sources
                ],
                "message": "Base de dados não configurada; nenhum dado é apresentado como real.",
            }

        async with self.pool.acquire() as connection:
            count_row = await connection.fetchrow(
                """
                SELECT
                  (
                    SELECT COUNT(*) FROM people p
                    WHERE p.active = TRUE
                      AND EXISTS (
                        SELECT 1 FROM parliamentary_membership_snapshots snapshot
                        WHERE snapshot.person_id = p.id
                      )
                      AND (
                        SELECT dpr.publishable
                        FROM data_publication_reviews dpr
                        WHERE dpr.entity_type = 'PERSON'
                          AND dpr.entity_id = p.id
                          AND dpr.source_document_id = (
                            SELECT snapshot.source_document_id
                            FROM parliamentary_membership_snapshots snapshot
                            WHERE snapshot.person_id = p.id
                            ORDER BY snapshot.observed_at DESC, snapshot.id DESC
                            LIMIT 1
                          )
                          AND EXISTS (
                            SELECT 1
                            FROM source_documents reviewed_source
                            JOIN source_archive_attestations reviewed_archive
                              ON reviewed_archive.source_document_id = reviewed_source.id
                            WHERE reviewed_source.id = dpr.source_document_id
                              AND reviewed_archive.content_sha256 =
                                  reviewed_source.content_sha256
                              AND reviewed_archive.retrieval_url = reviewed_source.url
                          )
                        ORDER BY dpr.reviewed_at DESC, dpr.id DESC LIMIT 1
                      ) = TRUE
                  ) AS politicians,
                  (
                    SELECT COUNT(*) FROM promises p
                    WHERE p.status IN ('FULFILLED', 'IN_PROGRESS', 'BROKEN', 'ABANDONED')
                      AND EXISTS (SELECT 1 FROM promise_evidence pe WHERE pe.promise_id = p.id)
                      AND EXISTS (
                        SELECT 1
                        FROM government_programmes gp
                        JOIN source_documents programme_source
                          ON programme_source.id = gp.source_document_id
                        JOIN source_archive_attestations programme_archive
                          ON programme_archive.source_document_id = programme_source.id
                        WHERE gp.id = p.programme_id
                          AND programme_archive.content_sha256 =
                              programme_source.content_sha256
                          AND programme_archive.retrieval_url = programme_source.url
                      )
                      AND EXISTS (
                        SELECT 1
                        FROM promise_evidence archived_proof
                        JOIN source_documents evidence_source
                          ON evidence_source.id = archived_proof.source_document_id
                        JOIN source_archive_attestations evidence_archive
                          ON evidence_archive.source_document_id = evidence_source.id
                        WHERE archived_proof.promise_id = p.id
                          AND evidence_archive.content_sha256 = evidence_source.content_sha256
                          AND evidence_archive.retrieval_url = evidence_source.url
                      )
                      AND (
                        SELECT pr.decision::text FROM promise_reviews pr
                        WHERE pr.promise_id = p.id
                        ORDER BY pr.reviewed_at DESC, pr.id DESC LIMIT 1
                      ) = 'ACCEPT'
                  ) AS promises,
                  (
                    SELECT COUNT(*)
                    FROM public_contracts contract
                    JOIN source_documents contract_source
                      ON contract_source.id = contract.source_document_id
                    WHERE contract.publication_status = 'PUBLISHED'
                      AND contract.verification_status = 'VERIFIED'
                      AND EXISTS (
                        SELECT 1
                        FROM source_archive_attestations contract_archive
                        WHERE contract_archive.source_document_id = contract_source.id
                          AND contract_archive.content_sha256 =
                              contract_source.content_sha256
                          AND contract_archive.retrieval_url = contract_source.url
                      )
                  ) AS contracts,
                  (
                    SELECT COUNT(*) FROM interest_relationships r
                    JOIN interest_entities f ON f.id = r.from_entity_id
                    JOIN interest_entities t ON t.id = r.to_entity_id
                    JOIN source_documents sd ON sd.id = r.source_document_id
                    WHERE r.publication_status = 'PUBLISHED'
                      AND r.verification_status = 'VERIFIED'
                      AND f.publication_status = 'PUBLISHED'
                      AND f.verification_status = 'VERIFIED'
                      AND t.publication_status = 'PUBLISHED'
                      AND t.verification_status = 'VERIFIED'
                      AND sd.publisher <> 'MEDIA'
                      AND EXISTS (
                        SELECT 1
                        FROM source_archive_attestations relationship_archive
                        WHERE relationship_archive.source_document_id = sd.id
                          AND relationship_archive.content_sha256 = sd.content_sha256
                          AND relationship_archive.retrieval_url = sd.url
                      )
                  ) AS relationships,
                  (
                    SELECT COUNT(*)
                    FROM news_articles article
                    JOIN source_documents article_source
                      ON article_source.id = article.source_document_id
                    WHERE article.publication_status = 'PUBLISHED'
                      AND article.review_status = 'VERIFIED_WITH_OFFICIAL_EVIDENCE'
                      AND EXISTS (
                        SELECT 1
                        FROM source_archive_attestations article_archive
                        WHERE article_archive.source_document_id = article_source.id
                          AND article_archive.content_sha256 = article_source.content_sha256
                          AND article_archive.retrieval_url = article_source.url
                      )
                      AND EXISTS (
                        SELECT 1
                        FROM news_evidence evidence
                        JOIN source_documents evidence_source
                          ON evidence_source.id = evidence.source_document_id
                        JOIN source_archive_attestations evidence_archive
                          ON evidence_archive.source_document_id = evidence_source.id
                        WHERE evidence.news_article_id = article.id
                          AND evidence_source.publisher <> 'MEDIA'
                          AND evidence_archive.content_sha256 = evidence_source.content_sha256
                          AND evidence_archive.retrieval_url = evidence_source.url
                      )
                  ) AS news,
                  (
                    SELECT COUNT(*)
                    FROM citizen_alerts alert
                    JOIN source_documents alert_source
                      ON alert_source.id = alert.source_document_id
                    WHERE alert.publication_status = 'PUBLISHED'
                      AND alert.requires_human_review = TRUE
                      AND EXISTS (
                        SELECT 1
                        FROM source_archive_attestations alert_archive
                        WHERE alert_archive.source_document_id = alert_source.id
                          AND alert_archive.content_sha256 = alert_source.content_sha256
                          AND alert_archive.retrieval_url = alert_source.url
                      )
                  ) AS citizen_alerts
                """
            )
            sync_rows = await connection.fetch(
                """
                SELECT DISTINCT ON (source_name)
                       source_name, dataset_url, status::text, started_at, finished_at,
                       records_read, records_written, warnings, code_version
                FROM sync_runs
                ORDER BY source_name, started_at DESC, id DESC
                """
            )

        counts = {key: int(count_row[key]) for key in empty_counts}
        latest = {str(row["source_name"]): row for row in sync_rows}
        source_names = [*canonical_sources]
        source_names.extend(sorted(name for name in latest if name not in canonical_sources))
        sources: list[dict[str, Any]] = []
        for name in source_names:
            row = latest.get(name)
            if row is None:
                sources.append({"source_name": name, "status": "NEVER"})
                continue
            sources.append(
                {
                    "source_name": name,
                    "status": row["status"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "records_read": row["records_read"],
                    "records_written": row["records_written"],
                    "warning_count": _warning_count(row["warnings"]),
                    "dataset_url": row["dataset_url"],
                    "code_version": row["code_version"],
                }
            )
        total = sum(counts.values())
        return {
            "mode": "LIVE" if total else "EMPTY",
            "database_configured": True,
            "counts": counts,
            "sources": sources,
            "message": (
                f"{total} registos aprovados estão disponíveis na API pública."
                if total
                else "A base está ligada, mas ainda não existem registos aprovados para publicação."
            ),
        }

    async def _public_person_rows(
        self,
        *,
        slug: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT p.id, p.slug,
                       COALESCE(p.parliamentary_name, p.full_name) AS name,
                       p.role::text AS role, p.photo_url,
                       COALESCE(pa.name, 'Sem filiação indicada') AS party,
                       COALESCE(pa.short_name, '—') AS party_short,
                       COALESCE(ms.constituency, 'Não disponível') AS constituency,
                       COALESCE(ms.legislature, 'Não disponível') AS legislature,
                       review.reviewed_at AS verified_at,
                       sd.publisher::text AS source_publisher,
                       sd.url AS source_url, sd.retrieved_at AS source_retrieved_at,
                       sd.content_sha256 AS source_sha256
                FROM people p
                JOIN LATERAL (
                    SELECT snapshot.party_id, snapshot.constituency, snapshot.legislature,
                           snapshot.source_document_id
                    FROM parliamentary_membership_snapshots snapshot
                    WHERE snapshot.person_id = p.id
                    ORDER BY snapshot.observed_at DESC, snapshot.id DESC LIMIT 1
                ) ms ON TRUE
                JOIN LATERAL (
                    SELECT dpr.publishable, dpr.reviewed_at
                    FROM data_publication_reviews dpr
                    WHERE dpr.entity_type = 'PERSON'
                      AND dpr.entity_id = p.id
                      AND dpr.source_document_id = ms.source_document_id
                    ORDER BY dpr.reviewed_at DESC, dpr.id DESC LIMIT 1
                ) review ON review.publishable = TRUE
                JOIN source_documents sd ON sd.id = ms.source_document_id
                LEFT JOIN parties pa ON pa.id = ms.party_id
                WHERE p.active = TRUE
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations profile_archive
                      WHERE profile_archive.source_document_id = sd.id
                        AND profile_archive.content_sha256 = sd.content_sha256
                        AND profile_archive.retrieval_url = sd.url
                  )
                  AND ($1::text IS NULL OR p.slug = $1)
                ORDER BY name, p.id
                LIMIT $2 OFFSET $3
                """,
                slug,
                limit,
                offset,
            )
        return list(rows)

    @staticmethod
    def _person_summary(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "role": row["role"],
            "party": row["party"],
            "party_short": row["party_short"],
            "constituency": row["constituency"],
            "legislature": row["legislature"],
            "portrait_url": row["photo_url"],
            "verified_at": row["verified_at"],
            "profile_source": _source_from_row(row),
        }

    async def list_public_politicians(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        rows = await self._public_person_rows(limit=limit, offset=offset)
        return [self._person_summary(row) for row in rows]

    async def get_public_politician(self, slug: str) -> dict[str, Any] | None:
        rows = await self._public_person_rows(slug=slug, limit=1)
        if not rows:
            return None
        row = rows[0]
        person = self._person_summary(row)
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            attendance = await connection.fetchrow(
                """
                SELECT COUNT(*) FILTER (WHERE ar.present IS NOT NULL) AS total,
                       COUNT(*) FILTER (WHERE ar.present = TRUE) AS present,
                       (
                           SELECT COUNT(*)
                           FROM vote_records available_record
                           JOIN vote_events available_event
                             ON available_event.id = available_record.vote_event_id
                           JOIN source_documents available_source
                             ON available_source.id = available_event.source_document_id
                           JOIN LATERAL (
                               SELECT review.publishable
                               FROM data_publication_reviews review
                               WHERE review.entity_type = 'PARLIAMENT_VOTES_SNAPSHOT'
                                 AND review.entity_id = available_event.source_document_id
                                 AND review.source_document_id = available_event.source_document_id
                               ORDER BY review.reviewed_at DESC, review.id DESC
                               LIMIT 1
                           ) latest_snapshot_review
                             ON latest_snapshot_review.publishable = TRUE
                           WHERE available_record.person_id = $1
                             AND available_record.actor_type = 'PERSON'
                             AND available_record.choice IN (
                                 'FAVOR', 'AGAINST', 'ABSTENTION', 'ABSENT'
                             )
                             AND available_record.source_document_id =
                                 available_event.source_document_id
                             AND available_event.is_nominal = TRUE
                             AND available_source.publisher = 'PARLIAMENT'
                             AND EXISTS (
                                 SELECT 1
                                 FROM source_archive_attestations available_archive
                                 WHERE available_archive.source_document_id =
                                       available_source.id
                                   AND available_archive.content_sha256 =
                                       available_source.content_sha256
                                   AND available_archive.retrieval_url =
                                       available_source.url
                             )
                       ) AS nominal_vote_count
                FROM mandates m
                JOIN attendance_records ar ON ar.mandate_id = m.id
                JOIN source_documents attendance_source
                  ON attendance_source.id = ar.source_document_id
                WHERE m.person_id = $1
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations attendance_archive
                      WHERE attendance_archive.source_document_id = attendance_source.id
                        AND attendance_archive.content_sha256 =
                            attendance_source.content_sha256
                        AND attendance_archive.retrieval_url = attendance_source.url
                  )
                """,
                row["id"],
            )
            vote_rows = await connection.fetch(
                """
                SELECT vr.id, ve.title, ve.voted_at, vr.choice::text AS choice,
                       COALESCE(ve.result, 'Resultado não indicado na fonte') AS result,
                       COALESCE(ve.initiative_number, 'Sem número indicado') AS initiative_number,
                       ve.is_nominal,
                       sd.publisher::text AS source_publisher,
                       sd.url AS source_url, sd.retrieved_at AS source_retrieved_at,
                       sd.content_sha256 AS source_sha256
                FROM vote_records vr
                JOIN vote_events ve ON ve.id = vr.vote_event_id
                JOIN source_documents sd ON sd.id = ve.source_document_id
                JOIN LATERAL (
                    SELECT review.publishable
                    FROM data_publication_reviews review
                    WHERE review.entity_type = 'PARLIAMENT_VOTES_SNAPSHOT'
                      AND review.entity_id = ve.source_document_id
                      AND review.source_document_id = ve.source_document_id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) latest_snapshot_review ON latest_snapshot_review.publishable = TRUE
                WHERE vr.person_id = $1 AND vr.actor_type = 'PERSON'
                  AND ve.is_nominal = TRUE
                  AND vr.choice IN ('FAVOR', 'AGAINST', 'ABSTENTION', 'ABSENT')
                  AND vr.source_document_id = ve.source_document_id
                  AND sd.publisher = 'PARLIAMENT'
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations vote_archive
                      WHERE vote_archive.source_document_id = sd.id
                        AND vote_archive.content_sha256 = sd.content_sha256
                        AND vote_archive.retrieval_url = sd.url
                  )
                ORDER BY ve.voted_at DESC NULLS LAST, ve.id DESC
                LIMIT 50
                """,
                row["id"],
            )
            declaration = await connection.fetchrow(
                """
                SELECT sd.publisher::text AS source_publisher,
                       sd.url AS source_url, sd.retrieved_at AS source_retrieved_at,
                       sd.content_sha256 AS source_sha256
                FROM asset_declaration_metadata adm
                JOIN source_documents sd ON sd.id = adm.source_document_id
                WHERE adm.person_id = $1
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations declaration_archive
                      WHERE declaration_archive.source_document_id = sd.id
                        AND declaration_archive.content_sha256 = sd.content_sha256
                        AND declaration_archive.retrieval_url = sd.url
                  )
                ORDER BY adm.declared_at DESC NULLS LAST, adm.created_at DESC
                LIMIT 1
                """,
                row["id"],
            )
        total = int(attendance["total"])
        present = int(attendance["present"])
        attendance_rate = round(present * 100 / total) if total else None
        nominal_vote_count = int(attendance["nominal_vote_count"])
        declaration_source = (
            _source_from_row(declaration)
            if declaration is not None
            else {
                "publisher": "EPT",
                "label": "Entidade para a Transparência — consulta oficial",
                "url": "https://www.tribunalconstitucional.pt/tc/ept/",
                "retrieved_at": datetime.now(UTC),
                "content_sha256": None,
            }
        )
        person.update(
            {
                "attendance_rate": attendance_rate,
                "attendance_label": (
                    f"{present} presenças em {total} registos oficiais com presença indicada."
                    if total
                    else "A fonte sincronizada não contém presenças individuais suficientes."
                ),
                "nominal_votes_available": nominal_vote_count > 0,
                "nominal_vote_count": nominal_vote_count,
                "declaration_source": declaration_source,
                "votes": [
                    {
                        "id": vote["id"],
                        "title": vote["title"],
                        "date": vote["voted_at"],
                        "choice": vote["choice"],
                        "result": vote["result"],
                        "initiative_number": vote["initiative_number"],
                        "source": _source_from_row(vote),
                        "is_nominal": vote["is_nominal"],
                    }
                    for vote in vote_rows
                ],
            }
        )
        return person

    async def list_public_promises(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                WITH selected AS (
                    SELECT p.*, latest_review.reviewed_at
                    FROM promises p
                    JOIN LATERAL (
                        SELECT pr.decision::text AS decision, pr.reviewed_at
                        FROM promise_reviews pr
                        WHERE pr.promise_id = p.id
                        ORDER BY pr.reviewed_at DESC, pr.id DESC LIMIT 1
                    ) latest_review ON latest_review.decision = 'ACCEPT'
                    JOIN government_programmes selected_programme
                      ON selected_programme.id = p.programme_id
                    JOIN source_documents selected_programme_source
                      ON selected_programme_source.id = selected_programme.source_document_id
                    WHERE p.status IN ('FULFILLED', 'IN_PROGRESS', 'BROKEN', 'ABANDONED')
                      AND EXISTS (
                        SELECT 1
                        FROM source_archive_attestations selected_programme_archive
                        WHERE selected_programme_archive.source_document_id =
                              selected_programme_source.id
                          AND selected_programme_archive.content_sha256 =
                              selected_programme_source.content_sha256
                          AND selected_programme_archive.retrieval_url =
                              selected_programme_source.url
                      )
                      AND EXISTS (
                        SELECT 1
                        FROM promise_evidence selected_proof
                        JOIN source_documents selected_evidence_source
                          ON selected_evidence_source.id = selected_proof.source_document_id
                        JOIN source_archive_attestations selected_evidence_archive
                          ON selected_evidence_archive.source_document_id =
                             selected_evidence_source.id
                        WHERE selected_proof.promise_id = p.id
                          AND selected_evidence_archive.content_sha256 =
                              selected_evidence_source.content_sha256
                          AND selected_evidence_archive.retrieval_url =
                              selected_evidence_source.url
                      )
                    ORDER BY p.area, p.title, p.id
                    LIMIT $1 OFFSET $2
                )
                SELECT p.id, p.title, p.area, p.status::text AS status, p.progress,
                       p.programme_page, p.rationale, p.reviewed_at,
                       programme_sd.publisher::text AS programme_source_publisher,
                       programme_sd.url AS programme_source_url,
                       programme_sd.retrieved_at AS programme_source_retrieved_at,
                       programme_sd.content_sha256 AS programme_source_sha256,
                       pe.id AS evidence_id, pe.explanation AS evidence_summary,
                       COALESCE(l.official_identifier, evidence_sd.official_identifier,
                                'Documento oficial') AS legal_reference,
                       COALESCE(l.published_at, evidence_sd.published_at) AS evidence_published_at,
                       evidence_sd.publisher::text AS evidence_source_publisher,
                       evidence_sd.url AS evidence_source_url,
                       evidence_sd.retrieved_at AS evidence_source_retrieved_at,
                       evidence_sd.content_sha256 AS evidence_source_sha256
                FROM selected p
                JOIN government_programmes gp ON gp.id = p.programme_id
                JOIN source_documents programme_sd ON programme_sd.id = gp.source_document_id
                JOIN promise_evidence pe ON pe.promise_id = p.id
                JOIN source_documents evidence_sd ON evidence_sd.id = pe.source_document_id
                LEFT JOIN laws l ON l.id = pe.law_id
                WHERE EXISTS (
                    SELECT 1
                    FROM source_archive_attestations programme_archive
                    WHERE programme_archive.source_document_id = programme_sd.id
                      AND programme_archive.content_sha256 = programme_sd.content_sha256
                      AND programme_archive.retrieval_url = programme_sd.url
                )
                  AND EXISTS (
                    SELECT 1
                    FROM source_archive_attestations evidence_archive
                    WHERE evidence_archive.source_document_id = evidence_sd.id
                      AND evidence_archive.content_sha256 = evidence_sd.content_sha256
                      AND evidence_archive.retrieval_url = evidence_sd.url
                  )
                ORDER BY p.area, p.title, pe.created_at, pe.id
                """,
                limit,
                offset,
            )
        promises: dict[str, dict[str, Any]] = {}
        for row in rows:
            promise = promises.setdefault(
                row["id"],
                {
                    "id": row["id"],
                    "title": row["title"],
                    "area": row["area"],
                    "status": row["status"],
                    "progress": row["progress"],
                    "programme_page": row["programme_page"] or "Página não indicada",
                    "programme_source": _source_from_row(row, "programme_source_"),
                    "rationale": row["rationale"]
                    or ("Decisão fundamentada no histórico de revisão."),
                    "last_reviewed_at": row["reviewed_at"],
                    "evidence": [],
                },
            )
            promise["evidence"].append(
                {
                    "id": row["evidence_id"],
                    "legal_reference": row["legal_reference"],
                    "summary": row["evidence_summary"],
                    "source": _source_from_row(row, "evidence_source_"),
                    "published_at": row["evidence_published_at"],
                }
            )
        return list(promises.values())

    async def get_public_investigator_dataset(self, *, limit: int) -> dict[str, Any]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            relationship_rows = await connection.fetch(
                """
                SELECT r.id, r.type::text AS relationship_type, r.public_description,
                       r.valid_from, r.valid_until, r.from_entity_id, r.to_entity_id,
                       f.public_label AS from_label, f.kind::text AS from_kind,
                       t.public_label AS to_label, t.kind::text AS to_kind,
                       CASE WHEN contract_proof.attested
                                  AND pc.publication_status = 'PUBLISHED'
                                  AND pc.verification_status = 'VERIFIED'
                            THEN pc.contract_value END AS contract_value,
                       CASE WHEN contract_proof.attested
                                  AND pc.publication_status = 'PUBLISHED'
                                  AND pc.verification_status = 'VERIFIED'
                            THEN pc.published_at END AS contract_published_at,
                       CASE WHEN f.kind = 'PARTY' THEN f.public_label
                            WHEN t.kind = 'PARTY' THEN t.public_label END AS party_label,
                       CASE WHEN f.kind IN ('COMPANY', 'NON_PROFIT') THEN f.public_label
                            WHEN t.kind IN ('COMPANY', 'NON_PROFIT') THEN t.public_label
                       END AS company_label,
                       sd.publisher::text AS source_publisher,
                       sd.url AS source_url, sd.retrieved_at AS source_retrieved_at,
                       sd.content_sha256 AS source_sha256
                FROM interest_relationships r
                JOIN interest_entities f ON f.id = r.from_entity_id
                JOIN interest_entities t ON t.id = r.to_entity_id
                JOIN source_documents sd ON sd.id = r.source_document_id
                LEFT JOIN public_contracts pc ON pc.id = r.public_contract_id
                LEFT JOIN source_documents contract_sd ON contract_sd.id = pc.source_document_id
                LEFT JOIN LATERAL (
                    SELECT TRUE AS attested
                    FROM source_archive_attestations contract_archive
                    WHERE contract_archive.source_document_id = contract_sd.id
                      AND contract_archive.content_sha256 = contract_sd.content_sha256
                      AND contract_archive.retrieval_url = contract_sd.url
                    LIMIT 1
                ) contract_proof ON TRUE
                WHERE r.publication_status = 'PUBLISHED'
                  AND r.verification_status = 'VERIFIED'
                  AND f.publication_status = 'PUBLISHED'
                  AND f.verification_status = 'VERIFIED'
                  AND t.publication_status = 'PUBLISHED'
                  AND t.verification_status = 'VERIFIED'
                  AND sd.publisher <> 'MEDIA'
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations relationship_archive
                      WHERE relationship_archive.source_document_id = sd.id
                        AND relationship_archive.content_sha256 = sd.content_sha256
                        AND relationship_archive.retrieval_url = sd.url
                  )
                ORDER BY COALESCE(r.valid_from, r.reviewed_at) DESC NULLS LAST, r.id
                LIMIT $1
                """,
                limit,
            )
            comparison_rows = await connection.fetch(
                """
                SELECT c.id, c.outcome::text, c.rationale, c.methodology_version,
                       ps.title AS statement_title, ps.statement_text, ps.stated_at,
                       COALESCE(p.parliamentary_name, p.full_name) AS speaker,
                       statement_sd.publisher::text AS statement_source_publisher,
                       statement_sd.url AS statement_source_url,
                       statement_sd.retrieved_at AS statement_source_retrieved_at,
                       statement_sd.content_sha256 AS statement_source_sha256,
                       ve.title AS vote_title, ve.voted_at, ve.initiative_number,
                       vr.choice::text AS vote_choice,
                       vote_sd.publisher::text AS vote_source_publisher,
                       vote_sd.url AS vote_source_url,
                       vote_sd.retrieved_at AS vote_source_retrieved_at,
                       vote_sd.content_sha256 AS vote_source_sha256,
                       snapshot.score, snapshot.comparable_count,
                       (
                         SELECT COUNT(*)
                         FROM public_statements all_ps
                         JOIN source_documents all_statement_sd
                           ON all_statement_sd.id = all_ps.source_document_id
                         WHERE all_ps.person_id = p.id
                           AND EXISTS (
                             SELECT 1
                             FROM source_archive_attestations all_statement_archive
                             WHERE all_statement_archive.source_document_id = all_statement_sd.id
                               AND all_statement_archive.content_sha256 =
                                   all_statement_sd.content_sha256
                               AND all_statement_archive.retrieval_url = all_statement_sd.url
                           )
                       ) AS total_statements
                FROM statement_vote_comparisons c
                JOIN public_statements ps ON ps.id = c.statement_id
                JOIN people p ON p.id = ps.person_id
                JOIN source_documents statement_sd ON statement_sd.id = ps.source_document_id
                JOIN source_documents comparison_sd ON comparison_sd.id = c.source_document_id
                JOIN vote_events ve ON ve.id = c.vote_event_id
                JOIN vote_records vr ON vr.vote_event_id = ve.id
                  AND vr.person_id = ps.person_id AND vr.actor_type = 'PERSON'
                  AND vr.source_document_id = ve.source_document_id
                JOIN source_documents vote_sd ON vote_sd.id = ve.source_document_id
                JOIN LATERAL (
                    SELECT review.publishable
                    FROM data_publication_reviews review
                    WHERE review.entity_type = 'PARLIAMENT_VOTES_SNAPSHOT'
                      AND review.entity_id = ve.source_document_id
                      AND review.source_document_id = ve.source_document_id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) latest_snapshot_review ON latest_snapshot_review.publishable = TRUE
                LEFT JOIN LATERAL (
                    SELECT cs.score, cs.comparable_count
                    FROM coherence_snapshots cs
                    WHERE cs.person_id = p.id
                    ORDER BY cs.period_ends_at DESC, cs.computed_at DESC LIMIT 1
                ) snapshot ON TRUE
                WHERE c.publication_status = 'PUBLISHED'
                  AND c.verification_status = 'VERIFIED'
                  AND c.comparable = TRUE
                  AND c.outcome IN ('CONSISTENT', 'INCONSISTENT', 'INCONCLUSIVE')
                  AND vr.choice IN ('FAVOR', 'AGAINST', 'ABSTENTION', 'ABSENT')
                  AND ve.is_nominal = TRUE
                  AND vote_sd.publisher = 'PARLIAMENT'
                  AND statement_sd.publisher <> 'MEDIA'
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations comparison_archive
                      WHERE comparison_archive.source_document_id = comparison_sd.id
                        AND comparison_archive.content_sha256 = comparison_sd.content_sha256
                        AND comparison_archive.retrieval_url = comparison_sd.url
                  )
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations vote_archive
                      WHERE vote_archive.source_document_id = vote_sd.id
                        AND vote_archive.content_sha256 = vote_sd.content_sha256
                        AND vote_archive.retrieval_url = vote_sd.url
                  )
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations statement_archive
                      WHERE statement_archive.source_document_id = statement_sd.id
                        AND statement_archive.content_sha256 = statement_sd.content_sha256
                        AND statement_archive.retrieval_url = statement_sd.url
                  )
                ORDER BY c.reviewed_at DESC, c.id
                LIMIT 20
                """
            )

        kind_map = {
            "PERSON": ("person", "Pessoa titular de cargo público"),
            "PARTY": ("party", "Partido político"),
            "PUBLIC_BODY": ("public", "Entidade pública"),
            "COMPANY": ("company", "Sociedade ou empresa"),
            "NON_PROFIT": ("company", "Organização sem fins lucrativos"),
            "EUROPEAN_BODY": ("public", "Entidade europeia"),
        }
        relationship_labels = {
            "PUBLIC_OFFICE": "Cargo público",
            "BOARD_MEMBERSHIP": "Órgão social",
            "OWNERSHIP": "Participação declarada",
            "PARTY_MEMBERSHIP": "Filiação partidária",
            "CAMPAIGN_DONATION": "Donativo de campanha",
            "FAMILY_RELATION": "Relação familiar declarada",
            "OFFICIAL_MEETING": "Reunião oficial",
            "PUBLIC_CONTRACT": "Contrato público",
            "OTHER_OFFICIAL": "Outra relação oficial",
        }
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        for row in relationship_rows:
            for side in ("from", "to"):
                raw_kind = row[f"{side}_kind"]
                kind, subtitle = kind_map.get(raw_kind, ("other", "Entidade documentada"))
                entity_id = row[f"{side}_entity_id"]
                nodes[entity_id] = {
                    "id": entity_id,
                    "label": row[f"{side}_label"],
                    "subtitle": subtitle,
                    "kind": kind,
                    "verified": True,
                }
            valid_from = row["valid_from"]
            valid_until = row["valid_until"]
            if valid_from and valid_until:
                period = f"{valid_from.year}–{valid_until.year}"
            elif valid_from:
                period = f"Desde {valid_from.year}"
            elif valid_until:
                period = f"Até {valid_until.year}"
            else:
                period = "Período não indicado na fonte"
            event_date = row["contract_published_at"] or valid_from
            edges.append(
                {
                    "id": row["id"],
                    "source_id": row["from_entity_id"],
                    "target_id": row["to_entity_id"],
                    "label": relationship_labels.get(
                        row["relationship_type"], row["public_description"]
                    ),
                    "period": period,
                    "source": _source_from_row(row),
                    "year": event_date.year if event_date else None,
                    "party": row["party_label"],
                    "amount": row["contract_value"],
                    "company": row["company_label"],
                }
            )

        comparisons = [
            {
                "id": row["id"],
                "subject": row["vote_title"] or row["statement_title"],
                "statement": {
                    "quote": row["statement_text"],
                    "speaker": row["speaker"],
                    "stated_at": row["stated_at"],
                    "source": _source_from_row(row, "statement_source_"),
                },
                "vote": {
                    "choice": row["vote_choice"],
                    "initiative": row["initiative_number"] or row["vote_title"],
                    "voted_at": row["voted_at"],
                    "source": _source_from_row(row, "vote_source_"),
                },
                "comparison": {
                    "outcome": row["outcome"],
                    "score": row["score"],
                    "comparable_pairs": row["comparable_count"] or 1,
                    "total_statements": max(int(row["total_statements"]), 1),
                    "methodology_version": row["methodology_version"],
                    "rationale": row["rationale"],
                },
            }
            for row in comparison_rows
        ]
        return {"nodes": list(nodes.values()), "edges": edges, "comparisons": comparisons}

    async def _start_sync_run(
        self,
        *,
        source_name: str,
        dataset_url: str,
        code_version: str,
    ) -> str:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        sync_id = _new_id("sync")
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO sync_runs
                    (id, source_name, dataset_url, status, started_at,
                     records_read, records_written, code_version)
                VALUES ($1, $2, $3, 'RUNNING', NOW(), 0, 0, $4)
                """,
                sync_id,
                source_name,
                dataset_url,
                code_version,
            )
        return sync_id

    async def _finish_sync_run(
        self,
        sync_id: str,
        *,
        status_value: str,
        records_read: int,
        records_written: int,
        warnings: list[str],
        error_message: str | None = None,
    ) -> None:
        if self.pool is None:
            return
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE sync_runs SET status = $2::"SyncStatus", finished_at = NOW(),
                    records_read = $3, records_written = $4, warnings = $5::jsonb,
                    error_message = $6
                WHERE id = $1
                """,
                sync_id,
                status_value,
                records_read,
                records_written,
                json.dumps(warnings, ensure_ascii=False),
                error_message[:2_000] if error_message else None,
            )

    @staticmethod
    async def _ensure_source_document(
        connection: asyncpg.Connection,
        *,
        publisher: str,
        kind: str,
        title: str,
        url: str,
        retrieved_at: datetime,
        content_sha256: str,
        mime_type: str | None,
        parser_version: str,
    ) -> str:
        row = await connection.fetchrow(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, url, retrieved_at, content_sha256,
                 mime_type, parser_version, created_at)
            VALUES ($1, $2::"SourcePublisher", $3::"DocumentKind", $4, $5, $6,
                    $7, $8, $9, NOW())
            ON CONFLICT (url, content_sha256) DO NOTHING
            RETURNING id
            """,
            _new_id("source"),
            publisher,
            kind,
            title,
            url,
            _database_timestamp(retrieved_at),
            content_sha256,
            mime_type,
            parser_version,
        )
        if row is None:
            # Uma segunda instrução recebe um novo snapshot READ COMMITTED. Assim,
            # também encontra a linha quando outra transação ganhou a corrida do
            # índice único imediatamente antes do ``ON CONFLICT``.
            row = await connection.fetchrow(
                """
                SELECT id
                FROM source_documents
                WHERE url = $1 AND content_sha256 = $2
                """,
                url,
                content_sha256,
            )
        if row is None:
            raise RuntimeError("Não foi possível garantir o SourceDocument imutável")
        return str(row["id"])

    @staticmethod
    async def _attest_source_archive(
        connection: asyncpg.Connection,
        *,
        source_document_id: str,
        receipt: RawArchiveReceipt,
        archived_by: str,
    ) -> dict[str, Any]:
        actor_alias = archived_by.strip()
        if not actor_alias or len(actor_alias) > 200:
            raise ValueError("O pseudónimo do processo de arquivo é inválido")
        source_url = require_official_url(str(receipt.source_url))
        source = await connection.fetchrow(
            """
            SELECT id, url, content_sha256
            FROM source_documents
            WHERE id = $1
            FOR UPDATE
            """,
            source_document_id,
        )
        if source is None:
            raise LookupError("SourceDocument não encontrado para atestação")
        if str(source["url"]) != source_url:
            raise ValueError("O URL recolhido não corresponde ao SourceDocument")
        if str(source["content_sha256"]) != receipt.content_sha256:
            raise ValueError("O SHA-256 arquivado não corresponde ao SourceDocument")

        retrieved_at = _millisecond_utc(receipt.retrieved_at)
        archived_at = _millisecond_utc(receipt.recorded_at)
        attestation_sha256 = _archive_attestation_sha256(
            source_document_id=source_document_id,
            receipt=receipt,
            archived_at=archived_at,
            archived_by=actor_alias,
        )
        attestation_id = _new_id("source_archive")
        inserted = await connection.fetchrow(
            """
            INSERT INTO source_archive_attestations
                (id, source_document_id, storage_backend, storage_key,
                 content_sha256, byte_size, mime_type, retrieval_url,
                 retrieved_at, archived_at, archived_by, attestation_sha256,
                 created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
            ON CONFLICT (source_document_id, storage_backend, storage_key) DO NOTHING
            RETURNING id, source_document_id, storage_backend, storage_key,
                      content_sha256, byte_size, mime_type, retrieval_url,
                      retrieved_at, archived_at, archived_by, attestation_sha256
            """,
            attestation_id,
            source_document_id,
            receipt.storage_backend,
            receipt.storage_key,
            receipt.content_sha256,
            receipt.byte_size,
            receipt.mime_type,
            source_url,
            _database_timestamp(retrieved_at),
            _database_timestamp(archived_at),
            actor_alias,
            attestation_sha256,
        )
        created = inserted is not None
        attestation = inserted
        if attestation is None:
            attestation = await connection.fetchrow(
                """
                SELECT id, source_document_id, storage_backend, storage_key,
                       content_sha256, byte_size, mime_type, retrieval_url,
                       retrieved_at, archived_at, archived_by, attestation_sha256
                FROM source_archive_attestations
                WHERE source_document_id = $1
                  AND storage_backend = $2
                  AND storage_key = $3
                """,
                source_document_id,
                receipt.storage_backend,
                receipt.storage_key,
            )
        if attestation is None:
            raise RuntimeError("A atestação de arquivo não foi criada nem encontrada")

        expected_existing = {
            "source_document_id": source_document_id,
            "storage_backend": receipt.storage_backend,
            "storage_key": receipt.storage_key,
            "content_sha256": receipt.content_sha256,
            "byte_size": receipt.byte_size,
            "mime_type": receipt.mime_type,
            "retrieval_url": source_url,
        }
        observed_existing = {
            key: int(attestation[key]) if key == "byte_size" else attestation[key]
            for key in expected_existing
        }
        if observed_existing != expected_existing:
            raise ValueError("A atestação existente diverge do recibo content-addressed")

        if created:
            after_json = {
                **expected_existing,
                "retrieved_at": retrieved_at.isoformat(),
                "archived_at": archived_at.isoformat(),
                "archived_by": actor_alias,
                "attestation_sha256": attestation_sha256,
            }
            await connection.execute(
                """
                INSERT INTO audit_events
                    (id, entity_type, entity_id, action, actor_alias,
                     before_json, after_json, reason, created_at)
                VALUES ($1, 'SOURCE_ARCHIVE_ATTESTATION', $2,
                        'ARCHIVED_OFFICIAL_BYTES', $3, NULL, $4::jsonb,
                        'Original oficial conservado em arquivo privado content-addressed', NOW())
                """,
                _new_id("audit"),
                str(attestation["id"]),
                actor_alias,
                json.dumps(after_json, ensure_ascii=False, default=str),
            )

        return {
            "id": str(attestation["id"]),
            **expected_existing,
            "retrieved_at": attestation["retrieved_at"],
            "archived_at": attestation["archived_at"],
            "archived_by": str(attestation["archived_by"]),
            "attestation_sha256": str(attestation["attestation_sha256"]),
            "created": created,
        }

    async def get_source_document_for_archival(
        self,
        *,
        source_document_id: str,
    ) -> dict[str, Any]:
        """Obtém apenas a proveniência necessária para uma recolha de arquivo."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, publisher, kind, title, url, retrieved_at,
                       content_sha256, mime_type, parser_version
                FROM source_documents
                WHERE id = $1
                """,
                source_document_id,
            )
        if row is None:
            raise LookupError("SourceDocument não encontrado")
        source_url = require_official_url(str(row["url"]))
        return {
            "id": str(row["id"]),
            "publisher": str(row["publisher"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "url": source_url,
            "retrieved_at": row["retrieved_at"],
            "content_sha256": str(row["content_sha256"]),
            "mime_type": row["mime_type"],
            "parser_version": row["parser_version"],
        }

    async def attest_source_archive(
        self,
        *,
        source_document_id: str,
        receipt: RawArchiveReceipt,
        archived_by: str,
    ) -> dict[str, Any]:
        """Acrescenta uma atestação e AuditEvent; nunca altera a fonte original."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection, connection.transaction():
            return await self._attest_source_archive(
                connection,
                source_document_id=source_document_id,
                receipt=receipt,
                archived_by=archived_by,
            )

    async def inspect_source_archive_attestation(
        self,
        *,
        source_document_id: str,
    ) -> dict[str, Any]:
        """Inspeciona a atestação mais recente sem criar arquivo, revisão ou evento."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT source.id AS source_document_id,
                       source.publisher, source.kind, source.title, source.url,
                       source.retrieved_at AS source_retrieved_at,
                       source.content_sha256 AS source_sha256,
                       source.mime_type AS source_mime_type,
                       archive.id AS archive_attestation_id,
                       archive.storage_backend, archive.storage_key,
                       archive.content_sha256 AS archive_sha256,
                       archive.byte_size, archive.mime_type AS archive_mime_type,
                       archive.retrieval_url, archive.retrieved_at,
                       archive.archived_at, archive.archived_by,
                       archive.attestation_sha256
                FROM source_documents AS source
                LEFT JOIN LATERAL (
                    SELECT candidate.*
                    FROM source_archive_attestations AS candidate
                    WHERE candidate.source_document_id = source.id
                    ORDER BY candidate.archived_at DESC, candidate.id DESC
                    LIMIT 1
                ) AS archive ON TRUE
                WHERE source.id = $1
                """,
                source_document_id,
            )
        if row is None:
            raise LookupError("SourceDocument não encontrado")

        source_url = require_official_url(str(row["url"]))
        source_sha256 = str(row["source_sha256"])
        archive_present = row["archive_attestation_id"] is not None
        expected_storage_key = f"sha256/{source_sha256[:2]}/{source_sha256}"
        archive_hash_matches = archive_present and str(row["archive_sha256"]) == source_sha256
        archive_url_matches = archive_present and str(row["retrieval_url"]) == source_url
        archive_key_matches = archive_present and str(row["storage_key"]) == expected_storage_key
        attestation_hash_matches = False
        if archive_present:
            retrieved_at = _utc_database_timestamp(row["retrieved_at"])
            archived_at = _utc_database_timestamp(row["archived_at"])
            receipt = RawArchiveReceipt(
                storage_backend=str(row["storage_backend"]),
                storage_key=str(row["storage_key"]),
                content_sha256=str(row["archive_sha256"]),
                byte_size=int(row["byte_size"]),
                mime_type=row["archive_mime_type"],
                source_url=HttpUrl(source_url),
                retrieved_at=retrieved_at,
                recorded_at=archived_at,
                object_created=False,
            )
            expected_attestation_sha256 = _archive_attestation_sha256(
                source_document_id=source_document_id,
                receipt=receipt,
                archived_at=_millisecond_utc(archived_at),
                archived_by=str(row["archived_by"]),
            )
            attestation_hash_matches = expected_attestation_sha256 == str(row["attestation_sha256"])

        return {
            "publication_eligible": False,
            "publication_rule": (
                "A inspeção do arquivo é privada e de leitura; uma atestação não constitui "
                "revisão humana nem autorização de publicação."
            ),
            "source": {
                "id": source_document_id,
                "publisher": str(row["publisher"]),
                "kind": str(row["kind"]),
                "title": str(row["title"]),
                "url": source_url,
                "retrieved_at": row["source_retrieved_at"],
                "content_sha256": source_sha256,
                "mime_type": row["source_mime_type"],
            },
            "archive": (
                {
                    "id": str(row["archive_attestation_id"]),
                    "storage_backend": str(row["storage_backend"]),
                    "storage_key": str(row["storage_key"]),
                    "content_sha256": str(row["archive_sha256"]),
                    "byte_size": int(row["byte_size"]),
                    "mime_type": row["archive_mime_type"],
                    "retrieval_url": str(row["retrieval_url"]),
                    "retrieved_at": row["retrieved_at"],
                    "archived_at": row["archived_at"],
                    "archived_by": str(row["archived_by"]),
                    "attestation_sha256": str(row["attestation_sha256"]),
                }
                if archive_present
                else None
            ),
            "availability": "VERIFICATION_PENDING" if archive_present else "UNAVAILABLE",
            "checks": {
                "official_source_url": bool(source_url),
                "valid_source_sha256": bool(re.fullmatch(r"[0-9a-f]{64}", source_sha256)),
                "archive_attested": archive_present,
                "archive_hash_matches_source": archive_hash_matches,
                "archive_url_matches_source": archive_url_matches,
                "archive_key_matches_source_hash": archive_key_matches,
                "attestation_hash_valid": attestation_hash_matches,
            },
        }

    @staticmethod
    async def _deactivate_stale_parliament_people(
        connection: asyncpg.Connection,
        *,
        legislature: str,
        incoming_source_ids: list[str],
    ) -> int:
        """Desativa pessoas ausentes do snapshot autoritativo sem apagar o histórico."""

        count = await connection.fetchval(
            """
            WITH stale_people AS (
                UPDATE people AS person
                SET active = FALSE, updated_at = NOW()
                WHERE person.role = 'DEPUTY'
                  AND person.active = TRUE
                  AND (
                    person.source_id IS NULL
                    OR person.source_id <> ALL($2::text[])
                  )
                  AND EXISTS (
                    SELECT 1
                    FROM parliamentary_membership_snapshots AS snapshot
                    JOIN source_documents AS source
                      ON source.id = snapshot.source_document_id
                    WHERE snapshot.person_id = person.id
                      AND snapshot.legislature = $1
                      AND source.publisher = 'PARLIAMENT'
                  )
                RETURNING person.id
            )
            SELECT COUNT(*) FROM stale_people
            """,
            legislature,
            incoming_source_ids,
        )
        return int(count or 0)

    @staticmethod
    async def _ensure_initial_parliament_vote_snapshot(
        connection: asyncpg.Connection,
    ) -> None:
        """Impede reingestão destrutiva enquanto não existirem versões append-only."""

        await connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            "parliament-votes-initial-snapshot",
        )
        snapshot_exists = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM vote_events
            )
            """
        )
        if snapshot_exists:
            raise ValueError(
                "A reingestão de votações parlamentares está bloqueada: "
                "já existem eventos em staging e qualquer nova fotografia exige "
                "versionamento append-only."
            )

    async def store_parliament_dataset(
        self,
        dataset: ParliamentDataset,
        *,
        kind: str,
        code_version: str,
        archive_receipt: RawArchiveReceipt | None = None,
    ) -> dict[str, int]:
        if kind not in {"deputies", "votes"}:
            raise ValueError("Tipo de dataset parlamentar desconhecido")
        if archive_receipt is None:
            raise ValueError("A persistência parlamentar exige arquivo prévio dos bytes oficiais")
        if archive_receipt.content_sha256 != dataset.document_sha256:
            raise ValueError("O recibo de arquivo não corresponde ao hash do dataset")
        if str(archive_receipt.source_url) != str(dataset.dataset_url):
            raise ValueError("O recibo de arquivo não corresponde ao URL efetivo do dataset")
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        source_name = f"PARLIAMENT_{kind.upper()}"
        records_read = len(dataset.deputies) if kind == "deputies" else len(dataset.votes)
        sync_id = await self._start_sync_run(
            source_name=source_name,
            dataset_url=str(dataset.dataset_url),
            code_version=code_version,
        )
        written = 0
        deactivated = 0
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                if kind == "votes":
                    await self._ensure_initial_parliament_vote_snapshot(connection)
                source_document_id = await self._ensure_source_document(
                    connection,
                    publisher="PARLIAMENT",
                    kind="OPEN_DATASET",
                    title=f"Assembleia da República — {kind} — {dataset.legislature}",
                    url=str(dataset.dataset_url),
                    retrieved_at=dataset.collected_at,
                    content_sha256=dataset.document_sha256,
                    mime_type=archive_receipt.mime_type,
                    parser_version=code_version,
                )
                archive_attestation = await self._attest_source_archive(
                    connection,
                    source_document_id=source_document_id,
                    receipt=archive_receipt,
                    archived_by=f"sync:{code_version}",
                )
                if kind == "deputies":
                    deactivated = await self._deactivate_stale_parliament_people(
                        connection,
                        legislature=dataset.legislature,
                        incoming_source_ids=[item.source_id for item in dataset.deputies],
                    )
                    for deputy in dataset.deputies:
                        party_id: str | None = None
                        if deputy.party_short:
                            party_row = await connection.fetchrow(
                                """
                                INSERT INTO parties
                                    (id, source_id, name, short_name, official_url,
                                     created_at, updated_at)
                                VALUES ($1, $2, $3, $3, $4, NOW(), NOW())
                                ON CONFLICT (source_id) DO UPDATE SET
                                    short_name = EXCLUDED.short_name, updated_at = NOW()
                                RETURNING id
                                """,
                                _new_id("party"),
                                f"ar-party:{deputy.party_short}",
                                deputy.party_short,
                                str(dataset.dataset_url),
                            )
                            party_id = str(party_row["id"])
                        person_row = await connection.fetchrow(
                            """
                            INSERT INTO people
                                (id, source_id, full_name, parliamentary_name, slug,
                                 role, active, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5, 'DEPUTY', TRUE, NOW(), NOW())
                            ON CONFLICT (source_id) DO UPDATE SET
                                full_name = EXCLUDED.full_name,
                                parliamentary_name = EXCLUDED.parliamentary_name,
                                active = TRUE, updated_at = NOW()
                            RETURNING id
                            """,
                            _new_id("person"),
                            deputy.source_id,
                            deputy.full_name or deputy.parliamentary_name,
                            deputy.parliamentary_name,
                            _slug(deputy.parliamentary_name, deputy.source_id),
                        )
                        await connection.execute(
                            """
                            INSERT INTO parliamentary_membership_snapshots
                                (id, person_id, party_id, legislature, constituency,
                                 observed_at, source_document_id)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (person_id, legislature, source_document_id) DO UPDATE SET
                                party_id = EXCLUDED.party_id,
                                constituency = EXCLUDED.constituency,
                                observed_at = EXCLUDED.observed_at
                            """,
                            _new_id("membership"),
                            person_row["id"],
                            party_id,
                            dataset.legislature,
                            deputy.constituency,
                            _database_timestamp(dataset.collected_at),
                            source_document_id,
                        )
                        written += 1
                else:
                    for event in dataset.votes:
                        event_row = await connection.fetchrow(
                            """
                            INSERT INTO vote_events
                                (id, source_id, title, initiative_number, voted_at, result,
                                 is_nominal, source_document_id, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                            RETURNING id
                            """,
                            _new_id("vote_event"),
                            event.source_id,
                            event.title,
                            event.initiative_number,
                            _database_timestamp(event.voted_at),
                            event.result,
                            event.is_nominal,
                            source_document_id,
                        )
                        for record in event.records:
                            person_id: str | None = None
                            if record.actor_source_id:
                                person_id = await connection.fetchval(
                                    "SELECT id FROM people WHERE source_id = $1",
                                    record.actor_source_id,
                                )
                            actor_type = "PERSON" if person_id else "UNKNOWN"
                            await connection.execute(
                                """
                                INSERT INTO vote_records
                                    (id, vote_event_id, actor_type, actor_label, person_id,
                                     party_id, choice, source_document_id)
                                VALUES ($1, $2, $3::"VoteActorType", $4, $5, NULL,
                                        $6::"VoteChoice", $7)
                                """,
                                _new_id("vote_record"),
                                event_row["id"],
                                actor_type,
                                record.actor_label,
                                person_id,
                                record.choice.value,
                                source_document_id,
                            )
                            written += 1
                        written += 1
            await self._finish_sync_run(
                sync_id,
                status_value="PARTIAL" if dataset.warnings else "SUCCEEDED",
                records_read=records_read,
                records_written=written,
                warnings=dataset.warnings,
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=records_read,
                records_written=0,
                warnings=dataset.warnings,
                error_message=str(exc),
            )
            raise
        return {
            "records_read": records_read,
            "records_written": written,
            "records_deactivated": deactivated,
            "archive_attestations_written": int(archive_attestation["created"]),
        }

    async def inspect_parliament_votes_staging(
        self,
        *,
        legislature: str,
    ) -> dict[str, Any]:
        """Inspeciona a última fotografia de votos apenas com leituras de staging."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")

        source_title = f"Assembleia da República — votes — {legislature}"
        async with self.pool.acquire() as connection:
            snapshot = await connection.fetchrow(
                """
                SELECT run.id AS sync_run_id, run.dataset_url,
                       run.status::text AS sync_status, run.started_at,
                       run.finished_at, run.records_read, run.records_written,
                       run.warnings, run.error_message, run.code_version,
                       source.id AS source_document_id,
                       source.publisher::text AS source_publisher,
                       source.kind::text AS source_kind, source.title AS source_title,
                       source.url AS source_url, source.retrieved_at,
                       source.content_sha256, source.mime_type,
                       source.raw_storage_key, source.parser_version,
                       MAX(archive.id) AS archive_attestation_id,
                       MAX(archive.storage_backend) AS archive_storage_backend,
                       MAX(archive.storage_key) AS archive_storage_key,
                       MAX(archive.content_sha256) AS archive_content_sha256,
                       MAX(archive.byte_size) AS archive_byte_size,
                       MAX(archive.mime_type) AS archive_mime_type,
                       MAX(archive.retrieval_url) AS archive_retrieval_url,
                       MAX(archive.retrieved_at) AS archive_retrieved_at,
                       MAX(archive.archived_at) AS archive_archived_at,
                       MAX(archive.archived_by) AS archive_archived_by,
                       MAX(archive.attestation_sha256) AS archive_attestation_sha256,
                       COUNT(DISTINCT event.id) AS event_count,
                       COUNT(record.id) AS position_count,
                       COUNT(DISTINCT event.id) FILTER (
                           WHERE event.is_nominal = TRUE
                       ) AS nominal_event_count,
                       COUNT(DISTINCT event.id) FILTER (
                           WHERE event.voted_at IS NULL
                       ) AS event_without_date_count,
                       COUNT(DISTINCT event.id) FILTER (
                           WHERE record.id IS NULL
                       ) AS event_without_normalised_positions_count,
                       COUNT(record.id) FILTER (
                           WHERE record.choice = 'UNKNOWN'
                       ) AS unknown_choice_count,
                       COUNT(record.id) FILTER (
                           WHERE record.person_id IS NOT NULL
                       ) AS person_link_count,
                       COUNT(record.id) FILTER (
                           WHERE record.party_id IS NOT NULL
                       ) AS party_link_count
                FROM sync_runs run
                JOIN source_documents source ON source.url = run.dataset_url
                LEFT JOIN LATERAL (
                    SELECT candidate.*
                    FROM source_archive_attestations candidate
                    WHERE candidate.source_document_id = source.id
                    ORDER BY candidate.archived_at DESC, candidate.id DESC
                    LIMIT 1
                ) archive ON TRUE
                JOIN vote_events event ON event.source_document_id = source.id
                LEFT JOIN vote_records record
                  ON record.vote_event_id = event.id
                 AND record.source_document_id = source.id
                WHERE run.source_name = 'PARLIAMENT_VOTES'
                  AND run.status IN ('SUCCEEDED', 'PARTIAL')
                  AND run.finished_at IS NOT NULL
                  AND source.publisher = 'PARLIAMENT'
                  AND source.kind = 'OPEN_DATASET'
                  AND source.title = $1
                  AND source.parser_version = run.code_version
                GROUP BY run.id, source.id
                HAVING MIN(event.updated_at) >= run.started_at
                   AND MAX(event.updated_at) <= run.finished_at
                   AND COUNT(DISTINCT event.id) = run.records_read
                   AND COUNT(DISTINCT event.id) + COUNT(record.id) = run.records_written
                ORDER BY run.started_at DESC, run.id DESC,
                         source.retrieved_at DESC, source.id DESC
                LIMIT 1
                """,
                source_title,
            )
            if snapshot is None:
                raise ValueError(
                    f"Não existe fotografia persistida de votações para a legislatura {legislature}"
                )

            source_document_id = str(snapshot["source_document_id"])
            distribution_rows = await connection.fetch(
                """
                SELECT dimension, value, count
                FROM (
                    SELECT 'choice'::text AS dimension, choice::text AS value,
                           COUNT(*)::bigint AS count
                    FROM vote_records
                    WHERE source_document_id = $1
                    GROUP BY choice
                    UNION ALL
                    SELECT 'actor_type'::text AS dimension, actor_type::text AS value,
                           COUNT(*)::bigint AS count
                    FROM vote_records
                    WHERE source_document_id = $1
                    GROUP BY actor_type
                ) distribution
                ORDER BY dimension, value
                """,
                source_document_id,
            )
            events_without_positions = await connection.fetch(
                """
                SELECT event.source_id, event.title, event.voted_at, event.result
                FROM vote_events event
                WHERE event.source_document_id = $1
                  AND NOT EXISTS (
                      SELECT 1
                      FROM vote_records record
                      WHERE record.vote_event_id = event.id
                        AND record.source_document_id = event.source_document_id
                  )
                ORDER BY event.voted_at DESC NULLS LAST, event.source_id
                """,
                source_document_id,
            )

        source_url = require_official_url(str(snapshot["source_url"]))
        source_sha256 = str(snapshot["content_sha256"])
        warnings: Any = snapshot["warnings"]
        if isinstance(warnings, str):
            try:
                warnings = json.loads(warnings)
            except json.JSONDecodeError:
                warnings = [warnings]
        elif warnings is None:
            warnings = []
        elif not isinstance(warnings, list):
            warnings = [warnings]

        choice_counts = {
            "FAVOR": 0,
            "AGAINST": 0,
            "ABSTENTION": 0,
            "ABSENT": 0,
            "PAIRED": 0,
            "UNKNOWN": 0,
        }
        actor_type_counts = {"PERSON": 0, "PARTY": 0, "UNKNOWN": 0}
        for row in distribution_rows:
            target = choice_counts if row["dimension"] == "choice" else actor_type_counts
            target[str(row["value"])] = int(row["count"])

        event_count = int(snapshot["event_count"])
        position_count = int(snapshot["position_count"])
        unavailable_count = int(snapshot["event_without_normalised_positions_count"])
        records_read = int(snapshot["records_read"])
        records_written = int(snapshot["records_written"])
        parser_version = str(snapshot["parser_version"] or "")
        code_version = str(snapshot["code_version"])
        unavailable_events = [dict(row) for row in events_without_positions]
        archive_attested = snapshot["archive_attestation_id"] is not None
        expected_archive_key = f"sha256/{source_sha256[:2]}/{source_sha256}"
        archive_hash_matches = (
            archive_attested and str(snapshot["archive_content_sha256"]) == source_sha256
        )
        archive_url_matches = (
            archive_attested and str(snapshot["archive_retrieval_url"]) == source_url
        )
        archive_key_matches = (
            archive_attested and str(snapshot["archive_storage_key"]) == expected_archive_key
        )

        return {
            "legislature": legislature,
            "publication_eligible": False,
            "publication_rule": (
                "Esta inspeção é privada e exclusivamente de leitura; não cria revisão, "
                "não associa atores e não publica votações."
            ),
            "sync_run": {
                "id": str(snapshot["sync_run_id"]),
                "dataset_url": str(snapshot["dataset_url"]),
                "status": str(snapshot["sync_status"]),
                "started_at": snapshot["started_at"],
                "finished_at": snapshot["finished_at"],
                "records_read": records_read,
                "records_written": records_written,
                "warnings": warnings,
                "error_message": snapshot["error_message"],
                "code_version": code_version,
            },
            "provenance": {
                "source_document_id": source_document_id,
                "publisher": str(snapshot["source_publisher"]),
                "kind": str(snapshot["source_kind"]),
                "title": str(snapshot["source_title"]),
                "url": source_url,
                "retrieved_at": snapshot["retrieved_at"],
                "content_sha256": source_sha256,
                "mime_type": snapshot["mime_type"],
                "raw_storage_key": snapshot["raw_storage_key"],
                "parser_version": parser_version,
                "archive_attestation": (
                    {
                        "id": str(snapshot["archive_attestation_id"]),
                        "storage_backend": str(snapshot["archive_storage_backend"]),
                        "storage_key": str(snapshot["archive_storage_key"]),
                        "content_sha256": str(snapshot["archive_content_sha256"]),
                        "byte_size": int(snapshot["archive_byte_size"]),
                        "mime_type": snapshot["archive_mime_type"],
                        "retrieval_url": str(snapshot["archive_retrieval_url"]),
                        "retrieved_at": snapshot["archive_retrieved_at"],
                        "archived_at": snapshot["archive_archived_at"],
                        "archived_by": str(snapshot["archive_archived_by"]),
                        "attestation_sha256": str(snapshot["archive_attestation_sha256"]),
                    }
                    if archive_attested
                    else None
                ),
            },
            "counts": {
                "events": event_count,
                "positions": position_count,
                "nominal_events": int(snapshot["nominal_event_count"]),
                "events_without_date": int(snapshot["event_without_date_count"]),
                "events_without_normalised_positions": unavailable_count,
                "unknown_choices": int(snapshot["unknown_choice_count"]),
                "person_links": int(snapshot["person_link_count"]),
                "party_links": int(snapshot["party_link_count"]),
            },
            "distributions": {
                "choices": choice_counts,
                "actor_types": actor_type_counts,
            },
            "normalised_position_availability": {
                "status": "UNAVAILABLE_FOR_LISTED_EVENTS",
                "event_count": unavailable_count,
                "description": (
                    "Não existem posições normalizadas para estes eventos; é necessário "
                    "confirmar no documento oficial se o detalhe está ausente ou se o parser "
                    "não o reconheceu."
                ),
                "events": unavailable_events,
            },
            "checks": {
                "official_source_url": bool(source_url),
                "valid_source_sha256": bool(re.fullmatch(r"[0-9a-f]{64}", source_sha256)),
                "sync_finished": snapshot["finished_at"] is not None,
                "sync_status_allows_inspection": snapshot["sync_status"]
                in {"SUCCEEDED", "PARTIAL"},
                "event_count_matches_records_read": event_count == records_read,
                "written_count_matches_events_and_positions": (
                    event_count + position_count == records_written
                ),
                "choice_distribution_matches_positions": (
                    sum(choice_counts.values()) == position_count
                ),
                "actor_distribution_matches_positions": (
                    sum(actor_type_counts.values()) == position_count
                ),
                "unavailable_list_matches_count": (len(unavailable_events) == unavailable_count),
                "parser_matches_sync_code_version": parser_version == code_version,
                "archive_attested": archive_attested,
                "archive_hash_matches_source": archive_hash_matches,
                "archive_url_matches_source": archive_url_matches,
                "archive_key_matches_source_hash": archive_key_matches,
            },
        }

    async def store_base_collection(
        self,
        collection: BaseContractCollection,
        *,
        code_version: str,
    ) -> dict[str, int]:
        # Fail closed antes de criar SyncRun, adquirir uma ligação ou executar qualquer escrita.
        raise RuntimeError(BASE_PERSISTENCE_DISABLED_MESSAGE)

    async def review_publication(
        self,
        *,
        entity_type: str,
        entity_id: str,
        publish: bool,
        reviewer_alias: str,
        rationale: str,
    ) -> dict[str, Any]:
        """Promove ou retira um registo com decisão humana e rasto append-only."""
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        allowed = {
            "PERSON",
            "PROMISE",
            "PUBLIC_CONTRACT",
            "INTEREST_ENTITY",
            "INTEREST_RELATIONSHIP",
        }
        if entity_type not in allowed:
            raise ValueError("Tipo de entidade não suportado para revisão pública")

        review_source_document_id: str | None = None
        async with self.pool.acquire() as connection, connection.transaction():
            if entity_type == "PERSON":
                current = await connection.fetchrow(
                    """
                    SELECT person.id, person.active, snapshot.source_document_id
                    FROM people person
                    LEFT JOIN LATERAL (
                        SELECT membership.source_document_id
                        FROM parliamentary_membership_snapshots membership
                        WHERE membership.person_id = person.id
                        ORDER BY membership.observed_at DESC, membership.id DESC
                        LIMIT 1
                    ) snapshot ON TRUE
                    WHERE person.id = $1
                    """,
                    entity_id,
                )
                evidence_exists = bool(current and current["source_document_id"])
                if current is not None and current["source_document_id"] is not None:
                    review_source_document_id = str(current["source_document_id"])
                sensitivity = "PUBLIC_PERSONAL"
            elif entity_type == "PROMISE":
                current = await connection.fetchrow(
                    "SELECT id, status::text AS status FROM promises WHERE id = $1",
                    entity_id,
                )
                evidence_exists = await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM promise_evidence WHERE promise_id = $1)",
                    entity_id,
                )
                sensitivity = "PUBLIC_OFFICIAL"
            elif entity_type == "PUBLIC_CONTRACT":
                current = await connection.fetchrow(
                    """
                    SELECT id, verification_status::text AS verification_status,
                           publication_status::text AS publication_status,
                           source_document_id
                    FROM public_contracts WHERE id = $1
                    """,
                    entity_id,
                )
                evidence_exists = current is not None
                if current is not None:
                    review_source_document_id = str(current["source_document_id"])
                sensitivity = "PUBLIC_OFFICIAL"
            elif entity_type == "INTEREST_ENTITY":
                current = await connection.fetchrow(
                    """
                    SELECT id, verification_status::text AS verification_status,
                           publication_status::text AS publication_status
                    FROM interest_entities WHERE id = $1
                    """,
                    entity_id,
                )
                evidence_exists = current is not None
                sensitivity = "PUBLIC_OFFICIAL"
            else:
                current = await connection.fetchrow(
                    """
                    SELECT r.id, r.verification_status::text AS verification_status,
                           r.publication_status::text AS publication_status,
                           f.publication_status::text AS from_publication_status,
                           t.publication_status::text AS to_publication_status,
                           f.verification_status::text AS from_verification_status,
                           t.verification_status::text AS to_verification_status,
                           r.source_document_id
                    FROM interest_relationships r
                    JOIN interest_entities f ON f.id = r.from_entity_id
                    JOIN interest_entities t ON t.id = r.to_entity_id
                    WHERE r.id = $1
                    """,
                    entity_id,
                )
                evidence_exists = bool(
                    current
                    and current["from_publication_status"] == "PUBLISHED"
                    and current["to_publication_status"] == "PUBLISHED"
                    and current["from_verification_status"] == "VERIFIED"
                    and current["to_verification_status"] == "VERIFIED"
                )
                if current is not None:
                    review_source_document_id = str(current["source_document_id"])
                sensitivity = "PUBLIC_OFFICIAL"

            if current is None:
                raise ValueError("Entidade a rever não encontrada")
            if publish and not evidence_exists:
                raise ValueError("A publicação exige prova associada e dependências publicadas")
            if publish and review_source_document_id is not None:
                archive_exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM source_archive_attestations archive
                        JOIN source_documents source
                          ON source.id = archive.source_document_id
                        WHERE source.id = $1
                          AND archive.content_sha256 = source.content_sha256
                          AND archive.retrieval_url = source.url
                    )
                    """,
                    review_source_document_id,
                )
                if not archive_exists:
                    raise ValueError("A publicação exige atestação do original no arquivo privado")

            before = dict(current)
            if entity_type == "PROMISE":
                await connection.execute(
                    """
                    INSERT INTO promise_reviews
                        (id, promise_id, previous_status, proposed_status, decision,
                         reviewer_alias, rationale, reviewed_at)
                    VALUES ($1, $2, $3::"PromiseStatus", $3::"PromiseStatus",
                            $4::"ReviewDecision", $5, $6, NOW())
                    """,
                    _new_id("promise_review"),
                    entity_id,
                    current["status"],
                    "ACCEPT" if publish else "REJECT",
                    reviewer_alias,
                    rationale,
                )
            elif entity_type in {
                "PUBLIC_CONTRACT",
                "INTEREST_ENTITY",
                "INTEREST_RELATIONSHIP",
            }:
                table = {
                    "PUBLIC_CONTRACT": "public_contracts",
                    "INTEREST_ENTITY": "interest_entities",
                    "INTEREST_RELATIONSHIP": "interest_relationships",
                }[entity_type]
                if publish:
                    query = f"""
                        UPDATE {table}
                        SET verification_status = 'VERIFIED', publication_status = 'PUBLISHED',
                            updated_at = NOW()
                        WHERE id = $1
                    """
                else:
                    query = f"""
                        UPDATE {table}
                        SET publication_status = 'WITHDRAWN', updated_at = NOW()
                        WHERE id = $1
                    """
                await connection.execute(query, entity_id)

            decision = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "publishable": publish,
                "reviewer_alias": reviewer_alias,
                "rationale": rationale,
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
            await connection.execute(
                """
                INSERT INTO data_publication_reviews
                    (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                     necessity_assessment, proportionality_test, publishable,
                     source_document_id, reviewed_by, reviewed_at)
                VALUES ($1, $2, $3, $4, 'PUBLIC_INTEREST', $5::"DataSensitivity",
                        $6, $7, $8, $9, $10, NOW())
                """,
                _new_id("publication_review"),
                entity_type,
                entity_id,
                "Informação factual necessária à fiscalização democrática",
                sensitivity,
                "A fonte e a identidade do registo foram verificadas pelo revisor.",
                "A exposição é limitada aos campos públicos necessários e conserva a fonte.",
                publish,
                review_source_document_id,
                reviewer_alias,
            )
            await connection.execute(
                """
                INSERT INTO audit_events
                    (id, entity_type, entity_id, action, actor_alias,
                     before_json, after_json, reason, created_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, NOW())
                """,
                _new_id("audit"),
                entity_type,
                entity_id,
                "PUBLISHED" if publish else "WITHDRAWN",
                reviewer_alias,
                json.dumps(before, default=str, ensure_ascii=False),
                json.dumps(decision, ensure_ascii=False),
                rationale,
            )
        return decision

    @staticmethod
    async def _parliament_people_publication_snapshot(
        connection: asyncpg.Connection,
        *,
        legislature: str,
        lock_people: bool = False,
    ) -> dict[str, Any]:
        """Obtém a última fotografia parlamentar persistida e os seus candidatos."""

        sync_run = await connection.fetchrow(
            """
            SELECT dataset_url, status::text AS status, records_read, records_written,
                   code_version, started_at, finished_at
            FROM sync_runs
            WHERE source_name = 'PARLIAMENT_DEPUTIES'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        )
        if sync_run is None:
            raise ValueError("Não existe sincronização de deputados para rever")
        if sync_run["status"] != "SUCCEEDED":
            raise ValueError("A última sincronização de deputados não terminou com sucesso")

        source = await connection.fetchrow(
            """
            SELECT sd.id, sd.url, sd.content_sha256, sd.retrieved_at,
                   sd.parser_version, MAX(snapshot.observed_at) AS observed_at,
                   COUNT(DISTINCT snapshot.person_id) AS candidate_count,
                   MAX(archive.id) AS archive_attestation_id,
                   MAX(archive.content_sha256) AS archive_content_sha256,
                   MAX(archive.retrieval_url) AS archive_retrieval_url,
                   MAX(archive.storage_key) AS archive_storage_key
            FROM source_documents sd
            LEFT JOIN LATERAL (
                SELECT candidate.*
                FROM source_archive_attestations candidate
                WHERE candidate.source_document_id = sd.id
                ORDER BY candidate.archived_at DESC, candidate.id DESC
                LIMIT 1
            ) archive ON TRUE
            JOIN parliamentary_membership_snapshots snapshot
              ON snapshot.source_document_id = sd.id
            JOIN people person ON person.id = snapshot.person_id
            WHERE sd.publisher = 'PARLIAMENT'
              AND sd.url = $1
              AND snapshot.legislature = $2
              AND person.role = 'DEPUTY'
              AND person.active = TRUE
            GROUP BY sd.id
            ORDER BY observed_at DESC, sd.retrieved_at DESC, sd.id DESC
            LIMIT 1
            """,
            sync_run["dataset_url"],
            legislature,
        )
        if source is None:
            raise ValueError("Documento-fonte da última sincronização não encontrado")
        source_url = require_official_url(str(source["url"]))
        source_sha256 = str(source["content_sha256"])
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
            raise ValueError("O documento-fonte não contém um SHA-256 válido")
        expected_archive_key = f"sha256/{source_sha256[:2]}/{source_sha256}"
        archive_attested = bool(
            source["archive_attestation_id"] is not None
            and str(source["archive_content_sha256"]) == source_sha256
            and str(source["archive_retrieval_url"]) == source_url
            and str(source["archive_storage_key"]) == expected_archive_key
        )

        people_query = """
            SELECT person.id, person.source_id,
                   COALESCE(person.parliamentary_name, person.full_name) AS name,
                   COALESCE(party.short_name, '—') AS party_short,
                   COALESCE(snapshot.constituency, 'Não disponível') AS constituency,
                   latest_review.publishable AS latest_publishable
            FROM parliamentary_membership_snapshots snapshot
            JOIN people person ON person.id = snapshot.person_id
            LEFT JOIN parties party ON party.id = snapshot.party_id
            LEFT JOIN LATERAL (
                SELECT review.publishable
                FROM data_publication_reviews review
                WHERE review.entity_type = 'PERSON'
                  AND review.entity_id = person.id
                  AND review.source_document_id = snapshot.source_document_id
                ORDER BY review.reviewed_at DESC, review.id DESC
                LIMIT 1
            ) latest_review ON TRUE
            WHERE snapshot.source_document_id = $1
              AND snapshot.legislature = $2
              AND person.role = 'DEPUTY'
              AND person.active = TRUE
            ORDER BY name, person.id
        """
        if lock_people:
            people_query += " FOR UPDATE OF person"
        people = await connection.fetch(people_query, source["id"], legislature)

        candidate_count = int(source["candidate_count"])
        if candidate_count != len(people):
            raise ValueError("A fotografia parlamentar contém candidatos duplicados")
        if int(sync_run["records_read"]) != candidate_count:
            raise ValueError(
                "A contagem persistida não coincide com a última sincronização de deputados"
            )
        if int(sync_run["records_written"]) != candidate_count:
            raise ValueError("Nem todos os deputados da última sincronização foram persistidos")
        source_ids = [str(person["source_id"] or "") for person in people]
        if not all(source_ids) or len(set(source_ids)) != len(source_ids):
            raise ValueError("A fotografia contém identificadores ausentes ou duplicados")

        return {
            "legislature": legislature,
            "source_document_id": str(source["id"]),
            "source_url": source_url,
            "source_sha256": source_sha256,
            "source_retrieved_at": source["retrieved_at"],
            "source_observed_at": source["observed_at"],
            "parser_version": str(source["parser_version"]),
            "sync_code_version": str(sync_run["code_version"]),
            "sync_finished_at": sync_run["finished_at"],
            "archive_attested": archive_attested,
            "archive_attestation_id": (
                str(source["archive_attestation_id"])
                if source["archive_attestation_id"] is not None
                else None
            ),
            "publication_eligible": archive_attested,
            "candidate_count": candidate_count,
            "already_published": sum(person["latest_publishable"] is True for person in people),
            "people": [dict(person) for person in people],
        }

    async def inspect_parliament_people_publication(
        self,
        *,
        legislature: str,
    ) -> dict[str, Any]:
        """Pré-visualiza, sem escrever, a fotografia elegível para revisão."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        async with self.pool.acquire() as connection:
            return await self._parliament_people_publication_snapshot(
                connection,
                legislature=legislature,
            )

    async def publish_parliament_people_snapshot(
        self,
        *,
        legislature: str,
        expected_source_sha256: str,
        expected_count: int,
        reviewer_alias: str,
        rationale: str,
    ) -> dict[str, Any]:
        """Publica uma fotografia validada, preservando uma decisão por pessoa."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_source_sha256):
            raise ValueError("O SHA-256 esperado deve conter 64 caracteres hexadecimais")
        if not 100 <= expected_count <= 500:
            raise ValueError("A contagem esperada deve estar entre 100 e 500")
        if len(reviewer_alias.strip()) < 3:
            raise ValueError("O pseudónimo do revisor é demasiado curto")
        if len(rationale.strip()) < 20:
            raise ValueError("A fundamentação deve ter pelo menos 20 caracteres")

        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"parliament-people-publication:{legislature}",
            )
            snapshot = await self._parliament_people_publication_snapshot(
                connection,
                legislature=legislature,
                lock_people=True,
            )
            if snapshot["source_sha256"] != expected_source_sha256:
                raise ValueError("O SHA-256 fornecido não corresponde à fotografia mais recente")
            if snapshot["candidate_count"] != expected_count:
                raise ValueError("A contagem fornecida não corresponde à fotografia mais recente")
            if not snapshot["archive_attested"]:
                raise ValueError("O documento-fonte não tem uma atestação de arquivo válida")

            pending_people = [
                person for person in snapshot["people"] if person["latest_publishable"] is not True
            ]
            review_arguments: list[tuple[object, ...]] = []
            audit_arguments: list[tuple[object, ...]] = []
            for person in pending_people:
                review_arguments.append(
                    (
                        _new_id("publication_review"),
                        person["id"],
                        snapshot["source_document_id"],
                        reviewer_alias.strip(),
                    )
                )
                before = {
                    "active": True,
                    "latest_publishable": person["latest_publishable"],
                }
                after = {
                    "publishable": True,
                    "legislature": legislature,
                    "source_sha256": expected_source_sha256,
                    "batch_expected_count": expected_count,
                }
                audit_arguments.append(
                    (
                        _new_id("audit"),
                        person["id"],
                        reviewer_alias.strip(),
                        json.dumps(before, ensure_ascii=False),
                        json.dumps(after, ensure_ascii=False),
                        rationale.strip(),
                    )
                )

            if review_arguments:
                await connection.executemany(
                    """
                    INSERT INTO data_publication_reviews
                        (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                         necessity_assessment, proportionality_test, publishable,
                         source_document_id, reviewed_by, reviewed_at)
                    VALUES ($1, 'PERSON', $2,
                            'Informação factual necessária à fiscalização democrática',
                            'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                            'A fonte, a identidade e a pertença parlamentar foram verificadas.',
                            'Publica apenas os campos necessários e mantém a fonte oficial.',
                            TRUE, $3, $4, NOW())
                    """,
                    review_arguments,
                )
                await connection.executemany(
                    """
                    INSERT INTO audit_events
                        (id, entity_type, entity_id, action, actor_alias,
                         before_json, after_json, reason, created_at)
                    VALUES ($1, 'PERSON', $2, 'PUBLISHED', $3,
                            $4::jsonb, $5::jsonb, $6, NOW())
                    """,
                    audit_arguments,
                )

        return {
            "legislature": legislature,
            "source_url": snapshot["source_url"],
            "source_sha256": snapshot["source_sha256"],
            "candidate_count": snapshot["candidate_count"],
            "already_published": snapshot["already_published"],
            "published_now": len(pending_people),
            "publication_rule": (
                "Uma decisão e um evento de auditoria foram preservados por pessoa."
            ),
        }

    async def list_open_data(
        self,
        dataset: str,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        queries = {
            "contracts": """
                SELECT c.source_id, c.object, c.procedure::text, c.cpv_code,
                       c.base_value, c.contract_value, c.currency, c.decision_at,
                       c.signed_at, c.published_at, c.execution_days,
                       sd.url AS source_url, sd.content_sha256 AS source_sha256,
                       COALESCE(
                         jsonb_agg(
                           jsonb_build_object('name', p.source_name, 'role', p.role::text)
                           ORDER BY p.role, p.source_name
                         ) FILTER (WHERE p.id IS NOT NULL), '[]'::jsonb
                       ) AS parties
                FROM public_contracts c
                JOIN source_documents sd ON sd.id = c.source_document_id
                LEFT JOIN public_contract_parties p ON p.public_contract_id = c.id
                WHERE c.publication_status = 'PUBLISHED'
                  AND c.verification_status = 'VERIFIED'
                  AND EXISTS (
                    SELECT 1
                    FROM source_archive_attestations contract_archive
                    WHERE contract_archive.source_document_id = sd.id
                      AND contract_archive.content_sha256 = sd.content_sha256
                      AND contract_archive.retrieval_url = sd.url
                  )
                GROUP BY c.id, sd.id
                ORDER BY c.published_at DESC NULLS LAST, c.source_id
                LIMIT $1 OFFSET $2
            """,
            "interest-graph": """
                SELECT r.id, r.type::text, r.public_description,
                       r.valid_from, r.valid_until,
                       f.public_label AS from_label, f.kind::text AS from_kind,
                       t.public_label AS to_label, t.kind::text AS to_kind,
                       sd.url AS source_url, sd.content_sha256 AS source_sha256,
                       r.methodology_version
                FROM interest_relationships r
                JOIN interest_entities f ON f.id = r.from_entity_id
                JOIN interest_entities t ON t.id = r.to_entity_id
                JOIN source_documents sd ON sd.id = r.source_document_id
                WHERE r.publication_status = 'PUBLISHED'
                  AND r.verification_status = 'VERIFIED'
                  AND f.publication_status = 'PUBLISHED'
                  AND t.publication_status = 'PUBLISHED'
                  AND EXISTS (
                    SELECT 1
                    FROM source_archive_attestations relationship_archive
                    WHERE relationship_archive.source_document_id = sd.id
                      AND relationship_archive.content_sha256 = sd.content_sha256
                      AND relationship_archive.retrieval_url = sd.url
                  )
                ORDER BY r.valid_from DESC NULLS LAST, r.id
                LIMIT $1 OFFSET $2
            """,
            "news": """
                SELECT n.external_id, n.outlet_name, n.title, n.url,
                       n.excerpt, n.published_at, sd.content_sha256 AS source_sha256,
                       COALESCE(
                         jsonb_agg(
                           DISTINCT jsonb_build_object(
                             'official_source_url', evd.url,
                             'supported_claim', e.supported_claim
                           )
                         ) FILTER (WHERE evd.id IS NOT NULL), '[]'::jsonb
                       ) AS official_evidence
                FROM news_articles n
                JOIN source_documents sd ON sd.id = n.source_document_id
                LEFT JOIN news_evidence e ON e.news_article_id = n.id
                LEFT JOIN source_documents evd
                  ON evd.id = e.source_document_id
                 AND EXISTS (
                    SELECT 1
                    FROM source_archive_attestations evidence_archive
                    WHERE evidence_archive.source_document_id = evd.id
                      AND evidence_archive.content_sha256 = evd.content_sha256
                      AND evidence_archive.retrieval_url = evd.url
                 )
                WHERE n.publication_status = 'PUBLISHED'
                  AND n.review_status = 'VERIFIED_WITH_OFFICIAL_EVIDENCE'
                  AND EXISTS (
                    SELECT 1
                    FROM source_archive_attestations article_archive
                    WHERE article_archive.source_document_id = sd.id
                      AND article_archive.content_sha256 = sd.content_sha256
                      AND article_archive.retrieval_url = sd.url
                  )
                  AND EXISTS (
                    SELECT 1
                    FROM news_evidence official_evidence
                    JOIN source_documents official_source
                      ON official_source.id = official_evidence.source_document_id
                    JOIN source_archive_attestations official_archive
                      ON official_archive.source_document_id = official_source.id
                    WHERE official_evidence.news_article_id = n.id
                      AND official_source.publisher <> 'MEDIA'
                      AND official_archive.content_sha256 = official_source.content_sha256
                      AND official_archive.retrieval_url = official_source.url
                  )
                GROUP BY n.id, sd.id
                ORDER BY n.published_at DESC NULLS LAST
                LIMIT $1 OFFSET $2
            """,
            "citizen-alerts": """
                SELECT a.id, a.category::text, a.title, a.body, a.effective_at,
                       a.expires_at, m.name AS municipality,
                       sd.url AS source_url, sd.content_sha256 AS source_sha256
                FROM citizen_alerts a
                JOIN source_documents sd ON sd.id = a.source_document_id
                LEFT JOIN municipalities m ON m.id = a.municipality_id
                WHERE a.publication_status = 'PUBLISHED'
                  AND a.requires_human_review = true
                  AND EXISTS (
                    SELECT 1
                    FROM source_archive_attestations alert_archive
                    WHERE alert_archive.source_document_id = sd.id
                      AND alert_archive.content_sha256 = sd.content_sha256
                      AND alert_archive.retrieval_url = sd.url
                  )
                ORDER BY a.effective_at DESC NULLS LAST, a.id
                LIMIT $1 OFFSET $2
            """,
            "rights-of-reply": """
                SELECT public_reference, target_type, target_id,
                       original_record_sha256, claimant_public_name, claimant_role,
                       statement_text, statement_sha256, official_response_url,
                       submitted_at, published_at, audit_sha256
                FROM rights_of_reply
                WHERE status = 'PUBLISHED'
                ORDER BY published_at DESC NULLS LAST, public_reference
                LIMIT $1 OFFSET $2
            """,
        }
        query = queries.get(dataset)
        if query is None:
            raise ValueError("Conjunto Open Data desconhecido")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(query, limit, offset)
        return [dict(row) for row in rows]
