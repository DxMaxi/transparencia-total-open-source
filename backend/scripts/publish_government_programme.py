"""Operação V4 desativada: a ingestão do programa nunca publica diretamente."""


def main() -> None:
    raise RuntimeError(
        "Operação desativada: use stage_government_programme_catalogue apenas em staging; "
        "aprovação e publicação são fases editoriais separadas."
    )


if __name__ == "__main__":
    main()
