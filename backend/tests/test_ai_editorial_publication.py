import hashlib
from datetime import UTC, datetime

from app.core.config import Settings
from app.models.api import CitizenSummary, SourceAnchor
from app.repositories.ai_editorial import AiDreSnapshot
from app.repositories.ai_editorial_publication import (
    AI_PUBLIC_LABEL,
    _proposal_projection,
    _sha256_json,
)
from app.services.ai_editorial import AiEditorialService


def _snapshot() -> AiDreSnapshot:
    text = "Artigo 1.º\nO presente diploma estabelece uma regra verificável."
    return AiDreSnapshot(
        snapshot_id="dre_snapshot_test",
        source_document_id="source_document_test",
        official_identifier="Lei n.º 9/2026",
        title="Lei n.º 9/2026",
        source_url="https://data.dre.pt/eli/lei/9/2026/p/dre/pt/html",
        source_content_sha256=hashlib.sha256(b"documento oficial").hexdigest(),
        normalised_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        extracted_text=text,
        source_characters=len(text),
        retrieved_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        published_at=datetime(2026, 8, 20, 0, 0, tzinfo=UTC),
        collected_at=datetime(2026, 8, 20, 10, 1, tzinfo=UTC),
        parser_version="dre-v5-test",
        archive_attestation_id="archive_attestation_test",
        archive_attestation_sha256="a" * 64,
        archive_storage_backend="test",
        archive_byte_size=123,
        archive_archived_at=datetime(2026, 8, 20, 10, 2, tzinfo=UTC),
    )


def _case() -> tuple[dict[str, object], AiDreSnapshot]:
    snapshot = _snapshot()
    summary = CitizenSummary(
        title="Explicação verificável",
        summary_2_minutes="O Artigo 1.º estabelece uma regra.",
        what_changes=["Estabelece uma regra verificável."],
        who_is_affected=[],
        dates_and_deadlines=[],
        duties_and_rights=[],
        uncertainties=["A consequência material exige prova oficial adicional."],
        glossary=[],
        source_anchors=[SourceAnchor(section="Artigo 1.º", reason="Contém a regra descrita.")],
    )
    service = AiEditorialService(
        repository=None,  # type: ignore[arg-type]
        editorial=None,  # type: ignore[arg-type]
        settings=Settings(
            _env_file=None,
            environment="test",
            ai_provider="openai",
            openai_api_key="test",
            openai_model="gpt-test",
        ),
        summarizer=None,
    )
    normalized = service._normalized_proposal(
        snapshot=snapshot,
        summary=summary,
        generated_at=datetime(2026, 8, 20, 10, 3, tzinfo=UTC),
        abstained=False,
        attempt_id="ai_attempt_test",
    )
    return (
        {
            "normalized_json": normalized,
            "editorial_sha256": _sha256_json(normalized),
        },
        snapshot,
    )


def test_projection_is_fully_labelled_and_contains_no_private_identifiers() -> None:
    case, snapshot = _case()

    projection, blockers = _proposal_projection(case=case, snapshot=snapshot)

    assert blockers == []
    assert projection is not None
    assert projection["id"] == f"dre-{snapshot.source_content_sha256}"
    assert projection["label"] == AI_PUBLIC_LABEL
    assert projection["ai_is_source"] is False
    assert projection["not_prediction"] is True
    assert projection["no_voting_recommendation"] is True
    serialized = str(projection)
    assert snapshot.snapshot_id not in serialized
    assert snapshot.source_document_id not in serialized
    assert snapshot.archive_attestation_id not in serialized


def test_projection_fails_closed_when_output_or_anchor_changes() -> None:
    case, snapshot = _case()
    normalized = case["normalized_json"]
    assert isinstance(normalized, dict)
    summary = normalized["summary"]
    assert isinstance(summary, dict)
    summary["what_changes"] = ["Afirmação sem suporte alterada depois da geração."]
    case["editorial_sha256"] = _sha256_json(normalized)

    projection, blockers = _proposal_projection(case=case, snapshot=snapshot)

    assert projection is None
    assert "OUTPUT_HASH_MISMATCH" in {item["code"] for item in blockers}
