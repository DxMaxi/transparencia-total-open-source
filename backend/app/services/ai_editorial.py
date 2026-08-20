"""Coordena geração privada de IA com fonte atestada e revisão obrigatória."""

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime

from app.core.config import Settings
from app.models.api import CitizenSummary
from app.models.editorial import AiDreProposalRequest, StaffSession
from app.repositories.ai_editorial import AiDreSnapshot, AiEditorialRepository, ai_subject_id
from app.repositories.editorial import EditorialConflictError, EditorialRepository
from app.services.ai_summarizer import PROMPT_SHA256, PROMPT_VERSION, Summarizer

AI_DRE_CONTRACT_VERSION = "v5.ai.dre-summary.v1"
_ABSTENTION_TEXT = "não é possível determinar"


class AiGenerationError(RuntimeError):
    """Falha controlada depois de um pedido ao fornecedor de IA."""


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


def _searchable(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def validate_summary_against_source(summary: CitizenSummary, source_text: str) -> bool:
    """Valida âncoras literais ou uma abstenção explícita.

    Não tenta decidir se a interpretação é correta; essa decisão pertence ao
    revisor. Impede apenas âncoras inexistentes e saídas factuais sem qualquer
    ponto verificável no documento recebido.
    """

    factual_items = (
        summary.what_changes
        + summary.who_is_affected
        + summary.dates_and_deadlines
        + summary.duties_and_rights
    )
    abstained = (
        not factual_items
        and _ABSTENTION_TEXT in _searchable(summary.summary_2_minutes)
        and any(_ABSTENTION_TEXT in _searchable(item) for item in summary.uncertainties)
    )
    if abstained:
        return True
    if not summary.source_anchors:
        raise EditorialConflictError("A proposta de IA não contém âncoras verificáveis")

    searchable_source = _searchable(source_text)
    missing = [
        anchor.section
        for anchor in summary.source_anchors
        if _searchable(anchor.section) not in searchable_source
    ]
    if missing:
        raise EditorialConflictError(
            "A proposta de IA contém uma âncora que não existe no documento oficial"
        )
    return False


class AiEditorialService:
    def __init__(
        self,
        *,
        repository: AiEditorialRepository,
        editorial: EditorialRepository,
        settings: Settings,
        summarizer: Summarizer,
    ) -> None:
        self.repository = repository
        self.editorial = editorial
        self.settings = settings
        self.summarizer = summarizer

    async def create_dre_proposal(
        self,
        *,
        payload: AiDreProposalRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        snapshot = await self.repository.load_dre_snapshot(payload.snapshot_id)
        subject_id = ai_subject_id(
            snapshot_id=snapshot.snapshot_id,
            provider=self.settings.ai_provider,
            model=self.settings.openai_model,
            prompt_sha256=PROMPT_SHA256,
        )
        async with self.repository.generation_guard():
            existing = await self.repository.find_existing_proposal(
                subject_id=subject_id,
                source_document_id=snapshot.source_document_id,
            )
            if existing is not None:
                return self._result(existing, created=False, reused=True)

            used_today = await self.repository.count_ai_generation_attempts_today()
            if used_today >= self.settings.ai_daily_generation_limit:
                raise EditorialConflictError(
                    "O limite diário de propostas de IA foi atingido; não foi chamado nenhum modelo"
                )

            attempt_id = f"ai_attempt_{uuid.uuid4().hex}"
            attempt_metadata = self._attempt_metadata(
                snapshot=snapshot,
                subject_id=subject_id,
            )
            await self.repository.record_generation_event(
                attempt_id=attempt_id,
                action="REQUESTED",
                actor_alias=actor.public_alias,
                metadata=attempt_metadata,
            )
            try:
                summary = await self.summarizer.summarize(snapshot.legal_document())
                abstained = validate_summary_against_source(summary, snapshot.extracted_text)
                generated_at = datetime.now(UTC)
                normalized_data = self._normalized_proposal(
                    snapshot=snapshot,
                    summary=summary,
                    generated_at=generated_at,
                    abstained=abstained,
                    attempt_id=attempt_id,
                )
                case, created = await self.editorial.create_ai_case(
                    subject_type="DRE_DOCUMENT_SNAPSHOT",
                    subject_id=subject_id,
                    source_document_id=snapshot.source_document_id,
                    normalized_data=normalized_data,
                    origin_alias=(
                        f"ai:{self.settings.ai_provider}:{self.settings.openai_model}"[:80]
                    ),
                    submission_rationale=(
                        "Proposta gerada por IA a pedido de staff; permanece privada, PENDING e "
                        "sujeita a comparação integral com a fonte oficial atestada."
                    ),
                    actor=actor,
                )
            except Exception as exc:
                await self.repository.record_generation_event(
                    attempt_id=attempt_id,
                    action="FAILED",
                    actor_alias=actor.public_alias,
                    metadata={
                        **attempt_metadata,
                        "failure_category": _failure_category(exc),
                    },
                )
                if isinstance(exc, ValueError) and not isinstance(
                    exc,
                    EditorialConflictError,
                ):
                    raise AiGenerationError(
                        "O fornecedor não devolveu uma proposta estruturada válida"
                    ) from exc
                raise

            await self.repository.record_generation_event(
                attempt_id=attempt_id,
                action="SUCCEEDED",
                actor_alias=actor.public_alias,
                metadata={
                    **attempt_metadata,
                    "case_id": str(case["id"]),
                    "output_sha256": _sha256_json(summary.model_dump(mode="json")),
                },
            )
            return self._result(case, created=created, reused=not created)

    def _attempt_metadata(
        self,
        *,
        snapshot: AiDreSnapshot,
        subject_id: str,
    ) -> dict[str, object]:
        return {
            "contract_version": AI_DRE_CONTRACT_VERSION,
            "subject_id": subject_id,
            "snapshot_id": snapshot.snapshot_id,
            "source_document_id": snapshot.source_document_id,
            "source_content_sha256": snapshot.source_content_sha256,
            "normalised_text_sha256": snapshot.normalised_text_sha256,
            "provider": self.settings.ai_provider,
            "model": self.settings.openai_model,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256,
            "provider_store": False,
        }

    def _normalized_proposal(
        self,
        *,
        snapshot: AiDreSnapshot,
        summary: CitizenSummary,
        generated_at: datetime,
        abstained: bool,
        attempt_id: str,
    ) -> dict[str, object]:
        summary_json = summary.model_dump(mode="json")
        input_manifest = {
            "snapshot_id": snapshot.snapshot_id,
            "source_document_id": snapshot.source_document_id,
            "source_content_sha256": snapshot.source_content_sha256,
            "normalised_text_sha256": snapshot.normalised_text_sha256,
            "provider": self.settings.ai_provider,
            "model": self.settings.openai_model,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256,
        }
        return {
            "contract_version": AI_DRE_CONTRACT_VERSION,
            "proposal_type": "DRE_CITIZEN_SUMMARY",
            "requires_human_review": True,
            "publication_eligible": False,
            "ai_is_source": False,
            "abstained": abstained,
            "source": {
                "publisher": "DRE",
                "source_document_reference_sha256": _reference_sha256(snapshot.source_document_id),
                "snapshot_reference_sha256": _reference_sha256(snapshot.snapshot_id),
                "official_identifier": snapshot.official_identifier,
                "title": snapshot.title,
                "url_sha256": _reference_sha256(snapshot.source_url),
                "retrieved_at": snapshot.retrieved_at.isoformat(),
                "published_at": (
                    snapshot.published_at.isoformat() if snapshot.published_at is not None else None
                ),
                "content_sha256": snapshot.source_content_sha256,
                "normalised_text_sha256": snapshot.normalised_text_sha256,
                "parser_version": snapshot.parser_version,
                "archive_attestation_reference_sha256": _reference_sha256(
                    snapshot.archive_attestation_id
                ),
                "archive_attestation_sha256": snapshot.archive_attestation_sha256,
            },
            "generation": {
                "provider": self.settings.ai_provider,
                "model": self.settings.openai_model,
                "attempt_reference_sha256": _reference_sha256(attempt_id),
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": PROMPT_SHA256,
                "input_sha256": _sha256_json(input_manifest),
                "output_sha256": _sha256_json(summary_json),
                "source_characters": snapshot.source_characters,
                "processed_characters": min(
                    snapshot.source_characters,
                    self.settings.ai_max_source_chars,
                ),
                "source_truncated": (
                    snapshot.source_characters > self.settings.ai_max_source_chars
                ),
                "generated_at": generated_at.isoformat(),
                "provider_store": False,
            },
            "summary": summary_json,
        }

    @staticmethod
    def _result(
        case: dict[str, object],
        *,
        created: bool,
        reused: bool,
    ) -> dict[str, object]:
        return {
            "case": case,
            "created": created,
            "reused": reused,
            "state": "PRIVATE_PENDING_REVIEW",
            "publication_performed": False,
        }


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, EditorialConflictError):
        return "VALIDATION_OR_CONFLICT"
    if isinstance(exc, ValueError):
        return "INVALID_STRUCTURED_OUTPUT"
    return "PROVIDER_OR_INTERNAL_ERROR"
