"""Porta privada entre snapshots anuais BASE e a revisão editorial V5."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import asyncpg

from app.core.security import require_official_url
from app.models.editorial import (
    BaseContractEditorialProposalRequest,
    EditorialCaseKind,
    StaffSession,
    validate_normalized_data,
)
from app.repositories.editorial import EditorialRepository, EditorialSourceError

_INGESTION_ALIAS = "base-contract-ingestion"
_SUBJECT_TYPE = "BASE_CONTRACT_SNAPSHOT"
_SOURCE_RECORD_SCHEMA = "base-contract-source-record-v1"
_PROPOSAL_SCHEMA = "base-contract-editorial-v1"
_CPV_CODE = re.compile(r"^[0-9]{8}-[0-9]$")
_DECIMAL_20_2 = re.compile(r"^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,2})?$")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _case_reference(row: Mapping[str, Any]) -> dict[str, object] | None:
    if row["case_id"] is None:
        return None
    return {
        "id": str(row["case_id"]),
        "state": str(row["case_state"]),
        "revision": int(row["case_revision"]),
        "origin": str(row["case_origin"]),
    }


def _encode_cursor(item: Mapping[str, Any]) -> str:
    batch = item["batch"]
    if not isinstance(batch, Mapping):
        raise EditorialSourceError("Não foi possível construir o cursor BASE")
    raw = _canonical_json(
        [
            int(batch["resource_year"]),
            item["published_at"],
            str(item["official_contract_id"]),
            str(item["contract_snapshot_id"]),
        ]
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[int, datetime | None, str, str]:
    if len(cursor) > 1600:
        raise EditorialSourceError("Cursor de paginação BASE inválido")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if not isinstance(payload, list) or len(payload) != 4:
            raise ValueError
        resource_year = int(payload[0])
        published_at = None
        if payload[1] is not None:
            parsed = datetime.fromisoformat(str(payload[1]).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            published_at = parsed.astimezone(UTC).replace(tzinfo=None)
        source_id = str(payload[2])
        snapshot_id = str(payload[3])
        if not 2012 <= resource_year <= 2100:
            raise ValueError
        if not 1 <= len(source_id) <= 500 or not 1 <= len(snapshot_id) <= 200:
            raise ValueError
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise EditorialSourceError("Cursor de paginação BASE inválido") from exc
    return resource_year, published_at, source_id, snapshot_id


def _json_object_list(value: object) -> tuple[list[dict[str, object]], bool]:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return [], False
    if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
        return [], False
    return [dict(item) for item in decoded], True


def _json_string_list(value: object) -> tuple[list[str], bool]:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (json.JSONDecodeError, TypeError):
        return [], False
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        return [], False
    return list(decoded), True


def _contains_unsafe_source_text(value: str) -> bool:
    try:
        validate_normalized_data({"official_source_text": value})
    except ValueError:
        return True
    return False


def _validate_base_editorial_payload(value: dict[str, Any]) -> dict[str, Any]:
    """Valida o payload produzido pelo adaptador sem confundir CPV/montantes com NIF.

    O validador editorial genérico é deliberadamente conservador e rejeita qualquer
    sequência de nove algarismos. Aqui os campos técnicos são reconstruídos no servidor
    a partir do snapshot BASE; os únicos campos livres voltam a passar pelo bloqueio
    genérico de identificadores fiscais.
    """

    if value.get("schema_version") != _PROPOSAL_SCHEMA:
        raise ValueError("A versão da proposta BASE é inválida")
    candidate = value.get("candidate")
    source = value.get("source")
    batch = value.get("annual_batch")
    catalogue = value.get("catalogue")
    archive = value.get("archive")
    proof_items = (candidate, source, batch, catalogue, archive)
    if not all(isinstance(item, Mapping) for item in proof_items):
        raise ValueError("A proposta BASE não contém a cadeia de prova obrigatória")
    assert isinstance(candidate, Mapping)
    assert isinstance(source, Mapping)
    assert isinstance(batch, Mapping)
    assert isinstance(catalogue, Mapping)

    official_contract_id = str(candidate.get("official_contract_id", ""))
    if not official_contract_id.strip() or len(official_contract_id) > 500:
        raise ValueError("O identificador oficial BASE é inválido")
    cpv_code = candidate.get("cpv_code")
    if cpv_code is not None and not _CPV_CODE.fullmatch(str(cpv_code)):
        raise ValueError("O código CPV BASE não tem o formato oficial esperado")
    for amount_name in ("base_value", "contract_value"):
        amount = candidate.get(amount_name)
        if amount is not None and not _DECIMAL_20_2.fullmatch(str(amount)):
            raise ValueError("Um montante BASE excede o formato decimal seguro")

    free_text_values: list[object] = [
        candidate.get("object"),
        source.get("title"),
        batch.get("resource_title"),
    ]
    parties = candidate.get("parties")
    if not isinstance(parties, list):
        raise ValueError("As partes BASE não têm uma representação válida")
    for party in parties:
        if not isinstance(party, Mapping):
            raise ValueError("Uma parte BASE não tem uma representação válida")
        free_text_values.append(party.get("source_name"))
    for index, text in enumerate(free_text_values):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Um campo textual BASE obrigatório está vazio")
        validate_normalized_data({f"official_source_text_{index}": text})

    urls = [
        source.get("url"),
        candidate.get("direct_official_url"),
        catalogue.get("versioned_url"),
        catalogue.get("stable_url"),
    ]
    for url in urls:
        if url is not None:
            require_official_url(str(url))
            validate_normalized_data({"official_source_url": str(url)})

    # A serialização canónica continua a validar tipos, NaN e profundidade prática.
    _canonical_json(value)
    return value


class BaseContractEditorialRepository:
    """Cria processos privados sem materializar contratos, organizações ou relações."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    async def list_candidates(
        self,
        *,
        query: str | None,
        resource_year: int | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, object]:
        normalized_query = query.strip() if query and query.strip() else None
        if normalized_query is None and resource_year is None:
            return {
                "items": [],
                "total": 0,
                "limit": limit,
                "next_cursor": None,
                "filter_required": True,
                "publication_performed": False,
                "organisation_created": False,
                "relationship_created": False,
                "protected_identifier_exposed": False,
                "search_rule": (
                    "Escolha um ano ou introduza um identificador oficial exato. A fila não "
                    "varre silenciosamente todo o histórico BASE."
                ),
                "coverage_rule": (
                    "Cada proposta prova apenas o registo específico e a coerência do lote "
                    "normalizado; não afirma que todas as linhas do ficheiro anual foram "
                    "convertidas em candidatos."
                ),
            }

        items, total = await self._load_candidates(
            query=normalized_query,
            resource_year=resource_year,
            contract_snapshot_id=None,
            source_record_sha256=None,
            limit=limit + 1,
            cursor=cursor,
        )
        has_more = len(items) > limit
        visible_items = items[:limit]
        return {
            "items": visible_items,
            "total": total,
            "limit": limit,
            "next_cursor": (
                _encode_cursor(visible_items[-1]) if has_more and visible_items else None
            ),
            "filter_required": False,
            "publication_performed": False,
            "organisation_created": False,
            "relationship_created": False,
            "protected_identifier_exposed": False,
            "search_rule": (
                "A pesquisa serve apenas para localizar snapshots privados por identificador "
                "oficial, objeto ou designação literal da fonte. Nunca constitui uma "
                "correspondência de identidade ou de organização."
            ),
            "coverage_rule": (
                "Só um registo de ano encerrado, presente no catálogo temporal atestado e num "
                "lote normalizado coerente pode originar uma proposta. A prova é específica "
                "do registo e não declara cobertura integral do ficheiro anual."
            ),
        }

    async def create_proposal(
        self,
        *,
        payload: BaseContractEditorialProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read"),
        ):
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"base-contract-editorial:{payload.contract_snapshot_id}",
            )
            await connection.fetchrow(
                """
                SELECT contract.id
                FROM base_contract_snapshots AS contract
                JOIN base_staging_batches AS batch ON batch.id = contract.batch_id
                JOIN sync_runs AS run ON run.id = batch.sync_run_id
                JOIN source_documents AS source ON source.id = batch.source_document_id
                WHERE contract.id = $1
                FOR SHARE OF contract, batch, run, source
                """,
                payload.contract_snapshot_id,
            )
            candidate = await self.get_exact_candidate(
                contract_snapshot_id=payload.contract_snapshot_id,
                source_record_sha256=payload.source_record_sha256,
                connection=connection,
            )
            if candidate is None:
                raise EditorialSourceError(
                    "O snapshot BASE não existe ou a respetiva prova deixou de coincidir"
                )
            if candidate["proposal_eligible"] is not True:
                reasons = candidate["blocked_reasons"]
                detail = (
                    "; ".join(str(reason) for reason in reasons)
                    if isinstance(reasons, list)
                    else ""
                )
                raise EditorialSourceError(
                    "O contrato BASE não reúne prova suficiente para revisão privada"
                    + (f": {detail}" if detail else "")
                )

            case, created = await self.editorial.create_ingestion_case(
                kind=EditorialCaseKind.PUBLIC_CONTRACT,
                subject_type=_SUBJECT_TYPE,
                subject_id=payload.contract_snapshot_id,
                source_document_id=str(candidate["source_document_id"]),
                normalized_data=self._normalized_proposal(candidate),
                origin_alias=_INGESTION_ALIAS,
                submission_rationale=(
                    "Registo específico do Portal BASE enviado para revisão privada após validar "
                    "fonte, arquivo, catálogo temporal, coerência do lote normalizado e "
                    "identificador oficial exato. Não se declara cobertura integral do ficheiro "
                    "anual e não foi criado contrato público, organização ou relação."
                ),
                actor=actor,
                connection=connection,
                normalized_data_validator=_validate_base_editorial_payload,
            )
        return {
            "created": created,
            "case": case,
            "state": "PRIVATE_PENDING_REVIEW",
            "publication_performed": False,
            "public_contract_created": False,
            "organisation_created": False,
            "interest_entity_created": False,
            "match_review_created": False,
            "relationship_created": False,
        }

    async def get_exact_candidate(
        self,
        *,
        contract_snapshot_id: str,
        source_record_sha256: str,
        connection: asyncpg.Connection | None = None,
    ) -> dict[str, object] | None:
        items, _total = await self._load_candidates(
            query=None,
            resource_year=None,
            contract_snapshot_id=contract_snapshot_id,
            source_record_sha256=source_record_sha256,
            limit=1,
            cursor=None,
            connection=connection,
        )
        return items[0] if items else None

    async def _load_candidates(
        self,
        *,
        query: str | None,
        resource_year: int | None,
        contract_snapshot_id: str | None,
        source_record_sha256: str | None,
        limit: int,
        cursor: str | None,
        connection: asyncpg.Connection | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        conditions = [
            "source.publisher = 'BASE_GOV'",
            "source.kind = 'OPEN_DATASET'",
            "source.url LIKE 'https://%'",
        ]
        arguments: list[object] = []
        if query:
            arguments.append(query)
            exact_arg = len(arguments)
            if resource_year is None:
                # Sem ano, a única pesquisa segura e indexável é o identificador exato.
                conditions.append(f"contract.source_id = ${exact_arg}")
            else:
                escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                arguments.append(f"%{escaped}%")
                search_arg = len(arguments)
                conditions.append(
                    "(contract.source_id = "
                    f"${exact_arg} OR contract.object ILIKE ${search_arg} ESCAPE '!' OR EXISTS ("
                    "SELECT 1 FROM base_contract_party_snapshots searched_party "
                    "WHERE searched_party.contract_snapshot_id = contract.id "
                    f"AND searched_party.source_name ILIKE ${search_arg} ESCAPE '!'))"
                )
        if resource_year is not None:
            arguments.append(resource_year)
            conditions.append(f"batch.resource_year = ${len(arguments)}")
        if contract_snapshot_id:
            arguments.append(contract_snapshot_id)
            conditions.append(f"contract.id = ${len(arguments)}")

        database: asyncpg.Pool | asyncpg.Connection = connection or self.pool
        total = int(
            await database.fetchval(
                f"""
                SELECT COUNT(*)::int
                FROM base_contract_snapshots AS contract
                JOIN base_staging_batches AS batch ON batch.id = contract.batch_id
                JOIN source_documents AS source ON source.id = batch.source_document_id
                WHERE {" AND ".join(conditions)}
                """,
                *arguments,
            )
        )
        page_conditions = list(conditions)
        if cursor is not None:
            cursor_year, cursor_published_at, cursor_source_id, cursor_snapshot_id = _decode_cursor(
                cursor
            )
            arguments.extend(
                [cursor_year, cursor_published_at, cursor_source_id, cursor_snapshot_id]
            )
            year_arg = len(arguments) - 3
            published_arg = len(arguments) - 2
            source_arg = len(arguments) - 1
            snapshot_arg = len(arguments)
            if cursor_published_at is None:
                page_conditions.append(
                    f"(batch.resource_year < ${year_arg} OR ("
                    f"batch.resource_year = ${year_arg} AND contract.published_at IS NULL AND ("
                    f'contract.source_id COLLATE "C" > (${source_arg}::text COLLATE "C") OR ('
                    f"contract.source_id = ${source_arg} AND "
                    f'contract.id COLLATE "C" > (${snapshot_arg}::text COLLATE "C")))))'
                )
            else:
                page_conditions.append(
                    f"(batch.resource_year < ${year_arg} OR ("
                    f"batch.resource_year = ${year_arg} AND ("
                    f"contract.published_at < ${published_arg} OR "
                    "contract.published_at IS NULL OR ("
                    f"contract.published_at = ${published_arg} AND ("
                    f'contract.source_id COLLATE "C" > (${source_arg}::text COLLATE "C") OR ('
                    f"contract.source_id = ${source_arg} AND "
                    f'contract.id COLLATE "C" > (${snapshot_arg}::text COLLATE "C")))))))'
                )
        arguments.append(limit)
        limit_arg = len(arguments)
        rows = await database.fetch(
            f"""
            WITH selected AS MATERIALIZED (
                SELECT contract.id AS contract_snapshot_id,
                       contract.source_id, contract.object,
                       contract.procedure::text AS procedure, contract.cpv_code,
                       contract.base_value, contract.contract_value, contract.currency,
                       contract.decision_at, contract.signed_at, contract.published_at,
                       contract.execution_days, contract.direct_official_url,
                       batch.id AS batch_id, batch.resource_year, batch.resource_title,
                       batch.resource_format, batch.parser_version,
                       batch.normalised_sha256, batch.identifier_digests_stored,
                       batch.contract_count, batch.party_count, batch.collected_at,
                       run.status::text AS sync_status,
                       run.finished_at AS sync_finished_at,
                       run.records_read, run.records_written, run.warnings,
                       source.id AS source_document_id, source.title AS source_title,
                       source.url AS source_url,
                       source.retrieved_at AS source_retrieved_at,
                       source.content_sha256 AS source_sha256,
                       source.mime_type AS source_mime_type
                FROM base_contract_snapshots AS contract
                JOIN base_staging_batches AS batch ON batch.id = contract.batch_id
                JOIN sync_runs AS run ON run.id = batch.sync_run_id
                JOIN source_documents AS source ON source.id = batch.source_document_id
                WHERE {" AND ".join(page_conditions)}
                ORDER BY batch.resource_year DESC,
                         contract.published_at DESC NULLS LAST,
                         contract.source_id COLLATE "C", contract.id COLLATE "C"
                LIMIT ${limit_arg}
            )
            SELECT selected.*,
                   archive.storage_backend, archive.byte_size AS archive_byte_size,
                   archive.archived_at, archive.attestation_sha256,
                   counts.actual_contract_count, counts.actual_party_count,
                   COALESCE(parties.items, '[]'::jsonb) AS parties,
                   COALESCE(parties.protected_identifier_count, 0)::int
                       AS protected_identifier_count,
                   catalogue.scope_id, catalogue.scope_sha256,
                   catalogue.scope_source_sha256, catalogue.catalogue_attestation_sha256,
                   catalogue.scope_resource_count, catalogue.actual_scope_resource_count,
                   catalogue.catalogue_sync_status,
                   catalogue.catalogue_sync_finished_at,
                   catalogue.resource_id AS catalogue_resource_id,
                   catalogue.resource_year AS catalogue_resource_year,
                   catalogue.coverage_state, catalogue.catalogue_resource_title,
                   catalogue.catalogue_resource_format,
                   catalogue.versioned_url, catalogue.stable_url,
                   catalogue.source_modified_at, catalogue.resource_byte_size,
                   catalogue.metadata_sha256,
                   editorial_case.id AS case_id,
                   editorial_case.current_state::text AS case_state,
                   editorial_case.revision AS case_revision,
                   editorial_case.origin::text AS case_origin
            FROM selected
            LEFT JOIN LATERAL (
                SELECT candidate.storage_backend, candidate.byte_size,
                       candidate.archived_at, candidate.attestation_sha256
                FROM source_archive_attestations AS candidate
                WHERE candidate.source_document_id = selected.source_document_id
                  AND candidate.content_sha256 = selected.source_sha256
                  AND candidate.retrieval_url = selected.source_url
                  AND candidate.retrieved_at = selected.source_retrieved_at
                ORDER BY candidate.archived_at ASC, candidate.id ASC
                LIMIT 1
            ) AS archive ON TRUE
            JOIN LATERAL (
                SELECT
                    (SELECT COUNT(*)::int FROM base_contract_snapshots counted_contract
                     WHERE counted_contract.batch_id = selected.batch_id)
                        AS actual_contract_count,
                    (SELECT COUNT(*)::int
                     FROM base_contract_party_snapshots counted_party
                     JOIN base_contract_snapshots counted_owner
                       ON counted_owner.id = counted_party.contract_snapshot_id
                     WHERE counted_owner.batch_id = selected.batch_id)
                        AS actual_party_count
            ) AS counts ON TRUE
            LEFT JOIN LATERAL (
                SELECT jsonb_agg(
                           jsonb_build_object(
                               'id', party.id,
                               'ordinal', party.ordinal,
                               'role', party.role::text,
                               'source_name', party.source_name,
                               'protected_identifier_observed',
                                   party.protected_identifier_digest IS NOT NULL
                           ) ORDER BY party.ordinal
                       ) AS items,
                       COUNT(*) FILTER (
                           WHERE party.protected_identifier_digest IS NOT NULL
                       ) AS protected_identifier_count
                FROM base_contract_party_snapshots AS party
                WHERE party.contract_snapshot_id = selected.contract_snapshot_id
            ) AS parties ON TRUE
            LEFT JOIN LATERAL (
                SELECT scope.id AS scope_id, scope.scope_sha256,
                       scope.source_sha256 AS scope_source_sha256,
                       scope.resource_count AS scope_resource_count,
                       scope_archive.attestation_sha256 AS catalogue_attestation_sha256,
                       scope_run.status::text AS catalogue_sync_status,
                       scope_run.finished_at AS catalogue_sync_finished_at,
                       resource.id AS resource_id, resource.resource_year,
                       resource.coverage_state,
                       resource.resource_title AS catalogue_resource_title,
                       resource.resource_format AS catalogue_resource_format,
                       resource.versioned_url, resource.stable_url,
                       resource.source_modified_at,
                       resource.byte_size AS resource_byte_size,
                       resource.metadata_sha256,
                       (SELECT COUNT(*)::int
                        FROM base_contract_catalogue_resources counted_resource
                        WHERE counted_resource.scope_id = scope.id)
                           AS actual_scope_resource_count
                FROM base_contract_catalogue_resources AS resource
                JOIN base_contract_catalogue_scopes AS scope ON scope.id = resource.scope_id
                JOIN sync_runs AS scope_run ON scope_run.id = scope.sync_run_id
                JOIN source_documents AS scope_source
                  ON scope_source.id = scope.source_document_id
                JOIN LATERAL (
                    SELECT candidate.attestation_sha256
                    FROM source_archive_attestations AS candidate
                    WHERE candidate.source_document_id = scope_source.id
                      AND candidate.content_sha256 = scope_source.content_sha256
                      AND candidate.retrieval_url = scope_source.url
                      AND candidate.retrieved_at = scope_source.retrieved_at
                    ORDER BY candidate.archived_at ASC, candidate.id ASC
                    LIMIT 1
                ) AS scope_archive ON TRUE
                WHERE resource.resource_year = selected.resource_year
                  AND selected.source_url IN (resource.versioned_url, resource.stable_url)
                ORDER BY scope.retrieved_at DESC, scope.id DESC
                LIMIT 1
            ) AS catalogue ON TRUE
            LEFT JOIN editorial_cases AS editorial_case
              ON editorial_case.kind = 'PUBLIC_CONTRACT'::"EditorialCaseKind"
             AND editorial_case.subject_type = '{_SUBJECT_TYPE}'
             AND editorial_case.subject_id = selected.contract_snapshot_id
             AND editorial_case.source_document_id = selected.source_document_id
            ORDER BY selected.resource_year DESC,
                     selected.published_at DESC NULLS LAST,
                     selected.source_id COLLATE "C",
                     selected.contract_snapshot_id COLLATE "C"
            """,
            *arguments,
        )
        candidates = [self._candidate(row) for row in rows]
        if source_record_sha256 is not None:
            candidates = [
                candidate
                for candidate in candidates
                if candidate["source_record_sha256"] == source_record_sha256
            ]
        return candidates, total

    @classmethod
    def _candidate(cls, row: Mapping[str, Any]) -> dict[str, object]:
        blocked: list[str] = []
        parties, parties_valid = _json_object_list(row["parties"])
        warnings, warnings_valid = _json_string_list(row["warnings"])
        if not parties_valid:
            blocked.append("A representação normalizada das partes está indisponível ou inválida.")
        if not warnings_valid:
            blocked.append("As limitações registadas pelo SyncRun não têm formato válido.")
        safe_parties: list[dict[str, object]] = []
        for party in parties:
            source_name = party.get("source_name")
            party_id = party.get("id")
            ordinal = party.get("ordinal")
            role = party.get("role")
            identifier_observed = party.get("protected_identifier_observed")
            party_shape_valid = (
                isinstance(party_id, str)
                and isinstance(ordinal, int)
                and ordinal >= 0
                and role in {"CONTRACTING_AUTHORITY", "CONTRACTOR", "CO_CONTRACTOR"}
                and isinstance(source_name, str)
                and bool(source_name.strip())
                and isinstance(identifier_observed, bool)
            )
            if not party_shape_valid:
                blocked.append("Uma parte do contrato tem uma representação inválida.")
                continue
            assert isinstance(source_name, str)
            if _contains_unsafe_source_text(source_name):
                blocked.append("Uma designação contém um identificador fiscal potencial.")
                source_name = "Dados indisponíveis: texto protegido"
            safe_parties.append({**party, "source_name": source_name})
        parties = safe_parties
        protected_identifier_count = int(row["protected_identifier_count"])
        if protected_identifier_count != sum(
            party["protected_identifier_observed"] is True for party in parties
        ):
            blocked.append("A contagem de identificadores protegidos diverge das partes.")
        object_text = str(row["object"])
        if _contains_unsafe_source_text(object_text):
            blocked.append("O objeto contém um identificador fiscal potencial.")
            object_text = "Dados indisponíveis: texto protegido"
        direct_official_url = row["direct_official_url"]
        if direct_official_url is not None and _contains_unsafe_source_text(
            str(direct_official_url)
        ):
            blocked.append("A ligação individual contém um identificador fiscal potencial.")
            direct_official_url = None
        source_record = cls._source_record(row, parties)
        source_record_sha256 = hashlib.sha256(
            _canonical_json(source_record).encode("utf-8")
        ).hexdigest()

        if row["sync_status"] not in {"SUCCEEDED", "PARTIAL"} or row["sync_finished_at"] is None:
            blocked.append("O lote normalizado não terminou de forma verificável.")
        if any(warning.startswith("Amostra limitada") for warning in warnings):
            blocked.append("A recolha foi truncada a uma amostra e não pode originar propostas.")
        if int(row["records_read"]) != int(row["contract_count"]):
            blocked.append("A contagem lida pelo SyncRun não coincide com o lote normalizado.")
        if int(row["records_written"]) != int(row["contract_count"]) + int(row["party_count"]):
            blocked.append("A contagem escrita pelo SyncRun não coincide com contratos e partes.")
        if int(row["actual_contract_count"]) != int(row["contract_count"]):
            blocked.append("O lote não contém todos os contratos declarados.")
        if int(row["actual_party_count"]) != int(row["party_count"]):
            blocked.append("O lote não contém todas as partes declaradas.")
        if row["storage_backend"] is None:
            blocked.append("O ficheiro anual BASE não possui arquivo privado atestado.")
        if row["source_retrieved_at"] != row["collected_at"]:
            blocked.append("A data de recolha do lote diverge da fonte oficial.")
        if row["resource_format"] != "ZIP":
            blocked.append("O lote não corresponde ao recurso ZIP anual do catálogo revisto.")
        if row["scope_id"] is None:
            blocked.append("O ano e URL do lote não constam do catálogo temporal BASE atestado.")
        else:
            if (
                row["catalogue_sync_status"] != "SUCCEEDED"
                or row["catalogue_sync_finished_at"] is None
            ):
                blocked.append("A recolha do catálogo temporal BASE não terminou com sucesso.")
            if int(row["scope_resource_count"]) != int(row["actual_scope_resource_count"]):
                blocked.append("A fotografia do catálogo temporal BASE está incompleta.")
            if row["catalogue_resource_year"] != row["resource_year"]:
                blocked.append("O ano do recurso catalogado diverge do lote.")
            if row["coverage_state"] != "HISTORICAL_CLOSED_YEAR":
                blocked.append("O ano corrente é provisório e ainda não pode ser proposto.")
            if row["catalogue_resource_format"] != "ZIP":
                blocked.append("O formato catalogado deixou de ser ZIP.")
            if row["storage_backend"] is not None and int(row["archive_byte_size"]) != int(
                row["resource_byte_size"]
            ):
                blocked.append("O tamanho do arquivo diverge do recurso anual catalogado.")
            if (
                row["source_modified_at"] is not None
                and row["source_retrieved_at"] < row["source_modified_at"]
            ):
                blocked.append("O arquivo foi recolhido antes da modificação declarada do recurso.")
            if (
                str(row["catalogue_resource_title"]).casefold()
                != str(row["resource_title"]).casefold()
            ):
                blocked.append("O título do recurso anual diverge do catálogo atestado.")
        if not str(row["source_id"]).strip():
            blocked.append("O identificador oficial do contrato está indisponível.")
        if row["cpv_code"] is not None and not _CPV_CODE.fullmatch(str(row["cpv_code"])):
            blocked.append("O código CPV não tem o formato oficial esperado.")

        return {
            "contract_snapshot_id": str(row["contract_snapshot_id"]),
            "source_document_id": str(row["source_document_id"]),
            "official_contract_id": str(row["source_id"]),
            "object": object_text,
            "procedure": str(row["procedure"]),
            "cpv_code": row["cpv_code"],
            "base_value": _decimal(row["base_value"]),
            "contract_value": _decimal(row["contract_value"]),
            "currency": str(row["currency"]),
            "decision_at": _iso(row["decision_at"]),
            "signed_at": _iso(row["signed_at"]),
            "published_at": _iso(row["published_at"]),
            "execution_days": row["execution_days"],
            "direct_official_url": direct_official_url,
            "parties": parties,
            "protected_identifier_count": protected_identifier_count,
            "protected_identifier_exposed": False,
            "source_record_sha256": source_record_sha256,
            "batch": {
                "id": str(row["batch_id"]),
                "resource_year": int(row["resource_year"]),
                "resource_title": str(row["resource_title"]),
                "parser_version": str(row["parser_version"]),
                "normalised_sha256": str(row["normalised_sha256"]),
                "contract_count": int(row["contract_count"]),
                "party_count": int(row["party_count"]),
                "actual_contract_count": int(row["actual_contract_count"]),
                "actual_party_count": int(row["actual_party_count"]),
                "collected_at": _iso(row["collected_at"]),
                "sync_status": str(row["sync_status"]),
                "sync_finished_at": _iso(row["sync_finished_at"]),
                "records_read": int(row["records_read"]),
                "records_written": int(row["records_written"]),
                "warnings": warnings,
                "counts_match": (
                    int(row["actual_contract_count"]) == int(row["contract_count"])
                    and int(row["actual_party_count"]) == int(row["party_count"])
                    and int(row["records_read"]) == int(row["contract_count"])
                    and int(row["records_written"])
                    == int(row["contract_count"]) + int(row["party_count"])
                ),
            },
            "source": {
                "title": str(row["source_title"]),
                "url": str(row["source_url"]),
                "retrieved_at": _iso(row["source_retrieved_at"]),
                "content_sha256": str(row["source_sha256"]),
                "mime_type": row["source_mime_type"],
            },
            "archive": (
                {
                    "storage_backend": str(row["storage_backend"]),
                    "byte_size": int(row["archive_byte_size"]),
                    "archived_at": _iso(row["archived_at"]),
                    "attestation_sha256": str(row["attestation_sha256"]),
                }
                if row["storage_backend"] is not None
                else None
            ),
            "catalogue": (
                {
                    "scope_id": str(row["scope_id"]),
                    "scope_sha256": str(row["scope_sha256"]),
                    "source_sha256": str(row["scope_source_sha256"]),
                    "archive_attestation_sha256": str(row["catalogue_attestation_sha256"]),
                    "resource_id": str(row["catalogue_resource_id"]),
                    "resource_year": int(row["catalogue_resource_year"]),
                    "coverage_state": str(row["coverage_state"]),
                    "versioned_url": str(row["versioned_url"]),
                    "stable_url": str(row["stable_url"]),
                    "source_modified_at": _iso(row["source_modified_at"]),
                    "byte_size": int(row["resource_byte_size"]),
                    "metadata_sha256": str(row["metadata_sha256"]),
                }
                if row["scope_id"] is not None
                else None
            ),
            "existing_case": _case_reference(row),
            "proposal_eligible": not blocked,
            "blocked_reasons": blocked,
            "coverage_claim": "SPECIFIC_SOURCE_RECORD_ONLY",
            "annual_source_completeness_claimed": False,
            "public_contract_creation_allowed": False,
            "organisation_creation_allowed": False,
            "identity_or_name_matching_allowed": False,
            "relationship_creation_allowed": False,
            "publication_allowed": False,
        }

    @staticmethod
    def _source_record(
        row: Mapping[str, Any], parties: list[dict[str, object]]
    ) -> dict[str, object]:
        return {
            "schema_version": _SOURCE_RECORD_SCHEMA,
            "contract_snapshot_id": str(row["contract_snapshot_id"]),
            "official_contract_id": str(row["source_id"]),
            "object": str(row["object"]),
            "procedure": str(row["procedure"]),
            "cpv_code": row["cpv_code"],
            "base_value": _decimal(row["base_value"]),
            "contract_value": _decimal(row["contract_value"]),
            "currency": str(row["currency"]),
            "decision_at": _iso(row["decision_at"]),
            "signed_at": _iso(row["signed_at"]),
            "published_at": _iso(row["published_at"]),
            "execution_days": row["execution_days"],
            "direct_official_url": row["direct_official_url"],
            "parties": parties,
            "batch": {
                "id": str(row["batch_id"]),
                "resource_year": int(row["resource_year"]),
                "normalised_sha256": str(row["normalised_sha256"]),
            },
            "source": {
                "id": str(row["source_document_id"]),
                "content_sha256": str(row["source_sha256"]),
            },
            "catalogue": (
                {
                    "scope_id": str(row["scope_id"]),
                    "scope_sha256": str(row["scope_sha256"]),
                    "resource_id": str(row["catalogue_resource_id"]),
                    "metadata_sha256": str(row["metadata_sha256"]),
                    "coverage_state": str(row["coverage_state"]),
                }
                if row["scope_id"] is not None
                else None
            ),
        }

    @staticmethod
    def _normalized_proposal(candidate: Mapping[str, Any]) -> dict[str, object]:
        source = candidate["source"]
        archive = candidate["archive"]
        batch = candidate["batch"]
        catalogue = candidate["catalogue"]
        assert isinstance(source, Mapping)
        assert isinstance(archive, Mapping)
        assert isinstance(batch, Mapping)
        assert isinstance(catalogue, Mapping)
        return {
            "schema_version": _PROPOSAL_SCHEMA,
            "candidate": {
                "contract_snapshot_id": candidate["contract_snapshot_id"],
                "official_contract_id": candidate["official_contract_id"],
                "object": candidate["object"],
                "procedure": candidate["procedure"],
                "cpv_code": candidate["cpv_code"],
                "base_value": candidate["base_value"],
                "contract_value": candidate["contract_value"],
                "currency": candidate["currency"],
                "decision_at": candidate["decision_at"],
                "signed_at": candidate["signed_at"],
                "published_at": candidate["published_at"],
                "execution_days": candidate["execution_days"],
                "direct_official_url": candidate["direct_official_url"],
                "parties": candidate["parties"],
                "protected_identifier_count": candidate["protected_identifier_count"],
                "source_record_sha256": candidate["source_record_sha256"],
            },
            "annual_batch": dict(batch),
            "source": dict(source),
            "archive": dict(archive),
            "catalogue": dict(catalogue),
            "review_constraints": {
                "private_only": True,
                "coverage_claim": "SPECIFIC_SOURCE_RECORD_ONLY",
                "annual_source_completeness_claimed": False,
                "exact_official_contract_id_only": True,
                "party_names_are_source_text_not_identity": True,
                "protected_identifier_exposed": False,
                "name_or_fuzzy_matching_allowed": False,
                "organisations_require_independent_official_sources": True,
                "public_contract_created": False,
                "interest_entities_created": False,
                "match_reviews_created": False,
                "relationships_created": False,
                "publication_performed": False,
            },
        }
