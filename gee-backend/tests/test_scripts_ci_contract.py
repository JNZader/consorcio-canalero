"""INF-1: scripts/tests is a workflow, not a directory nobody runs."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend.yml"


def test_backend_workflow_runs_scripts_tests_outside_the_integration_marker() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "name: scripts/tests" in text
    assert 'pytest -c scripts/pytest.ini scripts/tests -m "not integration"' in text
    assert "needs.changes.outputs.scripts == 'true'" in text
