import hashlib
import json
import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.core.config import Settings
from app.models.api import (
    BaseContractCollection,
    ParliamentDataset,
    PushSubscriptionRequest,
    RightOfReplyReceipt,
    RightOfReplyRequest,
)

logger = logging.getLogger(__name__)

PUBLICATION_RULE = (
    "Apenas registos aprovados segundo a regra explícita do respetivo conjunto; "
    "a ingestão nunca equivale a publicação."
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
                    {"source_name": source, "status": "NEVER"}
                    for source in canonical_sources
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
                        WHERE dpr.entity_type = 'PERSON' AND dpr.entity_id = p.id
                        ORDER BY dpr.reviewed_at DESC, dpr.id DESC LIMIT 1
                      ) = TRUE
                  ) AS politicians,
                  (
                    SELECT COUNT(*) FROM promises p
                    WHERE p.status IN ('FULFILLED', 'IN_PROGRESS', 'BROKEN', 'ABANDONED')
                      AND EXISTS (SELECT 1 FROM promise_evidence pe WHERE pe.promise_id = p.id)
                      AND (
                        SELECT pr.decision::text FROM promise_reviews pr
                        WHERE pr.promise_id = p.id
                        ORDER BY pr.reviewed_at DESC, pr.id DESC LIMIT 1
                      ) = 'ACCEPT'
                  ) AS promises,
                  (
                    SELECT COUNT(*) FROM public_contracts
                    WHERE publication_status = 'PUBLISHED' AND verification_status = 'VERIFIED'
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
                  ) AS relationships,
                  (
                    SELECT COUNT(*) FROM news_articles
                    WHERE publication_status = 'PUBLISHED'
                      AND review_status = 'VERIFIED_WITH_OFFICIAL_EVIDENCE'
                  ) AS news,
                  (
                    SELECT COUNT(*) FROM citizen_alerts
                    WHERE publication_status = 'PUBLISHED' AND requires_human_review = TRUE
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
                    SELECT dpr.publishable, dpr.reviewed_at
                    FROM data_publication_reviews dpr
                    WHERE dpr.entity_type = 'PERSON' AND dpr.entity_id = p.id
                    ORDER BY dpr.reviewed_at DESC, dpr.id DESC LIMIT 1
                ) review ON review.publishable = TRUE
                JOIN LATERAL (
                    SELECT snapshot.party_id, snapshot.constituency, snapshot.legislature,
                           snapshot.source_document_id
                    FROM parliamentary_membership_snapshots snapshot
                    WHERE snapshot.person_id = p.id
                    ORDER BY snapshot.observed_at DESC, snapshot.id DESC LIMIT 1
                ) ms ON TRUE
                JOIN source_documents sd ON sd.id = ms.source_document_id
                LEFT JOIN parties pa ON pa.id = ms.party_id
                WHERE p.active = TRUE AND ($1::text IS NULL OR p.slug = $1)
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
                       COUNT(*) FILTER (WHERE ar.present = TRUE) AS present
                FROM mandates m
                JOIN attendance_records ar ON ar.mandate_id = m.id
                WHERE m.person_id = $1
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
                JOIN source_documents sd ON sd.id = vr.source_document_id
                WHERE vr.person_id = $1 AND vr.actor_type = 'PERSON'
                  AND ve.is_nominal = TRUE AND vr.choice <> 'UNKNOWN'
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
                ORDER BY adm.declared_at DESC NULLS LAST, adm.created_at DESC
                LIMIT 1
                """,
                row["id"],
            )
        total = int(attendance["total"])
        present = int(attendance["present"])
        attendance_rate = round(present * 100 / total) if total else None
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
                    WHERE p.status IN ('FULFILLED', 'IN_PROGRESS', 'BROKEN', 'ABANDONED')
                      AND EXISTS (
                        SELECT 1 FROM promise_evidence proof WHERE proof.promise_id = p.id
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
                    "rationale": row["rationale"] or (
                        "Decisão fundamentada no histórico de revisão."
                    ),
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
                       pc.contract_value, pc.published_at AS contract_published_at,
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
                WHERE r.publication_status = 'PUBLISHED'
                  AND r.verification_status = 'VERIFIED'
                  AND f.publication_status = 'PUBLISHED'
                  AND f.verification_status = 'VERIFIED'
                  AND t.publication_status = 'PUBLISHED'
                  AND t.verification_status = 'VERIFIED'
                  AND sd.publisher <> 'MEDIA'
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
                       (SELECT COUNT(*) FROM public_statements all_ps
                        WHERE all_ps.person_id = p.id) AS total_statements
                FROM statement_vote_comparisons c
                JOIN public_statements ps ON ps.id = c.statement_id
                JOIN people p ON p.id = ps.person_id
                JOIN source_documents statement_sd ON statement_sd.id = ps.source_document_id
                JOIN vote_events ve ON ve.id = c.vote_event_id
                JOIN vote_records vr ON vr.vote_event_id = ve.id
                  AND vr.person_id = ps.person_id AND vr.actor_type = 'PERSON'
                JOIN source_documents vote_sd ON vote_sd.id = vr.source_document_id
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
                  AND vr.choice <> 'UNKNOWN'
                  AND statement_sd.publisher <> 'MEDIA'
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
    async def _upsert_source_document(
        connection: asyncpg.Connection,
        *,
        publisher: str,
        kind: str,
        title: str,
        url: str,
        retrieved_at: datetime,
        content_sha256: str,
        parser_version: str,
    ) -> str:
        row = await connection.fetchrow(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, url, retrieved_at, content_sha256,
                 parser_version, created_at)
            VALUES ($1, $2::"SourcePublisher", $3::"DocumentKind", $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (url, content_sha256) DO UPDATE SET
                retrieved_at = GREATEST(source_documents.retrieved_at, EXCLUDED.retrieved_at),
                parser_version = EXCLUDED.parser_version
            RETURNING id
            """,
            _new_id("source"),
            publisher,
            kind,
            title,
            url,
            _database_timestamp(retrieved_at),
            content_sha256,
            parser_version,
        )
        return str(row["id"])

    async def store_parliament_dataset(
        self,
        dataset: ParliamentDataset,
        *,
        kind: str,
        code_version: str,
    ) -> dict[str, int]:
        if kind not in {"deputies", "votes"}:
            raise ValueError("Tipo de dataset parlamentar desconhecido")
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
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                source_document_id = await self._upsert_source_document(
                    connection,
                    publisher="PARLIAMENT",
                    kind="OPEN_DATASET",
                    title=f"Assembleia da República — {kind} — {dataset.legislature}",
                    url=str(dataset.dataset_url),
                    retrieved_at=dataset.collected_at,
                    content_sha256=dataset.document_sha256,
                    parser_version=code_version,
                )
                if kind == "deputies":
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
                            ON CONFLICT (source_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                initiative_number = EXCLUDED.initiative_number,
                                voted_at = EXCLUDED.voted_at,
                                result = EXCLUDED.result,
                                is_nominal = EXCLUDED.is_nominal,
                                source_document_id = EXCLUDED.source_document_id,
                                updated_at = NOW()
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
                        await connection.execute(
                            "DELETE FROM vote_records WHERE vote_event_id = $1",
                            event_row["id"],
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
                                ON CONFLICT (vote_event_id, actor_type, actor_label) DO UPDATE SET
                                    person_id = EXCLUDED.person_id,
                                    choice = EXCLUDED.choice,
                                    source_document_id = EXCLUDED.source_document_id
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
        return {"records_read": records_read, "records_written": written}

    async def store_base_collection(
        self,
        collection: BaseContractCollection,
        *,
        code_version: str,
    ) -> dict[str, int]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        records_read = len(collection.contracts)
        warnings = list(collection.warnings)
        dataset_url = str(collection.dataset_resource.url)
        sync_id = await self._start_sync_run(
            source_name="BASE_CONTRACTS",
            dataset_url=dataset_url,
            code_version=code_version,
        )
        written = 0
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                dataset_document_id = await self._upsert_source_document(
                    connection,
                    publisher="BASE_GOV",
                    kind="OPEN_DATASET",
                    title=collection.dataset_resource.title,
                    url=dataset_url,
                    retrieved_at=collection.collected_at,
                    content_sha256=collection.document_sha256,
                    parser_version=code_version,
                )
                for contract in collection.contracts:
                    contract_url = str(contract.direct_official_url or contract.source.url)
                    contract_document_id = (
                        dataset_document_id
                        if contract_url == dataset_url
                        else await self._upsert_source_document(
                            connection,
                            publisher="BASE_GOV",
                            kind="PUBLIC_CONTRACT",
                            title=f"Portal BASE — contrato {contract.source_id}",
                            url=contract_url,
                            retrieved_at=collection.collected_at,
                            content_sha256=collection.document_sha256,
                            parser_version=code_version,
                        )
                    )
                    contract_row = await connection.fetchrow(
                        """
                        INSERT INTO public_contracts
                            (id, source_id, object, procedure, cpv_code, base_value,
                             contract_value, currency, decision_at, signed_at, published_at,
                             execution_days, source_document_id, verification_status,
                             publication_status, created_at, updated_at)
                        VALUES ($1, $2, $3, $4::"PublicContractProcedure", $5, $6, $7,
                                $8, $9, $10, $11, $12, $13, 'INGESTED', 'UNDER_REVIEW',
                                NOW(), NOW())
                        ON CONFLICT (source_id) DO UPDATE SET
                            object = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.object ELSE EXCLUDED.object END,
                            procedure = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.procedure ELSE EXCLUDED.procedure END,
                            cpv_code = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.cpv_code ELSE EXCLUDED.cpv_code END,
                            base_value = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.base_value ELSE EXCLUDED.base_value END,
                            contract_value = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.contract_value ELSE EXCLUDED.contract_value END,
                            decision_at = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.decision_at ELSE EXCLUDED.decision_at END,
                            signed_at = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.signed_at ELSE EXCLUDED.signed_at END,
                            published_at = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.published_at ELSE EXCLUDED.published_at END,
                            execution_days = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.execution_days ELSE EXCLUDED.execution_days END,
                            source_document_id = CASE
                              WHEN public_contracts.publication_status = 'PUBLISHED'
                              THEN public_contracts.source_document_id
                              ELSE EXCLUDED.source_document_id END,
                            updated_at = NOW()
                        RETURNING id, publication_status::text
                        """,
                        _new_id("contract"),
                        contract.source_id,
                        contract.object,
                        contract.procedure.value,
                        contract.cpv_code,
                        contract.base_value,
                        contract.contract_value,
                        contract.currency,
                        _database_timestamp(contract.decision_at),
                        _database_timestamp(contract.signed_at),
                        _database_timestamp(contract.published_at),
                        contract.execution_days,
                        contract_document_id,
                    )
                    if contract_row["publication_status"] == "PUBLISHED":
                        warnings.append(
                            "Contrato "
                            f"{contract.source_id} já publicado: a nova fotografia foi "
                            "conservada como fonte, sem alterar o registo público."
                        )
                        continue
                    await connection.execute(
                        "DELETE FROM public_contract_parties WHERE public_contract_id = $1",
                        contract_row["id"],
                    )
                    parties = [*contract.contracting_authorities, *contract.contractors]
                    for party in parties:
                        normalised = _normalise_name(party.name)
                        role_kind = (
                            "PUBLIC_BODY"
                            if party.role.value == "CONTRACTING_AUTHORITY"
                            else "COMPANY"
                        )
                        source_key = hashlib.sha256(
                            f"{role_kind}:{normalised}".encode()
                        ).hexdigest()[:32]
                        organisation_row = await connection.fetchrow(
                            """
                            INSERT INTO organisations
                                (id, source_id, legal_name, normalised_name, kind,
                                 public_nipc, official_url, source_document_id,
                                 verification_status, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5::"InterestEntityKind", NULL, NULL,
                                    $6, 'INGESTED', NOW(), NOW())
                            ON CONFLICT (source_id) DO UPDATE SET updated_at = NOW()
                            RETURNING id
                            """,
                            _new_id("organisation"),
                            f"base-party:{source_key}",
                            party.name,
                            normalised,
                            role_kind,
                            dataset_document_id,
                        )
                        entity_row = await connection.fetchrow(
                            """
                            INSERT INTO interest_entities
                                (id, kind, public_label, organisation_id,
                                 verification_status, publication_status,
                                 created_at, updated_at)
                            VALUES ($1, $2::"InterestEntityKind", $3, $4,
                                    'INGESTED', 'UNDER_REVIEW', NOW(), NOW())
                            ON CONFLICT (organisation_id) DO UPDATE SET updated_at = NOW()
                            RETURNING id
                            """,
                            _new_id("entity"),
                            role_kind,
                            party.name,
                            organisation_row["id"],
                        )
                        await connection.execute(
                            """
                            INSERT INTO public_contract_parties
                                (id, public_contract_id, interest_entity_id, role,
                                 source_name, source_public_id, created_at)
                            VALUES ($1, $2, $3, $4::"ContractPartyRole", $5, NULL, NOW())
                            ON CONFLICT (public_contract_id, interest_entity_id, role) DO UPDATE SET
                                source_name = EXCLUDED.source_name
                            """,
                            _new_id("contract_party"),
                            contract_row["id"],
                            entity_row["id"],
                            party.role.value,
                            party.name,
                        )
                        written += 1
                    written += 1
            await self._finish_sync_run(
                sync_id,
                status_value="PARTIAL" if warnings else "SUCCEEDED",
                records_read=records_read,
                records_written=written,
                warnings=warnings,
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=records_read,
                records_written=0,
                warnings=warnings,
                error_message=str(exc),
            )
            raise
        return {"records_read": records_read, "records_written": written}

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

        async with self.pool.acquire() as connection, connection.transaction():
            if entity_type == "PERSON":
                current = await connection.fetchrow(
                    "SELECT id, active FROM people WHERE id = $1",
                    entity_id,
                )
                evidence_exists = await connection.fetchval(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM parliamentary_membership_snapshots
                      WHERE person_id = $1
                    )
                    """,
                    entity_id,
                )
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
                           publication_status::text AS publication_status
                    FROM public_contracts WHERE id = $1
                    """,
                    entity_id,
                )
                evidence_exists = current is not None
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
                           t.verification_status::text AS to_verification_status
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
                sensitivity = "PUBLIC_OFFICIAL"

            if current is None:
                raise ValueError("Entidade a rever não encontrada")
            if publish and not evidence_exists:
                raise ValueError("A publicação exige prova associada e dependências publicadas")

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
                     reviewed_by, reviewed_at)
                VALUES ($1, $2, $3, $4, 'PUBLIC_INTEREST', $5::"DataSensitivity",
                        $6, $7, $8, $9, NOW())
                """,
                _new_id("publication_review"),
                entity_type,
                entity_id,
                "Informação factual necessária à fiscalização democrática",
                sensitivity,
                "A fonte e a identidade do registo foram verificadas pelo revisor.",
                "A exposição é limitada aos campos públicos necessários e conserva a fonte.",
                publish,
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
                         ) FILTER (WHERE e.id IS NOT NULL), '[]'::jsonb
                       ) AS official_evidence
                FROM news_articles n
                JOIN source_documents sd ON sd.id = n.source_document_id
                LEFT JOIN news_evidence e ON e.news_article_id = n.id
                LEFT JOIN source_documents evd ON evd.id = e.source_document_id
                WHERE n.publication_status = 'PUBLISHED'
                  AND n.review_status = 'VERIFIED_WITH_OFFICIAL_EVIDENCE'
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
