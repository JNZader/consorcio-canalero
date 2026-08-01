"""Ledger regression tests for the soils ETL packaging (JDB-002, JD-A-011).

JDB-002 was a BLOCKER: the first design put the loader in ``scripts/``, which
``gee-backend/Dockerfile:107`` never copies into the runtime image — the script
would have been unrunnable in every deployed environment. These tests are the
guard against that regression coming back:

* the loader resolves its source through ``importlib.resources``, never a
  repo-relative path (the repo does not exist inside the container);
* the module really is runnable as ``python -m …`` in a fresh interpreter;
* the packaged geojson is byte-identical to the frontend artifact it was copied
  from, so the two never drift apart silently (JD-A-011).

No database is touched here on purpose: this is about the image, not the data.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from app.domains.geo.etl import load_suelos_catastro as loader
from tests.new._suelos_fixtures import SOURCE_FEATURE_COUNT

#: ``tests/new/x.py`` → ``tests/new`` → ``tests`` → ``gee-backend`` → repo root.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_COPY = REPO_ROOT / "consorcio-web" / "public" / "data" / "suelos_cu.geojson"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestPackagedSource:
    """spec soils-etl › "Loader runs inside the deployed container"."""

    def test_default_source_resolves_inside_the_package(self):
        resolved = loader.resolve_source(None)

        assert resolved.is_file(), f"la copia empaquetada no existe: {resolved}"
        package_dir = Path(loader.__file__).resolve().parent
        assert resolved.resolve().is_relative_to(package_dir), (
            "el origen por defecto quedó fuera de app/domains/geo/etl/ — no viajaría "
            f"en la imagen: {resolved}"
        )

    def test_packaged_source_parses_as_a_feature_collection(self):
        features = loader.read_source(loader.resolve_source(None))

        assert len(features) == SOURCE_FEATURE_COUNT
        # The coercion that assertion 5 exists for, visible at parse time.
        assert all(f.ip is None or isinstance(f.ip, str) for f in features)

    def test_loader_code_never_reaches_for_the_repo(self):
        """A repo-relative path is exactly the JDB-002 bug.

        The module docstring *documents* the repo layout (that is its job), so
        the grep runs over the code with the module docstring stripped — what
        matters is that no executable path construction points outside the
        package.
        """
        tree = ast.parse(Path(loader.__file__).read_text(encoding="utf-8"))
        body = tree.body[1:] if ast.get_docstring(tree) else tree.body
        code = ast.unparse(ast.Module(body=body, type_ignores=[]))

        offenders = [
            token for token in ("consorcio-web", "parents[", "../", "gee-backend/") if token in code
        ]
        assert not offenders, f"el loader referencia rutas del repo: {offenders}"

    def test_explicit_source_must_exist(self):
        """An invocation error, not a load abort — hence ``EtlUsageError``."""
        with pytest.raises(loader.EtlUsageError, match="--source no existe"):
            loader.resolve_source("/no/existe/suelos.geojson")


class TestModuleInvocation:
    """The documented invocation is ``python -m`` — prove it in a real process."""

    def test_module_runs_as_python_m(self):
        result = subprocess.run(
            [sys.executable, "-m", "app.domains.geo.etl.load_suelos_catastro", "--help"],
            cwd=BACKEND_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
        assert "--check-prereqs" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--source" in result.stdout
        assert "--force" in result.stdout

    def test_docstring_documents_the_container_invocation(self):
        """A1b.9: the operator command lives with the code, not in a lost PR body."""
        assert "docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro" in (
            loader.__doc__ or ""
        )

    # The flag-combination contract (``--check-prereqs`` vs the load flags) is
    # pinned once in ``test_ficha_migration.TestCheckPrereqs`` — not duplicated
    # here, where the subject is the packaging.


class TestDriftGuard:
    """JD-A-011: the packaged copy and the frontend artifact are one file."""

    def test_packaged_copy_is_byte_identical_to_the_frontend_artifact(self):
        packaged = loader.resolve_source(None)

        assert FRONTEND_COPY.is_file(), f"no está el original del frontend: {FRONTEND_COPY}"
        assert _sha256(packaged) == _sha256(FRONTEND_COPY), (
            "la copia empaquetada derivó del artefacto del frontend: volver a copiar "
            f"{FRONTEND_COPY} sobre {packaged}"
        )
