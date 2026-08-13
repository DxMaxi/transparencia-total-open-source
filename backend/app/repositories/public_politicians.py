from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any

import asyncpg


class PublicPoliticianCursorError(ValueError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _filter_fingerprint(query: str | None, party_short: str | None) -> str:
    payload = {
        "party_short": party_short or "",
        "query": query.casefold() if query else "",
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def _encode_cursor(
    *,
    sort_name: str,
    slug: str,
    query: str | None,
    party_short: str | None,
) -> str:
    payload = [
        1,
        sort_name,
        slug,
        _filter_fingerprint(query, party_short),
    ]
    return (
        base64.urlsafe_b64encode(_canonical_json(payload).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )


def _decode_cursor(
    cursor: str,
    *,
    query: str | None,
    party_short: str | None,
) -> tuple[str, str]:
    if not cursor or len(cursor) > 512:
        raise PublicPoliticianCursorError("Cursor de paginação inválido")
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded.decode("utf-8"))
        if (
            not isinstance(payload, list)
            or len(payload) != 4
            or not isinstance(payload[0], int)
            or isinstance(payload[0], bool)
            or payload[0] != 1
        ):
            raise ValueError
        sort_name, slug, fingerprint = payload[1:]
        if not all(isinstance(value, str) for value in (sort_name, slug, fingerprint)):
            raise TypeError
        if not sort_name or len(sort_name) > 500:
            raise ValueError
        if not slug or len(slug) > 200:
            raise ValueError
        if fingerprint != _filter_fingerprint(query, party_short):
            raise ValueError
    except (binascii.Error, json.JSONDecodeError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise PublicPoliticianCursorError("Cursor de paginação inválido") from exc
    return sort_name, slug


def _like_pattern(value: str) -> str:
    escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


def _json_list(value: object) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _source(row: dict[str, Any]) -> dict[str, Any]:
    publisher = str(row["source_publisher"])
    publisher_codes = {
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
    publisher_labels = {
        "PARLIAMENT": "Assembleia da República — fonte oficial",
        "DRE": "Diário da República — diploma oficial",
        "TRANSPARENCY_ENTITY": "Entidade para a Transparência — fonte oficial",
        "BASE_GOV": "Portal BASE — contrato público",
        "COURT_OF_AUDIT": "Tribunal de Contas — fonte oficial",
        "EUROPEAN_PARLIAMENT": "Parlamento Europeu — fonte oficial",
        "SNS": "Serviço Nacional de Saúde — fonte oficial",
        "MUNICIPALITY": "Município — fonte oficial",
    }
    return {
        "publisher": publisher_codes.get(publisher, "OFICIAL"),
        "label": publisher_labels.get(publisher, "Fonte oficial"),
        "url": row["source_url"],
        "retrieved_at": row["source_retrieved_at"],
        "content_sha256": row["source_sha256"],
    }


def _person(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "role": row["role"],
        "party": row["party"],
        "party_short": row["party_short"],
        "constituency": row["constituency"],
        "legislature": row["legislature"],
        "portrait_url": row.get("photo_url"),
        "observed_at": row["observed_at"],
        "verified_at": row["verified_at"],
        "profile_source": _source(row),
    }


class PublicPoliticianRepository:
    """Consulta apenas identidades já publicadas, com paginação keyset estável."""

    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self.pool = pool

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        return self.pool

    async def explore(
        self,
        *,
        query: str | None,
        party_short: str | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, object]:
        after_name: str | None = None
        after_slug: str | None = None
        if cursor is not None:
            after_name, after_slug = _decode_cursor(
                cursor,
                query=query,
                party_short=party_short,
            )

        row = await self._require_pool().fetchrow(
            """
            WITH reviewed_sources AS (
                SELECT membership.source_document_id, membership.legislature,
                       MAX(latest_review.reviewed_at) AS fully_reviewed_at,
                       source.retrieved_at
                FROM parliamentary_membership_snapshots membership
                JOIN source_documents source
                  ON source.id = membership.source_document_id
                JOIN LATERAL (
                    SELECT review.publishable, review.reviewed_at
                    FROM data_publication_reviews review
                    WHERE review.entity_type = 'PERSON'
                      AND review.entity_id = membership.person_id
                      AND review.source_document_id = membership.source_document_id
                    ORDER BY review.reviewed_at DESC, review.id DESC
                    LIMIT 1
                ) latest_review ON latest_review.publishable = TRUE
                WHERE source.publisher = 'PARLIAMENT'
                  AND EXISTS (
                      SELECT 1
                      FROM source_archive_attestations archive
                      WHERE archive.source_document_id = source.id
                        AND archive.content_sha256 = source.content_sha256
                        AND archive.retrieval_url = source.url
                  )
                GROUP BY membership.source_document_id, membership.legislature,
                         source.retrieved_at
                HAVING COUNT(*) = (
                    SELECT COUNT(*)
                    FROM parliamentary_membership_snapshots candidate
                    WHERE candidate.source_document_id = membership.source_document_id
                      AND candidate.legislature = membership.legislature
                )
            ),
            latest_sources AS (
                SELECT DISTINCT ON (legislature)
                       source_document_id, legislature, fully_reviewed_at
                FROM reviewed_sources
                ORDER BY legislature, fully_reviewed_at DESC,
                         retrieved_at DESC, source_document_id DESC
            ),
            selected_memberships AS (
                SELECT membership.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY membership.person_id
                           ORDER BY membership.observed_at DESC, membership.id DESC
                       ) AS membership_rank
                FROM parliamentary_membership_snapshots membership
                JOIN latest_sources selected
                  ON selected.source_document_id = membership.source_document_id
                 AND selected.legislature = membership.legislature
            ),
            public_people AS (
                SELECT person.id, person.slug COLLATE "C" AS slug,
                       COALESCE(membership.parliamentary_name,
                                person.parliamentary_name, person.full_name) AS name,
                       LOWER(COALESCE(membership.parliamentary_name,
                                      person.parliamentary_name,
                                      person.full_name)) COLLATE "C" AS sort_name,
                       person.role::text AS role, person.photo_url,
                       COALESCE(party.name, 'Sem filiação indicada') AS party,
                       COALESCE(party.short_name, '—') AS party_short,
                       COALESCE(membership.constituency, 'Dados indisponíveis') AS constituency,
                       COALESCE(membership.legislature, 'Dados indisponíveis') AS legislature,
                       membership.observed_at,
                       review.reviewed_at AS verified_at,
                       source.publisher::text AS source_publisher,
                       source.url AS source_url,
                       source.retrieved_at AS source_retrieved_at,
                       source.content_sha256 AS source_sha256
                FROM people person
                JOIN selected_memberships membership
                  ON membership.person_id = person.id
                 AND membership.membership_rank = 1
                JOIN LATERAL (
                    SELECT candidate.publishable, candidate.reviewed_at
                    FROM data_publication_reviews candidate
                    WHERE candidate.entity_type = 'PERSON'
                      AND candidate.entity_id = person.id
                      AND candidate.source_document_id = membership.source_document_id
                    ORDER BY candidate.reviewed_at DESC, candidate.id DESC
                    LIMIT 1
                ) review ON review.publishable = TRUE
                JOIN source_documents source
                  ON source.id = membership.source_document_id
                LEFT JOIN parties party ON party.id = membership.party_id
                WHERE EXISTS (
                    SELECT 1
                    FROM source_archive_attestations profile_archive
                    WHERE profile_archive.source_document_id = source.id
                      AND profile_archive.content_sha256 = source.content_sha256
                      AND profile_archive.retrieval_url = source.url
                )
            ),
            searched_people AS (
                SELECT *
                FROM public_people
                WHERE $1::text IS NULL
                   OR name ILIKE $1 ESCAPE '!'
                   OR party ILIKE $1 ESCAPE '!'
                   OR party_short ILIKE $1 ESCAPE '!'
                   OR constituency ILIKE $1 ESCAPE '!'
                   OR legislature ILIKE $1 ESCAPE '!'
            ),
            filtered_people AS (
                SELECT *
                FROM searched_people
                WHERE $2::text IS NULL OR party_short = $2
            ),
            page_people AS (
                SELECT *
                FROM filtered_people
                WHERE $3::text IS NULL
                   OR (sort_name, slug) >
                      ($3::text COLLATE "C", $4::text COLLATE "C")
                ORDER BY sort_name, slug
                LIMIT $5::integer
            ),
            party_facets AS (
                SELECT party_short AS value,
                       MIN(party) AS label,
                       COUNT(*)::integer AS count
                FROM searched_people
                GROUP BY party_short
            )
            SELECT (SELECT COUNT(*)::integer FROM filtered_people) AS total,
                   COALESCE(
                       (
                           SELECT jsonb_agg(
                               to_jsonb(page_people)
                               ORDER BY page_people.sort_name, page_people.slug
                           )
                           FROM page_people
                       ),
                       '[]'::jsonb
                   ) AS items,
                   COALESCE(
                       (
                           SELECT jsonb_agg(
                               jsonb_build_object(
                                   'value', party_facets.value,
                                   'label', party_facets.label,
                                   'count', party_facets.count
                               )
                               ORDER BY party_facets.value
                           )
                           FROM party_facets
                       ),
                       '[]'::jsonb
                   ) AS parties
            """,
            _like_pattern(query) if query else None,
            party_short,
            after_name,
            after_slug,
            limit + 1,
        )
        if row is None:
            raise RuntimeError("Não foi possível consultar o diretório publicado")

        page_rows = _json_list(row["items"])
        has_more = len(page_rows) > limit
        if has_more:
            page_rows = page_rows[:limit]
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_cursor(
                sort_name=str(last["sort_name"]),
                slug=str(last["slug"]),
                query=query,
                party_short=party_short,
            )

        return {
            "items": [_person(item) for item in page_rows],
            "total": int(row["total"]),
            "limit": limit,
            "next_cursor": next_cursor,
            "query": query,
            "party_short": party_short,
            "parties": _json_list(row["parties"]),
        }
