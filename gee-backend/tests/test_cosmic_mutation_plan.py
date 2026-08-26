from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PLANNER = BACKEND / "scripts/cosmic_mutation_plan.py"
MANIFEST = BACKEND / "scripts/cosmic_mutation_targets.json"


def _plan(
    tmp_path: Path, contents: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    tmp_path.mkdir(exist_ok=True)
    status, output = tmp_path / "changed.txt", tmp_path / "github-output.txt"
    status.write_text(contents, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(PLANNER),
            "--manifest",
            str(MANIFEST),
            "--status-file",
            str(status),
            "--github-output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, json.loads(output.read_text(encoding="utf-8").split("=", 1)[1])


def _targets(payload: dict[str, object]) -> list[str]:
    return [entry["target"] for entry in payload["include"]]  # type: ignore[index]


def test_owned_domain_change_selects_only_its_mutation_target(tmp_path: Path) -> None:
    result, payload = _plan(tmp_path, "M\tgee-backend/app/domains/padron/repository.py\n")
    assert result.returncode == 0, result.stderr
    assert _targets(payload) == ["padron-service"]


def test_multiple_owned_domains_select_their_exact_targets(tmp_path: Path) -> None:
    result, payload = _plan(
        tmp_path,
        "M\tgee-backend/app/domains/denuncias/router.py\nA\tgee-backend/app/domains/finanzas/helpers.py\n",
    )
    assert result.returncode == 0, result.stderr
    assert _targets(payload) == ["denuncias-service", "finanzas-service"]


def test_tests_config_workflow_and_unknown_backend_paths_fail_closed(tmp_path: Path) -> None:
    for index, path in enumerate(
        [
            "gee-backend/tests/test_mutation_targets_padron.py",
            "gee-backend/requirements.lock",
            ".github/workflows/backend.yml",
            "gee-backend/app/domains/geo/rainfall/policy.py",
        ]
    ):
        result, payload = _plan(tmp_path / str(index), f"M\t{path}\n")
        assert result.returncode == 0, result.stderr
        assert len(_targets(payload)) == 5


def test_renamed_or_deleted_path_fails_closed(tmp_path: Path) -> None:
    result, payload = _plan(
        tmp_path,
        "R100\tgee-backend/app/domains/padron/service.py\tgee-backend/app/domains/padron/renamed.py\n",
    )
    assert result.returncode == 0, result.stderr
    assert len(_targets(payload)) == 5


def test_default_manifest_is_script_relative_when_run_from_the_repo_root(
    tmp_path: Path,
) -> None:
    """Regression for the backend.yml `Detect changed areas` failure.

    The workflow invokes ``python3 gee-backend/scripts/cosmic_mutation_plan.py``
    from the repository root WITHOUT ``--manifest``. A cwd-relative default
    resolved to ``scripts/cosmic_mutation_targets.json`` at the repo root and
    failed closed with ``[Errno 2] No such file or directory``.
    """
    status, output = tmp_path / "changed.txt", tmp_path / "github-output.txt"
    status.write_text("M\tgee-backend/app/domains/padron/repository.py\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(PLANNER),
            "--status-file",
            str(status),
            "--github-output",
            str(output),
        ],
        cwd=BACKEND.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8").split("=", 1)[1])
    assert _targets(payload) == ["padron-service"]


def test_target_config_uses_manifest_module_and_focused_tests(tmp_path: Path) -> None:
    config = tmp_path / "selected.toml"
    result = subprocess.run(
        [
            sys.executable,
            str(PLANNER),
            "--manifest",
            str(MANIFEST),
            "--target",
            "tramites-schemas",
            "--write-config",
            str(config),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = config.read_text(encoding="utf-8")
    assert '"app/domains/tramites/schemas.py"' in rendered
    assert "tests/test_tramites_schema.py tests/test_mutation_targets.py" in rendered
