"""Unit tests for per-view transaction isolation in refresh_materialized_views."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domains.geo.intelligence.repository import IntelligenceRepository


def test_refresh_materialized_views_commits_each_view_and_includes_parcelas() -> None:
    repo = IntelligenceRepository()
    executed_sql: list[str] = []
    commits = 0
    rollbacks = 0

    class FakeSession:
        def execute(self, statement, params=None):
            sql = str(statement)
            executed_sql.append(sql)
            if "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_hci_por_zona" in sql:
                raise RuntimeError("concurrent refresh requires unique index")
            if "mv_alertas_resumen" in sql:
                raise RuntimeError("broken view")
            return MagicMock()

        def commit(self):
            nonlocal commits
            commits += 1

        def rollback(self):
            nonlocal rollbacks
            rollbacks += 1

    session = FakeSession()
    results = repo.refresh_materialized_views(session)  # type: ignore[arg-type]

    assert set(results.keys()) == {
        "mv_dashboard_geo_stats",
        "mv_hci_por_zona",
        "mv_alertas_resumen",
        "mv_caminos_unificados",
        "vt_parcelas_catastro",
    }
    assert results["mv_dashboard_geo_stats"] == "ok"
    assert results["mv_hci_por_zona"] == "ok (non-concurrent)"
    assert results["mv_alertas_resumen"].startswith("error:")
    assert results["mv_caminos_unificados"] == "ok"
    assert results["vt_parcelas_catastro"] == "ok"

    # 4 views succeeded (1 fallback), 1 failed both attempts -> 4 commits, 3 rollbacks.
    assert commits == 4
    assert rollbacks == 3

    timeout_calls = [s for s in executed_sql if "set_config('statement_timeout'" in s]
    # Applied before each of the 5 views + re-applied on each of the 2 fallback attempts.
    assert len(timeout_calls) == 7
