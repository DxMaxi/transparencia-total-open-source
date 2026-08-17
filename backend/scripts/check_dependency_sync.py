from __future__ import annotations

import difflib
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PYPROJECT = BACKEND / "pyproject.toml"
REQUIREMENTS = BACKEND / "requirements.txt"


def main() -> int:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    expected = [str(item).strip() for item in data["project"]["dependencies"]]

    actual = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    if actual == expected:
        print("DEPENDENCIAS_PYTHON_SINCRONIZADAS")
        return 0

    diff = difflib.unified_diff(
        [f"{item}\n" for item in expected],
        [f"{item}\n" for item in actual],
        fromfile="pyproject.toml [project.dependencies]",
        tofile="requirements.txt",
    )
    print("requirements.txt divergiu de backend/pyproject.toml:")
    print("".join(diff), end="")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
