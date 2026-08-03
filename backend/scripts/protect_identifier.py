"""Gera localmente um HMAC para um NIF/NIPC sem guardar o valor em claro."""

import getpass

from app.core.config import get_settings
from app.core.security import hmac_protected_identifier


def main() -> None:
    settings = get_settings()
    if settings.protected_identifier_pepper is None:
        raise SystemExit(
            "PROTECTED_IDENTIFIER_PEPPER não configurado; não é possível gerar o HMAC."
        )

    identifier = getpass.getpass("NIF/NIPC (entrada oculta, não será guardada): ")
    try:
        digest = hmac_protected_identifier(
            identifier,
            settings.protected_identifier_pepper.get_secret_value(),
        )
    finally:
        identifier = ""
    print(digest)


if __name__ == "__main__":
    main()
