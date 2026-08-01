from app.services.ai_summarizer import PROMPT_SHA256, PROMPT_VERSION, SYSTEM_PROMPT


def test_prompt_is_versioned_and_hashed() -> None:
    assert PROMPT_VERSION
    assert "Não uses conhecimento externo" in SYSTEM_PROMPT
    assert len(PROMPT_SHA256) == 64
