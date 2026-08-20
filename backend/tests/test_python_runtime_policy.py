from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_python_runtime_policy import collect_runtime_policy_failures

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _write_valid_policy(repository_root: Path) -> None:
    workflow_root = repository_root / ".github" / "workflows"
    backend_root = repository_root / "backend"
    workflow_root.mkdir(parents=True)
    backend_root.mkdir(parents=True)

    (repository_root / ".python-version").write_text("3.13.15\n", encoding="utf-8")
    (workflow_root / "ci.yml").write_text(
        """jobs:
  test:
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version-file: .python-version
          cache: pip
""",
        encoding="utf-8",
    )
    (backend_root / "pyproject.toml").write_text(
        """[project]
requires-python = ">=3.13,<3.14"

[tool.ruff]
target-version = "py313"

[tool.mypy]
python_version = "3.13"
""",
        encoding="utf-8",
    )
    (backend_root / "Dockerfile").write_text(
        "FROM python:3.13.15-slim AS runtime\n",
        encoding="utf-8",
    )
    (repository_root / "render.yaml").write_text(
        """services:
  - type: web
    envVars:
      - key: PYTHON_VERSION
        value: 3.13.15
""",
        encoding="utf-8",
    )


class PythonRuntimePolicyTests(unittest.TestCase):
    def test_repository_has_no_runtime_drift(self) -> None:
        self.assertEqual(collect_runtime_policy_failures(REPOSITORY_ROOT), [])

    def test_valid_policy_accepts_the_exact_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root = Path(temporary_directory)
            _write_valid_policy(repository_root)

            failures = collect_runtime_policy_failures(
                repository_root,
                interpreter_version=(3, 13, 15),
            )

        self.assertEqual(failures, [])

    def test_direct_workflow_version_and_interpreter_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root = Path(temporary_directory)
            _write_valid_policy(repository_root)
            workflow = repository_root / ".github" / "workflows" / "ci.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "python-version-file: .python-version",
                    'python-version: "3.12"',
                ),
                encoding="utf-8",
            )

            failures = collect_runtime_policy_failures(
                repository_root,
                interpreter_version=(3, 14, 0),
            )

        self.assertTrue(any("define python-version diretamente" in item for item in failures))
        self.assertTrue(any("python-version-file: .python-version" in item for item in failures))
        self.assertTrue(any("intérprete ativo é Python 3.14.0" in item for item in failures))

    def test_production_and_tooling_drift_are_reported_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root = Path(temporary_directory)
            _write_valid_policy(repository_root)
            (repository_root / "render.yaml").write_text(
                """services:
  - envVars:
      - key: PYTHON_VERSION
        value: 3.13.5
""",
                encoding="utf-8",
            )
            (repository_root / "backend" / "Dockerfile").write_text(
                "FROM python:3.13-slim AS runtime\n",
                encoding="utf-8",
            )
            pyproject = repository_root / "backend" / "pyproject.toml"
            pyproject.write_text(
                pyproject.read_text(encoding="utf-8")
                .replace('requires-python = ">=3.13,<3.14"', 'requires-python = ">=3.12"')
                .replace('target-version = "py313"', 'target-version = "py312"')
                .replace('python_version = "3.13"', 'python_version = "3.12"'),
                encoding="utf-8",
            )

            failures = collect_runtime_policy_failures(repository_root)

        joined_failures = "\n".join(failures)
        self.assertIn("render.yaml", joined_failures)
        self.assertIn("backend/Dockerfile", joined_failures)
        self.assertIn("requires-python", joined_failures)
        self.assertIn("Ruff", joined_failures)
        self.assertIn("mypy", joined_failures)

    def test_canonical_file_cannot_silently_change_python_series(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository_root = Path(temporary_directory)
            _write_valid_policy(repository_root)
            (repository_root / ".python-version").write_text("3.14.1\n", encoding="utf-8")

            failures = collect_runtime_policy_failures(repository_root)

        self.assertTrue(any("série suportada 3.13" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
