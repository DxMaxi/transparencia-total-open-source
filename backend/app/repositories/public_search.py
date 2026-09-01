"""Pesquisa federada apenas sobre as projeções públicas existentes."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable
from typing import Any
from urllib.parse import urlencode

import asyncpg

from app.core.public_database_errors import is_public_database_unavailable
from app.repositories.ai_editorial_publication import PublicAiExplanationRepository
from app.repositories.public_parliament import PublicParliamentRepository
from app.repositories.public_politicians import PublicPoliticianRepository

logger = logging.getLogger(__name__)

_SECTION_ORDER = (
    "politicians",
    "parliament_sessions",
    "parliament_initiatives",
    "parliament_votes",
    "promises",
    "ai_explanations",
)
_SECTION_LABELS = {
    "politicians": "Políticos",
    "parliament_sessions": "Reuniões parlamentares",
    "parliament_initiatives": "Iniciativas parlamentares",
    "parliament_votes": "Votações parlamentares",
    "promises": "Promessómetro",
    "ai_explanations": "Explicações com IA revistas",
}
_SECTION_PATHS = {
    "politicians": "/politicos",
    "parliament_sessions": "/atividade-parlamentar?tipo=sessoes",
    "parliament_initiatives": "/atividade-parlamentar?tipo=iniciativas",
    "parliament_votes": "/atividade-parlamentar?tipo=votacoes",
    "promises": "/promessas",
    "ai_explanations": "/explicacoes",
}
_SECTION_COVERAGE = {
    "politicians": (
        "Identidades presentes numa fotografia oficial arquivada e integralmente aprovada; "
        "nomes semelhantes nunca são associados."
    ),
    "parliament_sessions": (
        "Reuniões da fotografia parlamentar oficial mais recente aprovada para a legislatura."
    ),
    "parliament_initiatives": (
        "Iniciativas da fotografia parlamentar oficial mais recente aprovada para a legislatura."
    ),
    "parliament_votes": (
        "Votações da fotografia oficial mais recente aprovada; posições individuais só usam "
        "identificadores oficiais inequívocos."
    ),
    "promises": (
        "Compromissos aceites por revisão humana; estados além de por verificar exigem prova "
        "oficial arquivada."
    ),
    "ai_explanations": (
        "Explicações de documentos do Diário da República publicadas por decisão humana; "
        "a IA não é fonte e não produz previsões nesta pesquisa."
    ),
}
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
    "SNS": "Serviço Nacional de Saúde — fonte oficial",
    "MUNICIPALITY": "Município — fonte oficial",
    "OTHER_OFFICIAL": "Fonte oficial",
}
_PROMISE_STATUS_LABELS = {
    "UNVERIFIED": "Por verificar",
    "NOT_STARTED": "Não iniciada",
    "IN_PROGRESS": "Em curso",
    "PARTIAL": "Parcialmente cumprida",
    "FULFILLED": "Cumprida",
}


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


def _exact_count(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RuntimeError("A projeção pública não devolveu uma contagem exata")
    return value


def _source(row: dict[str, Any]) -> dict[str, Any]:
    publisher = str(row["source_publisher"])
    return {
        "publisher": _PUBLISHER_CODES.get(publisher, "OFICIAL"),
        "label": _PUBLISHER_LABELS.get(publisher, "Fonte oficial"),
        "url": row["source_url"],
        "retrieved_at": row["source_retrieved_at"],
        "content_sha256": row["source_sha256"],
    }


def _path(path: str, **parameters: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urlencode(parameters)}" if parameters else path


def _available_section(
    kind: str,
    *,
    total: int,
    items: list[dict[str, Any]],
    view_all_href: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "label": _SECTION_LABELS[kind],
        "availability": "AVAILABLE",
        "total": total,
        "total_is_exact": True,
        "items": items,
        "view_all_href": view_all_href,
        "coverage_note": _SECTION_COVERAGE[kind],
    }


def _unavailable_section(kind: str, *, view_all_href: str) -> dict[str, object]:
    return {
        "kind": kind,
        "label": _SECTION_LABELS[kind],
        "availability": "UNAVAILABLE",
        "total": None,
        "total_is_exact": False,
        "items": [],
        "view_all_href": view_all_href,
        "coverage_note": (
            "Dados temporariamente indisponíveis nesta fonte. Não são usados exemplos, "
            "listas antigas ou dados por rever como substituição."
        ),
    }


class PublicGlobalSearchRepository:
    """Agrega consultas existentes sem criar uma nova porta de publicação."""

    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self.pool = pool

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        return self.pool

    async def search(
        self,
        *,
        query: str,
        legislature: str,
        section_limit: int,
    ) -> dict[str, object]:
        tasks: dict[str, Awaitable[object]] = {
            "politicians": self._search_politicians(query=query, limit=section_limit),
            "parliament": self._search_parliament(
                query=query,
                legislature=legislature,
                limit=section_limit,
            ),
            "promises": self._search_promises(query=query, limit=section_limit),
            "ai_explanations": self._search_ai(query=query, limit=section_limit),
        }
        task_names = list(tasks)
        outcomes = await asyncio.gather(*tasks.values(), return_exceptions=True)
        resolved = dict(zip(task_names, outcomes, strict=True))

        sections: dict[str, dict[str, object]] = {}
        for task_name, outcome in resolved.items():
            if isinstance(outcome, BaseException):
                if not is_public_database_unavailable(outcome):
                    raise outcome
                affected = (
                    (
                        "parliament_sessions",
                        "parliament_initiatives",
                        "parliament_votes",
                    )
                    if task_name == "parliament"
                    else (task_name,)
                )
                for kind in affected:
                    sections[kind] = _unavailable_section(
                        kind,
                        view_all_href=self._view_all_href(
                            kind,
                            query=query,
                            legislature=legislature,
                        ),
                    )
                logger.warning(
                    "public_global_search_section_unavailable",
                    extra={"public_search_section": task_name},
                )
                continue

            if task_name == "parliament":
                assert isinstance(outcome, dict)
                for kind, section in outcome.items():
                    sections[kind] = section
            else:
                assert isinstance(outcome, dict)
                sections[task_name] = outcome

        ordered = [sections[kind] for kind in _SECTION_ORDER]
        available = [section for section in ordered if section["availability"] == "AVAILABLE"]
        return {
            "query": query,
            "legislature": legislature,
            "section_limit": section_limit,
            "total_results": sum(_exact_count(section["total"]) for section in available),
            "available_sections": len(available),
            "unavailable_sections": len(ordered) - len(available),
            "sections": ordered,
        }

    def _view_all_href(self, kind: str, *, query: str, legislature: str) -> str:
        parameters = {"q": query}
        if kind.startswith("parliament_"):
            parameters["legislatura"] = legislature
        return _path(_SECTION_PATHS[kind], **parameters)

    async def _search_politicians(self, *, query: str, limit: int) -> dict[str, object]:
        result = await PublicPoliticianRepository(self._require_pool()).explore(
            query=query,
            party_short=None,
            limit=limit,
            cursor=None,
        )
        items = [
            {
                "id": person["id"],
                "kind": "politicians",
                "title": person["name"],
                "description": (
                    f"{person['party']} · {person['constituency']} · "
                    f"Legislatura {person['legislature']}"
                ),
                "href": f"/politicos/{person['slug']}",
                "source": person["profile_source"],
                "verified_at": person["verified_at"],
                "observed_at": person["observed_at"],
                "coverage_note": (
                    "A correspondência é a identidade oficial publicada; o nome não foi usado "
                    "para criar uma associação nova."
                ),
            }
            for person in _json_list(result["items"])
        ]
        return _available_section(
            "politicians",
            total=_exact_count(result["total"]),
            items=items,
            view_all_href=self._view_all_href(
                "politicians",
                query=query,
                legislature="",
            ),
        )

    async def _search_parliament(
        self,
        *,
        query: str,
        legislature: str,
        limit: int,
    ) -> dict[str, dict[str, object]]:
        result = await PublicParliamentRepository(self._require_pool()).search_global(
            query=query,
            legislature=legislature,
            limit=limit,
        )
        output: dict[str, dict[str, object]] = {}
        specifications = {
            "parliament_sessions": ("sessions", self._parliament_session_item),
            "parliament_initiatives": ("initiatives", self._parliament_initiative_item),
            "parliament_votes": ("votes", self._parliament_vote_item),
        }
        for kind, (result_key, mapper) in specifications.items():
            section = result[result_key]
            output[kind] = _available_section(
                kind,
                total=_exact_count(section["total"]),
                items=[mapper(item, query=query) for item in _json_list(section["items"])],
                view_all_href=self._view_all_href(
                    kind,
                    query=query,
                    legislature=legislature,
                ),
            )
        return output

    @staticmethod
    def _parliament_session_item(item: dict[str, Any], *, query: str) -> dict[str, Any]:
        return {
            "id": item["id"],
            "kind": "parliament_sessions",
            "title": item["title"],
            "description": (
                f"Reunião {item.get('session_number') or 'sem número indicado'} · "
                f"Legislatura {item['legislature']}"
            ),
            "href": _path(
                "/atividade-parlamentar?tipo=sessoes",
                legislatura=item["legislature"],
                q=query,
            ),
            "source": item["source"],
            "verified_at": item["verified_at"],
            "observed_at": item["starts_at"],
            "coverage_note": "Reunião presente na fotografia oficial publicada.",
        }

    @staticmethod
    def _parliament_initiative_item(item: dict[str, Any], *, query: str) -> dict[str, Any]:
        return {
            "id": item["id"],
            "kind": "parliament_initiatives",
            "title": item["title"],
            "description": f"{item['initiative_type']} {item['number']}",
            "href": _path(
                "/atividade-parlamentar?tipo=iniciativas",
                legislatura=item["legislature"],
                q=query,
            ),
            "source": item["source"],
            "verified_at": item["verified_at"],
            "observed_at": item.get("introduced_at"),
            "coverage_note": "Iniciativa presente na fotografia oficial publicada.",
        }

    @staticmethod
    def _parliament_vote_item(item: dict[str, Any], *, query: str) -> dict[str, Any]:
        result = item.get("result") or "Resultado não indicado pela fonte"
        return {
            "id": item["id"],
            "kind": "parliament_votes",
            "title": item["title"],
            "description": f"{result} · Legislatura {item['legislature']}",
            "href": _path(
                "/atividade-parlamentar?tipo=votacoes",
                legislatura=item["legislature"],
                q=query,
            ),
            "source": item["source"],
            "verified_at": item["verified_at"],
            "observed_at": item.get("voted_at"),
            "coverage_note": (
                "Votação presente na fotografia oficial publicada; o impacto não é inferido."
            ),
        }

    async def _search_promises(self, *, query: str, limit: int) -> dict[str, object]:
        pattern = _like_pattern(query)
        pool = self._require_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                WITH selected AS (
                    SELECT promise.id, promise.title, promise.area,
                           promise.status::text AS status, latest_review.reviewed_at,
                           source.publisher::text AS source_publisher,
                           source.url AS source_url,
                           source.retrieved_at AS source_retrieved_at,
                           source.content_sha256 AS source_sha256
                    FROM promises promise
                    JOIN LATERAL (
                        SELECT review.decision::text AS decision, review.reviewed_at
                        FROM promise_reviews review
                        WHERE review.promise_id = promise.id
                        ORDER BY review.reviewed_at DESC, review.id DESC
                        LIMIT 1
                    ) latest_review ON latest_review.decision = 'ACCEPT'
                    JOIN government_programmes programme
                      ON programme.id = promise.programme_id
                    JOIN source_documents source
                      ON source.id = programme.source_document_id
                    WHERE promise.status::text IN (
                        'UNVERIFIED', 'NOT_STARTED', 'IN_PROGRESS', 'PARTIAL', 'FULFILLED'
                    )
                      AND (
                        promise.title ILIKE $1 ESCAPE '!'
                        OR promise.area ILIKE $1 ESCAPE '!'
                        OR COALESCE(promise.rationale, '') ILIKE $1 ESCAPE '!'
                      )
                      AND EXISTS (
                        SELECT 1
                        FROM source_archive_attestations archive
                        WHERE archive.source_document_id = source.id
                          AND archive.content_sha256 = source.content_sha256
                          AND archive.retrieval_url = source.url
                      )
                      AND (promise.status = 'UNVERIFIED' OR EXISTS (
                        SELECT 1
                        FROM promise_evidence proof
                        JOIN source_documents proof_source
                          ON proof_source.id = proof.source_document_id
                        JOIN source_archive_attestations proof_archive
                          ON proof_archive.source_document_id = proof_source.id
                        WHERE proof.promise_id = promise.id
                          AND proof_archive.content_sha256 = proof_source.content_sha256
                          AND proof_archive.retrieval_url = proof_source.url
                      ))
                ), page AS (
                    SELECT *
                    FROM selected
                    ORDER BY area, title, id
                    LIMIT $2
                )
                SELECT (SELECT COUNT(*)::integer FROM selected) AS total,
                       COALESCE(
                           (SELECT jsonb_agg(to_jsonb(page) ORDER BY area, title, id) FROM page),
                           '[]'::jsonb
                       ) AS items
                """,
                pattern,
                limit,
            )
        if row is None:
            raise RuntimeError("A projeção pública de promessas não respondeu")
        promises = _json_list(row["items"])
        items = [
            {
                "id": promise["id"],
                "kind": "promises",
                "title": promise["title"],
                "description": (
                    f"{promise['area']} · "
                    f"{_PROMISE_STATUS_LABELS.get(str(promise['status']), 'Estado publicado')}"
                ),
                "href": f"/promessas#promessa-{promise['id']}",
                "source": _source(promise),
                "verified_at": promise["reviewed_at"],
                "observed_at": None,
                "coverage_note": (
                    "Compromisso do programa aceite por revisão humana; o estado mantém a "
                    "exigência de prova do Promessómetro."
                ),
            }
            for promise in promises
        ]
        return _available_section(
            "promises",
            total=_exact_count(row["total"]),
            items=items,
            view_all_href=self._view_all_href("promises", query=query, legislature=""),
        )

    async def _search_ai(self, *, query: str, limit: int) -> dict[str, object]:
        result = await PublicAiExplanationRepository(self._require_pool()).list_explanations(
            query=query,
            limit=limit,
            offset=0,
        )
        items = []
        for explanation in _json_list(result["items"]):
            summary = explanation["summary"]
            source = explanation["source"]
            editorial = explanation["editorial"]
            items.append(
                {
                    "id": explanation["id"],
                    "kind": "ai_explanations",
                    "title": summary["title"],
                    "description": summary["summary_2_minutes"],
                    "href": f"/explicacoes/{explanation['id']}",
                    "source": {
                        "publisher": source["publisher"],
                        "label": source["label"],
                        "url": source["url"],
                        "retrieved_at": source["retrieved_at"],
                        "content_sha256": source["content_sha256"],
                    },
                    "verified_at": editorial["published_at"],
                    "observed_at": source.get("published_at"),
                    "coverage_note": (
                        "Texto gerado por IA, explicitamente revisto e publicado por humano; "
                        "não é uma fonte nem uma previsão."
                    ),
                }
            )
        return _available_section(
            "ai_explanations",
            total=_exact_count(result["total"]),
            items=items,
            view_all_href=self._view_all_href(
                "ai_explanations",
                query=query,
                legislature="",
            ),
        )
