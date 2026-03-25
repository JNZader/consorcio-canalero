"""
Tests for Phase 4: Materialized views and refresh logic.

Validates SQL strings are syntactically reasonable and that the
refresh_materialized_views method exists with the expected signature.
"""

import inspect

from app.domains.geo.intelligence.repository import IntelligenceRepository


# ── SQL Validity ────────────────────────────────────


class TestMaterializedViewSQL:
    """Test that MV SQL strings are valid and reference correct tables."""

    @staticmethod
    def _get_mv_sql_strings() -> dict[str, str]:
        """Import the SQL constants from the migration module."""
        from app.db.migrations.versions.k5f2g1h2i361_add_geo_materialized_views import (
            MV_ALERTAS_RESUMEN,
            MV_DASHBOARD_GEO_STATS,
            MV_HCI_POR_ZONA,
        )

        return {
            "mv_dashboard_geo_stats": MV_DASHBOARD_GEO_STATS,
            "mv_hci_por_zona": MV_HCI_POR_ZONA,
            "mv_alertas_resumen": MV_ALERTAS_RESUMEN,
        }

    def test_all_mv_sql_starts_with_create_materialized_view(self):
        """Each MV SQL string should start with CREATE MATERIALIZED VIEW."""
        for name, sql in self._get_mv_sql_strings().items():
            stripped = sql.strip().upper()
            assert stripped.startswith(
                "CREATE MATERIALIZED VIEW"
            ), f"{name} does not start with CREATE MATERIALIZED VIEW"

    def test_all_mv_sql_contains_select(self):
        """Each MV SQL should contain a SELECT statement."""
        for name, sql in self._get_mv_sql_strings().items():
            assert "SELECT" in sql.upper(), f"{name} has no SELECT"

    def test_all_mv_sql_has_balanced_parentheses(self):
        """Basic check that parentheses are balanced."""
        for name, sql in self._get_mv_sql_strings().items():
            open_count = sql.count("(")
            close_count = sql.count(")")
            assert open_count == close_count, (
                f"{name} has unbalanced parentheses: {open_count} open, {close_count} close"
            )

    def test_mv_dashboard_references_expected_tables(self):
        """Dashboard MV should reference geo_layers, geo_jobs, geo_analisis_gee."""
        sql_map = self._get_mv_sql_strings()
        sql = sql_map["mv_dashboard_geo_stats"].lower()
        assert "geo_layers" in sql
        assert "geo_jobs" in sql
        assert "geo_analisis_gee" in sql
        assert "zonas_operativas" in sql
        assert "alertas_geo" in sql

    def test_mv_hci_references_expected_tables(self):
        """HCI MV should reference zonas_operativas and indices_hidricos."""
        sql_map = self._get_mv_sql_strings()
        sql = sql_map["mv_hci_por_zona"].lower()
        assert "zonas_operativas" in sql
        assert "indices_hidricos" in sql

    def test_mv_alertas_references_alertas_geo(self):
        """Alertas MV should reference alertas_geo with activa filter."""
        sql_map = self._get_mv_sql_strings()
        sql = sql_map["mv_alertas_resumen"].lower()
        assert "alertas_geo" in sql
        assert "activa" in sql


# ── Repository method signature ─────────────────────


class TestRefreshMaterializedViews:
    """Test that refresh_materialized_views method exists with correct sig."""

    def test_method_exists(self):
        repo = IntelligenceRepository()
        assert hasattr(repo, "refresh_materialized_views")
        assert callable(repo.refresh_materialized_views)

    def test_method_accepts_db_session(self):
        sig = inspect.signature(IntelligenceRepository.refresh_materialized_views)
        params = list(sig.parameters.keys())
        # First param is self, second is db
        assert "db" in params

    def test_method_refreshes_three_views(self):
        """The method body references exactly 3 materialized view names."""
        source = inspect.getsource(IntelligenceRepository.refresh_materialized_views)
        assert "mv_dashboard_geo_stats" in source
        assert "mv_hci_por_zona" in source
        assert "mv_alertas_resumen" in source
