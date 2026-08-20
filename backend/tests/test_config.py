import pytest

from app.core.config import Settings


def test_blank_optional_admin_key_is_not_configured() -> None:
    settings = Settings(admin_api_key="")

    assert settings.admin_api_key is None


def test_non_blank_admin_key_still_requires_32_characters() -> None:
    with pytest.raises(ValueError, match="ADMIN_API_KEY deve ter pelo menos 32 caracteres"):
        Settings(admin_api_key="curta")


def test_ai_provider_storage_cannot_be_enabled() -> None:
    with pytest.raises(ValueError, match="OPENAI_STORE tem de permanecer false"):
        Settings(openai_store=True)
