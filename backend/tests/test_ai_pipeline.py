from pathlib import Path

import pytest

from app.models.api import CitizenSummary, SourceAnchor
from app.repositories.editorial import EditorialConflictError
from app.services.ai_editorial import validate_summary_against_source
from app.services.ai_summarizer import PROMPT_SHA256, PROMPT_VERSION, SYSTEM_PROMPT

ROOT = Path(__file__).parents[2]


def test_prompt_is_versioned_and_hashed() -> None:
    assert PROMPT_VERSION
    assert "Não uses conhecimento externo" in SYSTEM_PROMPT
    assert "literalmente no texto fornecido" in SYSTEM_PROMPT
    assert "Não é possível determinar" in SYSTEM_PROMPT
    assert len(PROMPT_SHA256) == 64


def test_experimental_ai_routes_require_editorial_staff_with_mfa() -> None:
    route = (ROOT / "backend" / "app" / "api" / "routes" / "ai.py").read_text(encoding="utf-8")

    assert route.count("Depends(require_editorial_staff)") == 2
    assert "StaffSession" in route
    assert '@router.post("/summaries"' in route
    assert '@router.post("/civic-guide"' in route
    assert "status_code=410" in route


def test_legacy_dre_script_cannot_generate_an_unpersisted_summary() -> None:
    script = (ROOT / "backend" / "scripts" / "summarize_dre.py").read_text(encoding="utf-8")

    assert "Geração direta desativada" in script
    assert "get_summarizer" not in script
    assert "DreCollector" not in script


def _summary(*, section: str | None) -> CitizenSummary:
    return CitizenSummary(
        title="Resumo privado",
        summary_2_minutes="O Artigo 1.º define a entrada em vigor.",
        what_changes=["Define a entrada em vigor."],
        who_is_affected=[],
        dates_and_deadlines=[],
        duties_and_rights=[],
        uncertainties=[],
        glossary=[],
        source_anchors=(
            [SourceAnchor(section=section, reason="Contém a regra referida.")]
            if section is not None
            else []
        ),
    )


def test_ai_summary_requires_literal_source_anchors() -> None:
    source = "Artigo 1.º\nA presente lei entra em vigor no dia seguinte."

    assert validate_summary_against_source(_summary(section="Artigo 1.º"), source) is False
    with pytest.raises(EditorialConflictError, match="não existe"):
        validate_summary_against_source(_summary(section="Artigo 99.º"), source)
    with pytest.raises(EditorialConflictError, match="não contém âncoras"):
        validate_summary_against_source(_summary(section=None), source)


def test_ai_summary_can_abstain_without_inventing_an_anchor() -> None:
    summary = CitizenSummary(
        title="Dados insuficientes",
        summary_2_minutes="Não é possível determinar com os dados verificados fornecidos.",
        what_changes=[],
        who_is_affected=[],
        dates_and_deadlines=[],
        duties_and_rights=[],
        uncertainties=["Não é possível determinar com os dados verificados fornecidos."],
        glossary=[],
        source_anchors=[],
    )

    assert validate_summary_against_source(summary, "Documento oficial incompleto.") is True
