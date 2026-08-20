"""Comando legado desativado: uma geração sem persistência não é revisão editorial."""


def main() -> None:
    raise SystemExit(
        "Geração direta desativada. Use POST /api/v1/editorial/ai/dre-proposals "
        "com uma sessão editorial MFA e um snapshot DRE previamente arquivado."
    )


if __name__ == "__main__":
    main()
