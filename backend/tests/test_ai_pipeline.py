from pathlib import Path

from app.services.ai_summarizer import PROMPT_SHA256, PROMPT_VERSION, SYSTEM_PROMPT

ROOT = Path(__file__).parents[2]


def test_prompt_is_versioned_and_hashed() -> None:
    assert PROMPT_VERSION
    assert "Não uses conhecimento externo" in SYSTEM_PROMPT
    assert len(PROMPT_SHA256) == 64


def test_experimental_ai_routes_require_editorial_staff_with_mfa() -> None:
    route = (ROOT / "backend" / "app" / "api" / "routes" / "ai.py").read_text(encoding="utf-8")

    assert route.count("Depends(require_editorial_staff)") == 2
    assert "StaffSession" in route
    assert '@router.post("/summaries"' in route
    assert '@router.post("/civic-guide"' in route
