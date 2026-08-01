"""Bloqueia a antiga importação de fixtures fictícias para uma base de dados real."""

MESSAGE = """\
Este script foi desativado porque as fixtures contêm dados fictícios de teste e não
devem ser importadas para o Supabase.

Para recolher dados oficiais, execute a partir da pasta backend:
  python -m scripts.sync_parliament deputies --legislature XVII --persist
  python -m scripts.sync_parliament votes --legislature XVII --persist
"""


def main() -> int:
    print(MESSAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
