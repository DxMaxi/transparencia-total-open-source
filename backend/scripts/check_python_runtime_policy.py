from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_SERIES = (3, 13)
SUPPORTED_REQUIREMENT = ">=3.13,<3.14"
RUFF_TARGET = "py313"
MYPY_TARGET = "3.13"
VERSION_PATTERN = re.compile(r"(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)")
SETUP_PYTHON_PATTERN = re.compile(r"^(?P<indent>\s*)-\s+uses:\s+actions/setup-python@")
STEP_PATTERN = re.compile(r"^(?P<indent>\s*)-\s+")


def _canonical_version(repository_root: Path, failures: list[str]) -> str | None:
    version_file = repository_root / ".python-version"
    try:
        raw_version = version_file.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f".python-version não pôde ser lido: {exc}")
        return None

    version = raw_version.strip()
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        failures.append(".python-version deve conter uma versão exata no formato X.Y.Z")
        return None

    if raw_version != f"{version}\n":
        failures.append(".python-version deve conter apenas a versão exata e uma quebra de linha")

    series = (int(match["major"]), int(match["minor"]))
    if series != SUPPORTED_SERIES:
        failures.append(
            ".python-version saiu da série suportada 3.13; uma mudança de série exige "
            "alterar deliberadamente o contrato"
        )
    return version


def _check_pyproject(repository_root: Path, failures: list[str]) -> None:
    pyproject_path = repository_root / "backend" / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        failures.append(f"backend/pyproject.toml não pôde ser validado: {exc}")
        return

    checks = (
        (
            pyproject.get("project", {}).get("requires-python"),
            SUPPORTED_REQUIREMENT,
            "requires-python",
        ),
        (pyproject.get("tool", {}).get("ruff", {}).get("target-version"), RUFF_TARGET, "Ruff"),
        (
            pyproject.get("tool", {}).get("mypy", {}).get("python_version"),
            MYPY_TARGET,
            "mypy",
        ),
    )
    for actual, expected, label in checks:
        if actual != expected:
            failures.append(
                f"backend/pyproject.toml: {label} deve ser {expected!r}, encontrado {actual!r}"
            )


def _check_render(repository_root: Path, version: str, failures: list[str]) -> None:
    render_path = repository_root / "render.yaml"
    try:
        render_text = render_path.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"render.yaml não pôde ser lido: {exc}")
        return

    values = re.findall(
        r"(?m)^\s*-\s+key:\s*PYTHON_VERSION\s*$\n^\s+value:\s*([^\s#]+)\s*$",
        render_text,
    )
    normalized_values = [value.strip("'\"") for value in values]
    if normalized_values != [version]:
        failures.append(
            "render.yaml: PYTHON_VERSION deve existir uma vez e coincidir com "
            f".python-version ({version}); encontrado {normalized_values!r}"
        )


def _check_docker(repository_root: Path, version: str, failures: list[str]) -> None:
    dockerfile_path = repository_root / "backend" / "Dockerfile"
    try:
        dockerfile_lines = dockerfile_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        failures.append(f"backend/Dockerfile não pôde ser lido: {exc}")
        return

    python_from_lines = [
        line.strip() for line in dockerfile_lines if line.lstrip().startswith("FROM python:")
    ]
    expected = f"FROM python:{version}-slim AS runtime"
    if python_from_lines != [expected]:
        failures.append(
            "backend/Dockerfile: a imagem Python deve existir uma vez e ser "
            f"{expected!r}; encontrado {python_from_lines!r}"
        )


def _setup_python_blocks(workflow_text: str) -> list[str]:
    lines = workflow_text.splitlines()
    blocks: list[str] = []
    for index, line in enumerate(lines):
        setup_match = SETUP_PYTHON_PATTERN.match(line)
        if setup_match is None:
            continue

        setup_indent = len(setup_match["indent"])
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            step_match = STEP_PATTERN.match(lines[next_index])
            if step_match is not None and len(step_match["indent"]) <= setup_indent:
                end = next_index
                break
        blocks.append("\n".join(lines[index:end]))
    return blocks


def _check_workflows(repository_root: Path, failures: list[str]) -> None:
    workflow_root = repository_root / ".github" / "workflows"
    workflow_paths = sorted({*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")})
    setup_step_count = 0

    for workflow_path in workflow_paths:
        try:
            workflow_text = workflow_path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(
                f"{workflow_path.relative_to(repository_root)} não pôde ser lido: {exc}"
            )
            continue

        blocks = _setup_python_blocks(workflow_text)
        if not blocks:
            continue

        relative_path = workflow_path.relative_to(repository_root).as_posix()
        if "actions/checkout@" not in workflow_text:
            failures.append(
                f"{relative_path}: actions/setup-python precisa de checkout para ler "
                ".python-version"
            )

        for block_index, block in enumerate(blocks, start=1):
            setup_step_count += 1
            if re.search(r"(?m)^\s+python-version\s*:", block):
                failures.append(
                    f"{relative_path}: setup-python #{block_index} ainda define "
                    "python-version diretamente"
                )
            if re.search(
                r"(?m)^\s+python-version-file:\s*['\"]?\.python-version['\"]?\s*$",
                block,
            ) is None:
                failures.append(
                    f"{relative_path}: setup-python #{block_index} deve usar "
                    "python-version-file: .python-version"
                )

    if setup_step_count == 0:
        failures.append("nenhum passo actions/setup-python foi encontrado nos workflows")


def collect_runtime_policy_failures(
    repository_root: Path,
    *,
    interpreter_version: tuple[int, int, int] | None = None,
) -> list[str]:
    failures: list[str] = []
    version = _canonical_version(repository_root, failures)
    _check_pyproject(repository_root, failures)
    _check_workflows(repository_root, failures)

    if version is not None:
        _check_render(repository_root, version, failures)
        _check_docker(repository_root, version, failures)
        if interpreter_version is not None and interpreter_version != tuple(
            int(part) for part in version.split(".")
        ):
            actual = ".".join(str(part) for part in interpreter_version)
            failures.append(
                f"o intérprete ativo é Python {actual}, mas a política exige Python {version}"
            )
    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida a paridade do runtime Python entre CI, produção e ferramentas."
    )
    parser.add_argument(
        "--check-interpreter",
        action="store_true",
        help="exige que o intérprete ativo coincida com a revisão exata canónica",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    interpreter_version = tuple(sys.version_info[:3]) if args.check_interpreter else None
    failures = collect_runtime_policy_failures(
        REPOSITORY_ROOT,
        interpreter_version=interpreter_version,
    )
    if failures:
        print("POLITICA_RUNTIME_PYTHON_INVALIDA")
        for failure in failures:
            print(f"- {failure}")
        return 1

    version = (REPOSITORY_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    print(f"POLITICA_RUNTIME_PYTHON_VALIDA: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
