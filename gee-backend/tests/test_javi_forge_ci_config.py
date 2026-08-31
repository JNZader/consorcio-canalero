"""Issue #164: hybrid pre-push must not auto-detect the root as Node-only."""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _ci_config() -> dict:
    loaded = yaml.safe_load(_read(".javi-forge/ci.yaml"))
    assert isinstance(loaded, dict)
    return loaded


def _runner(name: str) -> dict:
    runners = _ci_config()["runners"]
    match = next((item for item in runners if item.get("name") == name), None)
    assert match is not None, f"runner {name!r} is missing"
    return match


def _commands(runner: dict, field: str) -> list[str]:
    value = runner.get(field, [])
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    assert isinstance(value, list)
    return [str(item) for item in value]


def test_ci_yaml_declares_frontend_and_backend_runners() -> None:
    frontend = _runner("frontend")
    backend = _runner("backend")
    assert frontend["stack"] == "node"
    assert frontend["directory"] == "consorcio-web"
    assert backend["stack"] == "python"
    assert backend["directory"] == "gee-backend"


def test_ci_yaml_compile_is_typecheck_not_vite_build() -> None:
    """Assert the frontend *build* commands, not comments.

    The YAML documents 'never vite build' in a comment. A whole-file substring
    check collides with that prose and greens a regression that reintroduces
    `npm run build` as long as the comment stays.
    """
    build_cmds = _commands(_runner("frontend"), "build")
    joined = "\n".join(build_cmds)
    assert build_cmds == ["npm run typecheck"]
    assert "npm run build" not in joined
    assert "vite" not in joined


def test_ci_yaml_backend_test_is_not_a_skip_echo() -> None:
    test_cmds = _commands(_runner("backend"), "test")
    joined = "\n".join(test_cmds)
    assert "skipped in pre-push" not in joined
    assert "pytest tests/test_ci_workflow_contracts.py" in joined
    assert "tests/test_javi_forge_ci_config.py" in joined


def test_pre_push_hook_always_runs_native_quick() -> None:
    """Docker-up used to pick a Node image with no Make/Python (#164)."""
    text = _read(".ci-local/hooks/pre-push")
    assert "javi-forge ci --quick --no-docker --no-security --no-ci-ghagga" in text
    assert "docker info" not in text


def test_install_hooks_targets_git_common_dir() -> None:
    text = _read("Makefile")
    _, _, install_block = text.partition("install-hooks:")
    next_target = install_block.find("\n#")
    if next_target != -1:
        install_block = install_block[:next_target]
    assert "git rev-parse --git-common-dir" in install_block
    assert ".ci-local/hooks/pre-push" in install_block


def test_test_local_reaches_frontend_when_python_is_missing() -> None:
    text = _read("scripts/test-local.sh")
    python_block, _, frontend_block = text.partition("npm run test:run")
    assert frontend_block != ""
    assert "exit 127" not in python_block
    assert "backend_rc=127" in python_block
    assert "frontend_rc" in text
    assert "npm run test\n" not in text


def test_build_local_fails_closed_when_make_is_missing() -> None:
    text = _read("scripts/build-local.sh")
    assert "command -v make" in text
    assert "exit 127" in text
