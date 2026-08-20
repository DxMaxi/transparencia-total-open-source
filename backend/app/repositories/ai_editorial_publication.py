"""Publicação e leitura pública fail-closed de explicações DRE revistas."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
from pydantic import ValidationError

from app.models.api import CitizenSummary
from app.models.editorial import (
    AiEditorialPublicationRequest,
    AiEditorialWithdrawalRequest,
    EditorialAction,
    EditorialCaseKind,
    EditorialOrigin,
    EditorialState,
    ParliamentWithdrawalReason,
    StaffRole,
    StaffSession,
)
from app.repositories.ai_editorial import AiDreSnapshot, _snapshot_from_row
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialRepository,
    EditorialSourceError,
)
from app.services.ai_editorial import AI_DRE_CONTRACT_VERSION, validate_summary_against_source

AI_PUBLIC_TARGET_TYPE = "DRE_AI_EXPLANATION"
AI_PUBLIC_AUDIT_TYPE = "AI_DRE_EXPLANATION"
AI_PUBLIC_CONTRACT_VERSION = "v5.ai.publication.v1"
AI_PUBLIC_LABEL = "Explicação gerada por IA — revista por humano"
AI_PUBLIC_LIMITATIONS = [
    "A IA não é fonte: a prova factual é o documento oficial do Diário da República.",
    "Esta explicação não prevê efeitos futuros nem substitui aconselhamento jurídico.",
    "A explicação não recomenda partidos, candidatos ou qualquer sentido de voto.",
]
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_ID = re.compile(r"^dre-[0-9a-f]{64}$")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reference_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_json_object(value: object) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds") + "Z"


def _publication_event_sha256(
    *,
    event_id: str,
    case_id: str,
    version_id: str,
    action: str,
    target_type: str,
    target_id: str,
    rationale: str,
    actor_id: str,
    actor_alias: str,
    created_at: datetime,
) -> str:
    return _sha256_json(
        {
            "id": event_id,
            "case_id": case_id,
            "version_id": version_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "rationale": rationale,
            "actor_id": actor_id,
            "actor_alias": actor_alias,
            "created_at": _iso_timestamp(created_at),
        }
    )


def _public_id(snapshot: AiDreSnapshot) -> str:
    return f"dre-{snapshot.source_content_sha256}"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _digest(value: object) -> str | None:
    return value if isinstance(value, str) and _DIGEST.fullmatch(value) else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _proposal_projection(
    *,
    case: dict[str, Any],
    snapshot: AiDreSnapshot,
) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
    """Reconstrói apenas campos publicáveis; qualquer divergência bloqueia tudo."""

    blockers: list[dict[str, str]] = []

    def block(code: str, detail: str) -> None:
        blockers.append({"code": code, "detail": detail})

    normalized = _as_json_object(case.get("normalized_json"))
    editorial_sha256 = _digest(case.get("editorial_sha256"))
    if normalized is None or editorial_sha256 is None:
        block("EDITORIAL_VERSION_INVALID", "A versão editorial atual não é verificável.")
        return None, blockers
    if _sha256_json(normalized) != editorial_sha256:
        block("EDITORIAL_HASH_MISMATCH", "O SHA-256 da versão editorial deixou de coincidir.")

    source = _as_json_object(normalized.get("source"))
    generation = _as_json_object(normalized.get("generation"))
    summary_data = _as_json_object(normalized.get("summary"))
    if source is None or generation is None or summary_data is None:
        block("AI_CONTRACT_INVALID", "A estrutura da proposta de IA está incompleta.")
        return None, blockers

    try:
        summary = CitizenSummary.model_validate(summary_data)
    except ValidationError:
        block("AI_SUMMARY_INVALID", "O resumo não cumpre o contrato estruturado publicado.")
        return None, blockers

    expected_source = {
        "publisher": "DRE",
        "source_document_reference_sha256": _reference_sha256(snapshot.source_document_id),
        "snapshot_reference_sha256": _reference_sha256(snapshot.snapshot_id),
        "official_identifier": snapshot.official_identifier,
        "content_sha256": snapshot.source_content_sha256,
        "normalised_text_sha256": snapshot.normalised_text_sha256,
        "parser_version": snapshot.parser_version,
        "archive_attestation_reference_sha256": _reference_sha256(snapshot.archive_attestation_id),
        "archive_attestation_sha256": snapshot.archive_attestation_sha256,
        "url_sha256": _reference_sha256(snapshot.source_url),
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            block("SOURCE_PROOF_MISMATCH", f"A prova oficial não coincide no campo {key}.")

    retrieved_at = _text(source.get("retrieved_at"))
    published_at = source.get("published_at")
    if retrieved_at != snapshot.retrieved_at.isoformat() or published_at != (
        snapshot.published_at.isoformat() if snapshot.published_at is not None else None
    ):
        block("SOURCE_DATE_MISMATCH", "As datas da fonte não coincidem com o snapshot atestado.")

    provider = _text(generation.get("provider"))
    model = _text(generation.get("model"))
    prompt_version = _text(generation.get("prompt_version"))
    prompt_sha256 = _digest(generation.get("prompt_sha256"))
    input_sha256 = _digest(generation.get("input_sha256"))
    output_sha256 = _digest(generation.get("output_sha256"))
    generated_at = _text(generation.get("generated_at"))
    source_characters = _integer(generation.get("source_characters"))
    processed_characters = _integer(generation.get("processed_characters"))
    source_truncated = generation.get("source_truncated")
    if not all((provider, model, prompt_version, prompt_sha256, input_sha256, output_sha256)):
        block("GENERATION_PROOF_INVALID", "A prova técnica da geração está incompleta.")
    if generated_at is None:
        block("GENERATION_DATE_INVALID", "A data da geração está indisponível.")
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            block("GENERATION_DATE_INVALID", "A data da geração não é válida.")

    if source_characters != snapshot.source_characters:
        block("SOURCE_LENGTH_MISMATCH", "O tamanho do texto oficial deixou de coincidir.")
    if (
        processed_characters is None
        or processed_characters < 1
        or processed_characters > snapshot.source_characters
        or not isinstance(source_truncated, bool)
        or source_truncated != (processed_characters < snapshot.source_characters)
    ):
        block("PROCESSED_RANGE_INVALID", "O intervalo de texto processado não é verificável.")
    if generation.get("provider_store") is not False:
        block("PROVIDER_STORAGE_UNCONFIRMED", "A não retenção pelo fornecedor não está registada.")

    if provider and model and prompt_version and prompt_sha256 and input_sha256:
        expected_input = _sha256_json(
            {
                "snapshot_id": snapshot.snapshot_id,
                "source_document_id": snapshot.source_document_id,
                "source_content_sha256": snapshot.source_content_sha256,
                "normalised_text_sha256": snapshot.normalised_text_sha256,
                "provider": provider,
                "model": model,
                "prompt_version": prompt_version,
                "prompt_sha256": prompt_sha256,
            }
        )
        if not secrets.compare_digest(input_sha256, expected_input):
            block("INPUT_HASH_MISMATCH", "O manifesto entregue ao modelo não coincide.")
    if output_sha256 and not secrets.compare_digest(
        output_sha256,
        _sha256_json(summary.model_dump(mode="json")),
    ):
        block("OUTPUT_HASH_MISMATCH", "O resumo atual não coincide com a saída registada.")

    try:
        abstained = validate_summary_against_source(summary, snapshot.extracted_text)
    except EditorialConflictError as exc:
        block("SOURCE_ANCHOR_INVALID", str(exc))
        abstained = False
    if normalized.get("abstained") is not abstained:
        block("ABSTENTION_MISMATCH", "O estado de abstenção não coincide com o conteúdo.")
    if (
        normalized.get("contract_version") != AI_DRE_CONTRACT_VERSION
        or normalized.get("proposal_type") != "DRE_CITIZEN_SUMMARY"
        or normalized.get("requires_human_review") is not True
        or normalized.get("publication_eligible") is not False
        or normalized.get("ai_is_source") is not False
    ):
        block("AI_GOVERNANCE_MISMATCH", "A versão não conserva as salvaguardas obrigatórias.")

    if blockers:
        return None, blockers

    assert provider is not None
    assert model is not None
    assert prompt_version is not None
    assert prompt_sha256 is not None
    assert input_sha256 is not None
    assert output_sha256 is not None
    assert generated_at is not None
    assert source_characters is not None
    assert processed_characters is not None
    assert isinstance(source_truncated, bool)
    public_id = _public_id(snapshot)
    projection: dict[str, object] = {
        "schema_version": AI_PUBLIC_CONTRACT_VERSION,
        "id": public_id,
        "content_kind": "AI_EXPLANATION",
        "label": AI_PUBLIC_LABEL,
        "ai_generated": True,
        "ai_is_source": False,
        "human_review_required": True,
        "not_prediction": True,
        "no_voting_recommendation": True,
        "abstained": abstained,
        "summary": summary.model_dump(mode="json"),
        "source": {
            "publisher": "DRE",
            "label": "Diário da República — fonte oficial",
            "title": snapshot.title,
            "official_identifier": snapshot.official_identifier,
            "url": snapshot.source_url,
            "retrieved_at": snapshot.retrieved_at.isoformat(),
            "published_at": (
                snapshot.published_at.isoformat() if snapshot.published_at is not None else None
            ),
            "content_sha256": snapshot.source_content_sha256,
            "normalised_text_sha256": snapshot.normalised_text_sha256,
        },
        "generation": {
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "prompt_sha256": prompt_sha256,
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
            "generated_at": generated_at,
            "source_characters": source_characters,
            "processed_characters": processed_characters,
            "source_truncated": source_truncated,
            "provider_store": False,
        },
        "editorial_version_sha256": editorial_sha256,
        "limitations": AI_PUBLIC_LIMITATIONS,
    }
    return projection, blockers


def _publication_proof(projection: dict[str, object]) -> str:
    return _sha256_json(projection)


def _public_effect(public_id: str) -> dict[str, str]:
    return {
        "kind": "DATA_UNAVAILABLE",
        "public_id": public_id,
        "message": (
            "Explicação retirada da consulta ativa. A decisão, a fonte e os hashes "
            "permanecem no histórico público."
        ),
    }


async def _case_core(
    connection: asyncpg.Connection,
    *,
    case_id: str,
    lock: bool,
    version_id: str | None = None,
) -> dict[str, Any]:
    version_clause = (
        "version.id = $2" if version_id is not None else "version.id = c.current_version_id"
    )
    query = f"""
        SELECT c.id, c.kind::text, c.subject_type, c.subject_id,
               c.source_document_id, c.origin::text, c.current_version_id,
               c.current_state::text, c.revision, c.created_at, c.updated_at,
               version.id AS version_id, version.version_number,
               version.normalized_json, version.normalized_sha256 AS editorial_sha256,
               version.origin::text AS version_origin, version.created_at AS version_created_at,
               source.publisher::text AS source_publisher,
               source.kind::text AS source_kind, source.url AS source_url,
               source.content_sha256 AS source_sha256
        FROM editorial_cases c
        JOIN editorial_versions version ON {version_clause} AND version.case_id = c.id
        JOIN source_documents source ON source.id = c.source_document_id
        WHERE c.id = $1
        {"FOR UPDATE OF c" if lock else ""}
    """
    arguments: tuple[object, ...] = (case_id, version_id) if version_id is not None else (case_id,)
    row = await connection.fetchrow(query, *arguments)
    if row is None:
        raise EditorialNotFoundError("Processo editorial não encontrado")
    result = dict(row)
    if (
        str(result["kind"]) != EditorialCaseKind.AI_EXPLANATION.value
        or str(result["subject_type"]) != "DRE_DOCUMENT_SNAPSHOT"
        or str(result["origin"]) != EditorialOrigin.AI.value
        or str(result["source_publisher"]) != "DRE"
        or str(result["source_kind"]) not in {"LAW", "REGULATION"}
    ):
        raise EditorialConflictError("O processo não pertence à publicação DRE de IA")
    return result


async def _snapshot_for_version(
    connection: asyncpg.Connection,
    *,
    case: dict[str, Any],
) -> AiDreSnapshot:
    normalized = _as_json_object(case.get("normalized_json"))
    source_manifest = _as_json_object(normalized.get("source")) if normalized else None
    reference = source_manifest.get("snapshot_reference_sha256") if source_manifest else None
    if not isinstance(reference, str) or not _DIGEST.fullmatch(reference):
        raise EditorialSourceError("A versão não conserva uma referência válida do snapshot DRE")
    rows = await connection.fetch(
        """
        SELECT snapshot.id AS snapshot_id, snapshot.official_identifier,
               snapshot.title, snapshot.published_at, snapshot.collected_at,
               snapshot.parser_version, snapshot.normalised_text_sha256,
               snapshot.extracted_text, snapshot.text_length,
               source.id AS source_document_id, source.url AS source_url,
               source.retrieved_at, source.content_sha256 AS source_content_sha256,
               archive.id AS archive_attestation_id, archive.storage_backend,
               archive.storage_key, archive.content_sha256 AS archive_content_sha256,
               archive.byte_size, archive.mime_type AS archive_mime_type,
               archive.retrieval_url, archive.retrieved_at AS archive_retrieved_at,
               archive.archived_at, archive.archived_by, archive.attestation_sha256
        FROM dre_document_snapshots snapshot
        JOIN source_documents source ON source.id = snapshot.source_document_id
        JOIN sync_runs run ON run.id = snapshot.sync_run_id
        JOIN LATERAL (
            SELECT candidate.id, candidate.storage_backend, candidate.storage_key,
                   candidate.content_sha256, candidate.byte_size, candidate.mime_type,
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
        WHERE snapshot.source_document_id = $1
          AND source.publisher = 'DRE'
          AND source.kind IN ('LAW', 'REGULATION')
          AND source.url LIKE 'https://%'
          AND run.status = 'SUCCEEDED'
          AND run.finished_at IS NOT NULL
        ORDER BY snapshot.collected_at DESC, snapshot.id DESC
        """,
        str(case["source_document_id"]),
    )
    matches: list[AiDreSnapshot] = []
    for row in rows:
        if _reference_sha256(str(row["snapshot_id"])) != reference:
            continue
        matches.append(_snapshot_from_row(row))
    if len(matches) != 1:
        raise EditorialSourceError("A versão não resolve um único snapshot DRE atestado")
    return matches[0]


async def _events(
    connection: asyncpg.Connection,
    *,
    case_id: str,
    version_id: str,
    public_id: str,
) -> dict[str, dict[str, Any] | None]:
    rows = await connection.fetch(
        """
        SELECT id, case_id, version_id, action::text, target_type, target_id,
               rationale, actor_id, actor_alias, event_sha256, created_at
        FROM editorial_publication_events
        WHERE case_id = $1 AND version_id = $2
          AND target_type = $3 AND target_id = $4
        ORDER BY created_at, id
        """,
        case_id,
        version_id,
        AI_PUBLIC_TARGET_TYPE,
        public_id,
    )
    by_action: dict[str, dict[str, Any] | None] = {"PUBLISH": None, "WITHDRAW": None}
    for row in rows:
        action = str(row["action"])
        if action in by_action:
            if by_action[action] is not None:
                raise EditorialSourceError("Existem eventos públicos duplicados para a versão")
            by_action[action] = dict(row)
    return by_action


def _event_is_valid(event: dict[str, Any] | None) -> bool:
    if event is None:
        return False
    expected = _publication_event_sha256(
        event_id=str(event["id"]),
        case_id=str(event["case_id"]),
        version_id=str(event["version_id"]),
        action=str(event["action"]),
        target_type=str(event["target_type"]),
        target_id=str(event["target_id"]),
        rationale=str(event["rationale"]),
        actor_id=str(event["actor_id"]),
        actor_alias=str(event["actor_alias"]),
        created_at=event["created_at"],
    )
    return secrets.compare_digest(expected, str(event["event_sha256"]))


async def _latest_public_review(
    connection: asyncpg.Connection,
    *,
    public_id: str,
    source_document_id: str,
) -> dict[str, Any] | None:
    row = await connection.fetchrow(
        """
        SELECT id, publishable, reviewed_by, reviewed_at
        FROM data_publication_reviews
        WHERE entity_type = $1 AND entity_id = $2 AND source_document_id = $3
        ORDER BY reviewed_at DESC, id DESC
        LIMIT 1
        """,
        AI_PUBLIC_AUDIT_TYPE,
        public_id,
        source_document_id,
    )
    return dict(row) if row is not None else None


async def _public_review_by_reference(
    connection: asyncpg.Connection,
    *,
    public_id: str,
    source_document_id: str,
    reference_sha256: str,
) -> dict[str, Any] | None:
    """Resolve uma revisão sem publicar o respetivo identificador interno."""

    if not _DIGEST.fullmatch(reference_sha256):
        return None
    rows = await connection.fetch(
        """
        SELECT id, publishable, reviewed_by, reviewed_at
        FROM data_publication_reviews
        WHERE entity_type = $1 AND entity_id = $2 AND source_document_id = $3
        ORDER BY reviewed_at, id
        """,
        AI_PUBLIC_AUDIT_TYPE,
        public_id,
        source_document_id,
    )
    matches = [
        dict(row)
        for row in rows
        if secrets.compare_digest(_reference_sha256(str(row["id"])), reference_sha256)
    ]
    return matches[0] if len(matches) == 1 else None


async def _publication_audit(
    connection: asyncpg.Connection,
    *,
    public_id: str,
    publication_event_sha256: str,
) -> dict[str, Any] | None:
    row = await connection.fetchrow(
        """
        SELECT id, action, actor_alias, before_json, after_json, reason, created_at
        FROM audit_events
        WHERE entity_type = $1 AND entity_id = $2 AND action = 'PUBLISHED'
          AND after_json ->> 'publication_event_sha256' = $3
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        AI_PUBLIC_AUDIT_TYPE,
        public_id,
        publication_event_sha256,
    )
    return dict(row) if row is not None else None


def _audit_payload(
    *,
    action: str,
    case_id: str,
    version_id: str,
    projection: dict[str, object],
    publication_proof_sha256: str,
    publication_event_id: str,
    publication_event_sha256: str,
    public_review_id: str,
    reason_category: str | None = None,
    public_effect: dict[str, str] | None = None,
) -> dict[str, object]:
    source = projection["source"]
    generation = projection["generation"]
    assert isinstance(source, dict)
    assert isinstance(generation, dict)
    payload: dict[str, object] = {
        "schema_version": AI_PUBLIC_CONTRACT_VERSION,
        "publication_action": action,
        "public_id": projection["id"],
        "case_reference_sha256": _reference_sha256(case_id),
        "version_reference_sha256": _reference_sha256(version_id),
        "editorial_version_sha256": projection["editorial_version_sha256"],
        "publication_proof_sha256": publication_proof_sha256,
        "publication_event_reference_sha256": _reference_sha256(publication_event_id),
        "publication_event_sha256": publication_event_sha256,
        "public_review_reference_sha256": _reference_sha256(public_review_id),
        "label": AI_PUBLIC_LABEL,
        "source": source,
        "output_sha256": generation["output_sha256"],
        "prompt_sha256": generation["prompt_sha256"],
    }
    if reason_category is not None:
        payload["withdrawal_reason_category"] = reason_category
    if public_effect is not None:
        payload["public_effect"] = public_effect
        payload["public_effect_sha256"] = _sha256_json(public_effect)
    return payload


def _audit_matches(
    *,
    audit: dict[str, Any] | None,
    review: dict[str, Any] | None,
    event: dict[str, Any] | None,
    expected_after: dict[str, object],
    expected_publishable: bool = True,
) -> bool:
    if audit is None or review is None or event is None:
        return False
    after = _as_json_object(audit.get("after_json"))
    return bool(
        after == expected_after
        and review.get("publishable") is expected_publishable
        and str(review.get("reviewed_by")) == str(event.get("actor_alias"))
        and review.get("reviewed_at") == event.get("created_at")
        and audit.get("created_at") == event.get("created_at")
        and str(audit.get("actor_alias")) == str(event.get("actor_alias"))
        and isinstance(audit.get("reason"), str)
        and len(str(audit["reason"]).strip()) >= 20
        and _reference_sha256(str(review["id"])) == expected_after["public_review_reference_sha256"]
    )


class AiEditorialPublicationRepository:
    """Liga uma aprovação humana à projeção pública, sem tabela de resumo mutável."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.editorial = EditorialRepository(pool)

    async def inspect(self, *, case_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            case = await _case_core(connection, case_id=case_id, lock=False)
            snapshot = await _snapshot_for_version(connection, case=case)
            return await self._publication_preview(
                connection,
                case=case,
                snapshot=snapshot,
            )

    async def inspect_withdrawal(self, *, case_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            case = await _case_core(connection, case_id=case_id, lock=False)
            snapshot = await _snapshot_for_version(connection, case=case)
            return await self._withdrawal_preview(
                connection,
                case=case,
                snapshot=snapshot,
            )

    async def _publication_preview(
        self,
        connection: asyncpg.Connection,
        *,
        case: dict[str, Any],
        snapshot: AiDreSnapshot,
    ) -> dict[str, object]:
        projection, blockers = _proposal_projection(case=case, snapshot=snapshot)
        public_id = _public_id(snapshot)
        proof = _publication_proof(projection) if projection is not None else "0" * 64
        events = await _events(
            connection,
            case_id=str(case["id"]),
            version_id=str(case["version_id"]),
            public_id=public_id,
        )
        duplicate_count = await connection.fetchval(
            """
            SELECT COUNT(DISTINCT candidate.id)
            FROM editorial_cases candidate
            JOIN editorial_publication_events event
              ON event.case_id = candidate.id
             AND event.version_id = candidate.current_version_id
             AND event.action = 'PUBLISH'
             AND event.target_type = $1
             AND event.target_id = $2
            WHERE candidate.current_state = 'PUBLISHED'
              AND candidate.id <> $3
            """,
            AI_PUBLIC_TARGET_TYPE,
            public_id,
            str(case["id"]),
        )
        if str(case["current_state"]) != EditorialState.APPROVED.value:
            blockers.append(
                {"code": "CASE_NOT_APPROVED", "detail": "O processo não está aprovado em privado."}
            )
        if events["PUBLISH"] is not None:
            blockers.append(
                {"code": "VERSION_ALREADY_PUBLISHED", "detail": "A versão já possui publicação."}
            )
        if int(duplicate_count or 0) > 0:
            blockers.append(
                {
                    "code": "PUBLIC_ID_CONFLICT",
                    "detail": "Outra explicação ativa representa o mesmo documento oficial.",
                }
            )
        generation = projection.get("generation") if projection else None
        source = projection.get("source") if projection else None
        return {
            "case_id": str(case["id"]),
            "case_state": str(case["current_state"]),
            "revision": int(case["revision"]),
            "public_id": public_id,
            "source": source,
            "generation": generation,
            "editorial_version_sha256": str(case["editorial_sha256"]),
            "output_sha256": (
                str(generation["output_sha256"]) if isinstance(generation, dict) else "0" * 64
            ),
            "publication_proof_sha256": proof,
            "public_projection": projection,
            "eligible": not blockers,
            "blockers": blockers,
            "automatic_publication": False,
            "publication_rule": (
                "Só um administrador com MFA pode publicar a versão exata depois de confirmar "
                "fonte, rótulo de IA, ausência de previsão e ausência de recomendação eleitoral."
            ),
        }

    async def _withdrawal_preview(
        self,
        connection: asyncpg.Connection,
        *,
        case: dict[str, Any],
        snapshot: AiDreSnapshot,
    ) -> dict[str, object]:
        projection, blockers = _proposal_projection(case=case, snapshot=snapshot)
        public_id = _public_id(snapshot)
        proof = _publication_proof(projection) if projection is not None else "0" * 64
        events = await _events(
            connection,
            case_id=str(case["id"]),
            version_id=str(case["version_id"]),
            public_id=public_id,
        )
        publication = events["PUBLISH"]
        if str(case["current_state"]) != EditorialState.PUBLISHED.value:
            blockers.append(
                {"code": "CASE_NOT_PUBLISHED", "detail": "O processo não está publicado."}
            )
        if not _event_is_valid(publication):
            blockers.append(
                {"code": "PUBLICATION_EVENT_INVALID", "detail": "O evento publicado não é válido."}
            )
        if events["WITHDRAW"] is not None:
            blockers.append(
                {"code": "VERSION_ALREADY_WITHDRAWN", "detail": "A versão já foi retirada."}
            )
        review = await _latest_public_review(
            connection,
            public_id=public_id,
            source_document_id=str(case["source_document_id"]),
        )
        audit = (
            await _publication_audit(
                connection,
                public_id=public_id,
                publication_event_sha256=str(publication["event_sha256"]),
            )
            if publication is not None
            else None
        )
        expected_after = (
            _audit_payload(
                action="PUBLISHED",
                case_id=str(case["id"]),
                version_id=str(case["version_id"]),
                projection=projection,
                publication_proof_sha256=proof,
                publication_event_id=str(publication["id"]),
                publication_event_sha256=str(publication["event_sha256"]),
                public_review_id=str(review["id"]),
            )
            if projection is not None and publication is not None and review is not None
            else {}
        )
        if not expected_after or not _audit_matches(
            audit=audit,
            review=review,
            event=publication,
            expected_after=expected_after,
        ):
            blockers.append(
                {
                    "code": "PUBLICATION_AUDIT_INVALID",
                    "detail": "A revisão pública e o rasto da publicação não coincidem.",
                }
            )
        effect = _public_effect(public_id)
        generation = projection.get("generation") if projection else None
        source = projection.get("source") if projection else None
        return {
            "case_id": str(case["id"]),
            "case_state": str(case["current_state"]),
            "revision": int(case["revision"]),
            "public_id": public_id,
            "source": source,
            "generation": generation,
            "editorial_version_sha256": str(case["editorial_sha256"]),
            "output_sha256": (
                str(generation["output_sha256"]) if isinstance(generation, dict) else "0" * 64
            ),
            "publication_proof_sha256": proof,
            "public_review_id": str(review["id"]) if review else "",
            "publication_audit_event_id": str(audit["id"]) if audit else "",
            "publication_event_id": str(publication["id"]) if publication else "",
            "publication_event_sha256": (
                str(publication["event_sha256"]) if publication else "0" * 64
            ),
            "public_effect": effect,
            "public_effect_sha256": _sha256_json(effect),
            "eligible": not blockers,
            "blockers": blockers,
            "withdrawal_rule": (
                "A retirada remove a versão da consulta ativa, mas acrescenta revisão, decisão, "
                "evento e motivo público sem alterar o histórico anterior."
            ),
        }

    async def publish(
        self,
        *,
        case_id: str,
        payload: AiEditorialPublicationRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor, action="publicação")
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"editorial-ai-public-id:{payload.expected_public_id}",
                )
                case = await _case_core(connection, case_id=case_id, lock=True)
                snapshot = await _snapshot_for_version(connection, case=case)
                preview = await self._publication_preview(
                    connection,
                    case=case,
                    snapshot=snapshot,
                )
                self._confirm_publication(case=case, preview=preview, payload=payload)
                self._raise_blockers(case=case, preview=preview, required=EditorialState.APPROVED)
                projection = preview["public_projection"]
                assert isinstance(projection, dict)

                created_at = await self._clock(connection)
                next_revision = int(case["revision"]) + 1
                version_id = str(case["version_id"])
                decision_id = _new_id("editorial_decision")
                event_id = _new_id("editorial_publication")
                review_id = _new_id("publication_review")
                audit_id = _new_id("audit")
                event_sha256 = _publication_event_sha256(
                    event_id=event_id,
                    case_id=case_id,
                    version_id=version_id,
                    action="PUBLISH",
                    target_type=AI_PUBLIC_TARGET_TYPE,
                    target_id=payload.expected_public_id,
                    rationale=payload.rationale,
                    actor_id=actor.staff_id,
                    actor_alias=actor.public_alias,
                    created_at=created_at,
                )
                decision_sha256 = self.editorial._decision_sha256(
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.PUBLISH,
                    previous_state=EditorialState.APPROVED,
                    resulting_state=EditorialState.PUBLISHED,
                    case_revision=next_revision,
                    rationale=payload.rationale,
                    source_confirmed=True,
                    actor=actor,
                    created_at=created_at,
                )
                audit_after = _audit_payload(
                    action="PUBLISHED",
                    case_id=case_id,
                    version_id=version_id,
                    projection=projection,
                    publication_proof_sha256=payload.expected_publication_proof_sha256,
                    publication_event_id=event_id,
                    publication_event_sha256=event_sha256,
                    public_review_id=review_id,
                )
                await self._insert_public_review(
                    connection,
                    review_id=review_id,
                    public_id=payload.expected_public_id,
                    source_document_id=str(case["source_document_id"]),
                    publishable=True,
                    actor=actor,
                    created_at=created_at,
                )
                await self._insert_public_audit(
                    connection,
                    audit_id=audit_id,
                    public_id=payload.expected_public_id,
                    action="PUBLISHED",
                    actor=actor,
                    before=None,
                    after=audit_after,
                    public_rationale=payload.public_rationale,
                    created_at=created_at,
                )
                await self.editorial._insert_decision(
                    connection,
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.PUBLISH,
                    previous_state=EditorialState.APPROVED,
                    resulting_state=EditorialState.PUBLISHED,
                    case_revision=next_revision,
                    rationale=payload.rationale,
                    source_confirmed=True,
                    actor=actor,
                    decision_sha256=decision_sha256,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    UPDATE editorial_cases
                    SET current_state = 'PUBLISHED', revision = $2, updated_at = $3
                    WHERE id = $1
                    """,
                    case_id,
                    next_revision,
                    created_at,
                )
                await self._insert_event(
                    connection,
                    event_id=event_id,
                    case_id=case_id,
                    version_id=version_id,
                    action="PUBLISH",
                    public_id=payload.expected_public_id,
                    rationale=payload.rationale,
                    actor=actor,
                    event_sha256=event_sha256,
                    created_at=created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A publicação já foi acrescentada ao histórico") from exc
        return {
            "created": True,
            "case_id": case_id,
            "state": "PUBLISHED",
            "revision": next_revision,
            "public_id": payload.expected_public_id,
            "decision_sha256": decision_sha256,
            "event_sha256": event_sha256,
            "publication_review_id": review_id,
            "audit_event_id": audit_id,
            "publication_rule": (
                "A revisão pública, a decisão humana e o evento imutável foram confirmados "
                "na mesma transação; nenhuma geração foi efetuada nesta ação."
            ),
        }

    async def withdraw(
        self,
        *,
        case_id: str,
        payload: AiEditorialWithdrawalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        self._require_admin(actor, action="retirada")
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"editorial-ai-public-id:{payload.expected_public_id}",
                )
                case = await _case_core(connection, case_id=case_id, lock=True)
                snapshot = await _snapshot_for_version(connection, case=case)
                preview = await self._withdrawal_preview(
                    connection,
                    case=case,
                    snapshot=snapshot,
                )
                self._confirm_withdrawal(case=case, preview=preview, payload=payload)
                self._raise_blockers(case=case, preview=preview, required=EditorialState.PUBLISHED)
                projection, projection_blockers = _proposal_projection(case=case, snapshot=snapshot)
                if projection is None or projection_blockers:
                    raise EditorialSourceError("A projeção publicada deixou de ser verificável")

                created_at = await self._clock(connection)
                next_revision = int(case["revision"]) + 1
                version_id = str(case["version_id"])
                decision_id = _new_id("editorial_decision")
                event_id = _new_id("editorial_publication")
                review_id = _new_id("publication_review")
                audit_id = _new_id("audit")
                internal_rationale = f"[{payload.reason_category.value}] {payload.rationale}"
                event_sha256 = _publication_event_sha256(
                    event_id=event_id,
                    case_id=case_id,
                    version_id=version_id,
                    action="WITHDRAW",
                    target_type=AI_PUBLIC_TARGET_TYPE,
                    target_id=payload.expected_public_id,
                    rationale=internal_rationale,
                    actor_id=actor.staff_id,
                    actor_alias=actor.public_alias,
                    created_at=created_at,
                )
                decision_sha256 = self.editorial._decision_sha256(
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.WITHDRAW,
                    previous_state=EditorialState.PUBLISHED,
                    resulting_state=EditorialState.WITHDRAWN,
                    case_revision=next_revision,
                    rationale=internal_rationale,
                    source_confirmed=False,
                    actor=actor,
                    created_at=created_at,
                )
                effect = _public_effect(payload.expected_public_id)
                audit_after = _audit_payload(
                    action="WITHDRAWN",
                    case_id=case_id,
                    version_id=version_id,
                    projection=projection,
                    publication_proof_sha256=payload.expected_publication_proof_sha256,
                    publication_event_id=event_id,
                    publication_event_sha256=event_sha256,
                    public_review_id=review_id,
                    reason_category=payload.reason_category.value,
                    public_effect=effect,
                )
                await self._insert_public_review(
                    connection,
                    review_id=review_id,
                    public_id=payload.expected_public_id,
                    source_document_id=str(case["source_document_id"]),
                    publishable=False,
                    actor=actor,
                    created_at=created_at,
                )
                await self._insert_public_audit(
                    connection,
                    audit_id=audit_id,
                    public_id=payload.expected_public_id,
                    action="WITHDRAWN",
                    actor=actor,
                    before={
                        "publishable": True,
                        "publication_event_reference_sha256": _reference_sha256(
                            payload.expected_publication_event_id
                        ),
                    },
                    after=audit_after,
                    public_rationale=payload.public_rationale,
                    created_at=created_at,
                )
                await self.editorial._insert_decision(
                    connection,
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.WITHDRAW,
                    previous_state=EditorialState.PUBLISHED,
                    resulting_state=EditorialState.WITHDRAWN,
                    case_revision=next_revision,
                    rationale=internal_rationale,
                    source_confirmed=False,
                    actor=actor,
                    decision_sha256=decision_sha256,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    UPDATE editorial_cases
                    SET current_state = 'WITHDRAWN', revision = $2, updated_at = $3
                    WHERE id = $1
                    """,
                    case_id,
                    next_revision,
                    created_at,
                )
                await self._insert_event(
                    connection,
                    event_id=event_id,
                    case_id=case_id,
                    version_id=version_id,
                    action="WITHDRAW",
                    public_id=payload.expected_public_id,
                    rationale=internal_rationale,
                    actor=actor,
                    event_sha256=event_sha256,
                    created_at=created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A retirada já foi acrescentada ao histórico") from exc
        return {
            "created": True,
            "case_id": case_id,
            "state": "WITHDRAWN",
            "revision": next_revision,
            "public_id": payload.expected_public_id,
            "reason_category": payload.reason_category.value,
            "decision_sha256": decision_sha256,
            "event_sha256": event_sha256,
            "publication_review_id": review_id,
            "audit_event_id": audit_id,
            "public_effect": effect,
            "public_effect_sha256": _sha256_json(effect),
            "withdrawal_rule": (
                "A consulta ativa regressou a dados indisponíveis; a versão, a publicação e "
                "todos os eventos anteriores permanecem imutáveis."
            ),
        }

    @staticmethod
    def _require_admin(actor: StaffSession, *, action: str) -> None:
        if actor.role is not StaffRole.ADMIN:
            raise EditorialConflictError(f"Esta {action} exige um administrador editorial")
        if actor.assurance_level != "aal2":
            raise EditorialConflictError(f"A {action} exige autenticação multifator")

    @staticmethod
    def _raise_blockers(
        *,
        case: dict[str, Any],
        preview: dict[str, object],
        required: EditorialState,
    ) -> None:
        blockers = preview["blockers"]
        assert isinstance(blockers, list)
        if not blockers:
            return
        details = "; ".join(str(item["detail"]) for item in blockers)
        if str(case["current_state"]) != required.value:
            raise EditorialConflictError(details)
        raise EditorialSourceError(details)

    @staticmethod
    def _confirm_publication(
        *,
        case: dict[str, Any],
        preview: dict[str, object],
        payload: AiEditorialPublicationRequest,
    ) -> None:
        source = _as_json_object(preview["source"]) or {}
        checks = {
            "revisão": (str(payload.expected_revision), str(case["revision"])),
            "identificador público": (payload.expected_public_id, str(preview["public_id"])),
            "SHA-256 da fonte": (
                payload.expected_source_sha256,
                str(source.get("content_sha256")),
            ),
            "SHA-256 do texto": (
                payload.expected_normalised_text_sha256,
                str(source.get("normalised_text_sha256")),
            ),
            "SHA-256 editorial": (
                payload.expected_editorial_sha256,
                str(preview["editorial_version_sha256"]),
            ),
            "SHA-256 da saída": (payload.expected_output_sha256, str(preview["output_sha256"])),
            "prova de publicação": (
                payload.expected_publication_proof_sha256,
                str(preview["publication_proof_sha256"]),
            ),
        }
        for label, (received, expected) in checks.items():
            if not secrets.compare_digest(received, expected):
                raise EditorialConflictError(f"A confirmação de {label} já não coincide")

    @staticmethod
    def _confirm_withdrawal(
        *,
        case: dict[str, Any],
        preview: dict[str, object],
        payload: AiEditorialWithdrawalRequest,
    ) -> None:
        source = _as_json_object(preview["source"]) or {}
        checks = {
            "revisão": (str(payload.expected_revision), str(case["revision"])),
            "identificador público": (payload.expected_public_id, str(preview["public_id"])),
            "SHA-256 da fonte": (payload.expected_source_sha256, str(source.get("content_sha256"))),
            "SHA-256 do texto": (
                payload.expected_normalised_text_sha256,
                str(source.get("normalised_text_sha256")),
            ),
            "SHA-256 editorial": (
                payload.expected_editorial_sha256,
                str(preview["editorial_version_sha256"]),
            ),
            "SHA-256 da saída": (payload.expected_output_sha256, str(preview["output_sha256"])),
            "prova de publicação": (
                payload.expected_publication_proof_sha256,
                str(preview["publication_proof_sha256"]),
            ),
            "revisão pública": (
                payload.expected_public_review_id,
                str(preview["public_review_id"]),
            ),
            "auditoria pública": (
                payload.expected_publication_audit_event_id,
                str(preview["publication_audit_event_id"]),
            ),
            "evento publicado": (
                payload.expected_publication_event_id,
                str(preview["publication_event_id"]),
            ),
            "SHA-256 do evento": (
                payload.expected_publication_event_sha256,
                str(preview["publication_event_sha256"]),
            ),
            "efeito público": (
                payload.expected_public_effect_sha256,
                str(preview["public_effect_sha256"]),
            ),
        }
        for label, (received, expected) in checks.items():
            if not secrets.compare_digest(received, expected):
                raise EditorialConflictError(f"A confirmação de {label} já não coincide")

    @staticmethod
    async def _clock(connection: asyncpg.Connection) -> datetime:
        value = await connection.fetchval(
            "SELECT (clock_timestamp() AT TIME ZONE 'UTC')::timestamp(3)"
        )
        if not isinstance(value, datetime):
            raise RuntimeError("Não foi possível obter o relógio transacional")
        return value

    @staticmethod
    async def _insert_public_review(
        connection: asyncpg.Connection,
        *,
        review_id: str,
        public_id: str,
        source_document_id: str,
        publishable: bool,
        actor: StaffSession,
        created_at: datetime,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO data_publication_reviews
                (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                 necessity_assessment, proportionality_test, publishable,
                 source_document_id, reviewed_by, reviewed_at)
            VALUES ($1, $2, $3,
                    'Explicação cívica de um documento oficial do Diário da República',
                    'NOT_APPLICABLE', 'PUBLIC_OFFICIAL',
                    'Publica apenas a fonte oficial, a síntese revista e as provas técnicas.',
                    'Não publica o texto privado, instruções internas ou notas editoriais.',
                    $4, $5, $6, $7)
            """,
            review_id,
            AI_PUBLIC_AUDIT_TYPE,
            public_id,
            publishable,
            source_document_id,
            actor.public_alias,
            created_at,
        )

    @staticmethod
    async def _insert_public_audit(
        connection: asyncpg.Connection,
        *,
        audit_id: str,
        public_id: str,
        action: str,
        actor: StaffSession,
        before: dict[str, object] | None,
        after: dict[str, object],
        public_rationale: str,
        created_at: datetime,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO audit_events
                (id, entity_type, entity_id, action, actor_alias,
                 before_json, after_json, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9)
            """,
            audit_id,
            AI_PUBLIC_AUDIT_TYPE,
            public_id,
            action,
            actor.public_alias,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False, sort_keys=True),
            public_rationale,
            created_at,
        )

    @staticmethod
    async def _insert_event(
        connection: asyncpg.Connection,
        *,
        event_id: str,
        case_id: str,
        version_id: str,
        action: str,
        public_id: str,
        rationale: str,
        actor: StaffSession,
        event_sha256: str,
        created_at: datetime,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO editorial_publication_events
                (id, case_id, version_id, action, target_type, target_id,
                 rationale, actor_id, actor_alias, event_sha256, created_at)
            VALUES ($1, $2, $3, $4::"EditorialPublicationAction", $5, $6,
                    $7, $8, $9, $10, $11)
            """,
            event_id,
            case_id,
            version_id,
            action,
            AI_PUBLIC_TARGET_TYPE,
            public_id,
            rationale,
            actor.staff_id,
            actor.public_alias,
            event_sha256,
            created_at,
        )


class PublicAiExplanationRepository:
    """Projeção pública que volta a validar a versão, a fonte e todos os eventos."""

    def __init__(self, pool: asyncpg.Pool | None) -> None:
        self.pool = pool

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        return self.pool

    async def list_explanations(
        self,
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        pool = self._require_pool()
        async with (
            pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            case_ids = await connection.fetch(
                """
                SELECT id
                FROM editorial_cases
                WHERE kind = 'AI_EXPLANATION'
                  AND subject_type = 'DRE_DOCUMENT_SNAPSHOT'
                  AND origin = 'AI'
                  AND current_state = 'PUBLISHED'
                ORDER BY updated_at DESC, id DESC
                """
            )
            items: list[dict[str, object]] = []
            for candidate in case_ids:
                projected = await self._published_case(
                    connection,
                    case_id=str(candidate["id"]),
                )
                if projected is not None:
                    items.append(projected)

        counts: dict[str, int] = {}
        for item in items:
            public_id = str(item["id"])
            counts[public_id] = counts.get(public_id, 0) + 1
        items = [item for item in items if counts[str(item["id"])] == 1]
        needle = query.casefold().strip() if query else None
        if needle:
            items = [item for item in items if self._matches_query(item, needle)]
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
            "query": query,
            "total_is_exact": True,
            "publication_rule": (
                "Só aparecem versões com fonte DRE atestada, revisão humana, evento PUBLISH "
                "íntegro e porta pública positiva para a mesma versão."
            ),
        }

    @staticmethod
    def _matches_query(item: dict[str, object], needle: str) -> bool:
        summary = _as_json_object(item.get("summary")) or {}
        source = _as_json_object(item.get("source")) or {}
        haystack = " ".join(
            (
                str(summary.get("title") or ""),
                str(source.get("title") or ""),
                str(source.get("official_identifier") or ""),
            )
        ).casefold()
        return needle in haystack

    async def get_explanation(self, *, public_id: str) -> dict[str, object] | None:
        if not _PUBLIC_ID.fullmatch(public_id):
            return None
        pool = self._require_pool()
        async with (
            pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            rows = await connection.fetch(
                """
                SELECT DISTINCT candidate.id
                FROM editorial_cases candidate
                JOIN editorial_publication_events event
                  ON event.case_id = candidate.id
                 AND event.version_id = candidate.current_version_id
                 AND event.action = 'PUBLISH'
                 AND event.target_type = $1
                 AND event.target_id = $2
                WHERE candidate.kind = 'AI_EXPLANATION'
                  AND candidate.subject_type = 'DRE_DOCUMENT_SNAPSHOT'
                  AND candidate.origin = 'AI'
                  AND candidate.current_state = 'PUBLISHED'
                """,
                AI_PUBLIC_TARGET_TYPE,
                public_id,
            )
            if len(rows) != 1:
                return None
            item = await self._published_case(connection, case_id=str(rows[0]["id"]))
            return item if item is not None and item["id"] == public_id else None

    async def _published_case(
        self,
        connection: asyncpg.Connection,
        *,
        case_id: str,
    ) -> dict[str, object] | None:
        try:
            case = await _case_core(connection, case_id=case_id, lock=False)
            if str(case["current_state"]) != EditorialState.PUBLISHED.value:
                return None
            snapshot = await _snapshot_for_version(connection, case=case)
            projection, blockers = _proposal_projection(case=case, snapshot=snapshot)
            if projection is None or blockers:
                return None
            public_id = str(projection["id"])
            proof = _publication_proof(projection)
            events = await _events(
                connection,
                case_id=case_id,
                version_id=str(case["version_id"]),
                public_id=public_id,
            )
            event = events["PUBLISH"]
            if not _event_is_valid(event) or events["WITHDRAW"] is not None:
                return None
            assert event is not None
            review = await _latest_public_review(
                connection,
                public_id=public_id,
                source_document_id=str(case["source_document_id"]),
            )
            audit = await _publication_audit(
                connection,
                public_id=public_id,
                publication_event_sha256=str(event["event_sha256"]),
            )
            expected_after = (
                _audit_payload(
                    action="PUBLISHED",
                    case_id=case_id,
                    version_id=str(case["version_id"]),
                    projection=projection,
                    publication_proof_sha256=proof,
                    publication_event_id=str(event["id"]),
                    publication_event_sha256=str(event["event_sha256"]),
                    public_review_id=str(review["id"]),
                )
                if review is not None
                else {}
            )
            if not expected_after or not _audit_matches(
                audit=audit,
                review=review,
                event=event,
                expected_after=expected_after,
            ):
                return None
            source = projection.pop("source")
            generation = projection.pop("generation")
            summary = projection.pop("summary")
            projection.pop("schema_version")
            projection.pop("editorial_version_sha256")
            return {
                **projection,
                "summary": summary,
                "source": source,
                "generation": generation,
                "editorial": {
                    "human_reviewed": True,
                    "reviewed_by": str(event["actor_alias"]),
                    "published_at": _aware(event["created_at"]),
                    "editorial_version_sha256": str(case["editorial_sha256"]),
                    "publication_proof_sha256": proof,
                    "publication_event_reference_sha256": _reference_sha256(str(event["id"])),
                },
            }
        except (
            EditorialConflictError,
            EditorialNotFoundError,
            EditorialSourceError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return None

    async def list_publication_history(self, *, limit: int) -> list[dict[str, object]]:
        pool = self._require_pool()
        async with (
            pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            rows = await connection.fetch(
                """
                SELECT audit.id AS audit_id, audit.action AS audit_action,
                       audit.actor_alias AS audit_actor_alias, audit.after_json,
                       audit.reason AS public_rationale, audit.created_at AS audit_created_at,
                       event.id AS event_id, event.case_id, event.version_id,
                       event.action::text AS event_action, event.target_type,
                       event.target_id, event.rationale AS event_rationale,
                       event.actor_id, event.actor_alias AS event_actor_alias,
                       event.event_sha256, event.created_at AS event_created_at
                FROM audit_events audit
                JOIN editorial_publication_events event
                  ON event.event_sha256 = audit.after_json ->> 'publication_event_sha256'
                 AND event.target_type = $1
                 AND event.target_id = audit.entity_id
                WHERE audit.entity_type = $2
                  AND audit.action IN ('PUBLISHED', 'WITHDRAWN')
                ORDER BY audit.created_at DESC, audit.id DESC
                LIMIT $3
                """,
                AI_PUBLIC_TARGET_TYPE,
                AI_PUBLIC_AUDIT_TYPE,
                limit * 3,
            )
            history: list[dict[str, object]] = []
            for row_record in rows:
                row = dict(row_record)
                item = await self._history_item(connection, row=row)
                if item is not None:
                    history.append(item)
                if len(history) >= limit:
                    break
            return history

    async def _history_item(
        self,
        connection: asyncpg.Connection,
        *,
        row: dict[str, Any],
    ) -> dict[str, object] | None:
        try:
            case = await _case_core(
                connection,
                case_id=str(row["case_id"]),
                lock=False,
                version_id=str(row["version_id"]),
            )
            snapshot = await _snapshot_for_version(connection, case=case)
            projection, blockers = _proposal_projection(case=case, snapshot=snapshot)
            if projection is None or blockers or str(projection["id"]) != str(row["target_id"]):
                return None
            event = {
                "id": row["event_id"],
                "case_id": row["case_id"],
                "version_id": row["version_id"],
                "action": row["event_action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "rationale": row["event_rationale"],
                "actor_id": row["actor_id"],
                "actor_alias": row["event_actor_alias"],
                "event_sha256": row["event_sha256"],
                "created_at": row["event_created_at"],
            }
            if not _event_is_valid(event):
                return None
            after = _as_json_object(row.get("after_json"))
            if after is None:
                return None
            action = str(row["audit_action"])
            if action not in {"PUBLISHED", "WITHDRAWN"}:
                return None
            expected_event_action = "PUBLISH" if action == "PUBLISHED" else "WITHDRAW"
            if str(row["event_action"]) != expected_event_action:
                return None
            proof = _publication_proof(projection)
            review_reference = after.get("public_review_reference_sha256")
            if not isinstance(review_reference, str):
                return None
            review = await _public_review_by_reference(
                connection,
                public_id=str(projection["id"]),
                source_document_id=str(case["source_document_id"]),
                reference_sha256=review_reference,
            )
            if review is None:
                return None
            effect: dict[str, Any] | None = None
            effect_sha: object = None
            reason_category: str | None = None
            if action == "WITHDRAWN":
                effect = _as_json_object(after.get("public_effect"))
                effect_sha = after.get("public_effect_sha256")
                raw_reason_category = after.get("withdrawal_reason_category")
                try:
                    reason_category = ParliamentWithdrawalReason(str(raw_reason_category)).value
                except ValueError:
                    return None
                if (
                    effect != _public_effect(str(projection["id"]))
                    or not isinstance(effect_sha, str)
                    or _sha256_json(effect) != effect_sha
                ):
                    return None
            expected_after = _audit_payload(
                action=action,
                case_id=str(case["id"]),
                version_id=str(case["version_id"]),
                projection=projection,
                publication_proof_sha256=proof,
                publication_event_id=str(row["event_id"]),
                publication_event_sha256=str(row["event_sha256"]),
                public_review_id=str(review["id"]),
                reason_category=reason_category,
                public_effect=effect,
            )
            audit = {
                "after_json": after,
                "created_at": row["audit_created_at"],
                "actor_alias": row["audit_actor_alias"],
                "reason": row["public_rationale"],
            }
            if not _audit_matches(
                audit=audit,
                review=review,
                event=event,
                expected_after=expected_after,
                expected_publishable=action == "PUBLISHED",
            ):
                return None
            summary = _as_json_object(projection["summary"])
            source = projection["source"]
            assert summary is not None
            return {
                "event_reference_sha256": _reference_sha256(str(row["event_id"])),
                "action": action,
                "public_id": str(projection["id"]),
                "title": str(summary["title"]),
                "decided_at": _aware(row["audit_created_at"]),
                "actor_alias": str(row["audit_actor_alias"]),
                "public_rationale": str(row["public_rationale"]),
                "reason_category": after.get("withdrawal_reason_category"),
                "source": source,
                "editorial_version_sha256": str(case["editorial_sha256"]),
                "publication_proof_sha256": proof,
                "public_effect": effect,
                "public_effect_sha256": effect_sha,
            }
        except (
            EditorialConflictError,
            EditorialNotFoundError,
            EditorialSourceError,
            KeyError,
            TypeError,
            ValueError,
        ):
            return None
