"""Unit tests for app.domains.geo.intelligence.repository — data access layer.

All database calls are mocked. These tests verify query construction,
parameter passing, and result transformation logic.
"""

import uuid
from datetime import date, datetime
from unittest.mock import MagicMock, patch, call

import pytest

from app.domains.geo.intelligence.repository import IntelligenceRepository


@pytest.fixture
def repo():
    return IntelligenceRepository()


@pytest.fixture
def db():
    return MagicMock()


# ---------------------------------------------------------------------------
# ZonaOperativa CRUD
# ---------------------------------------------------------------------------


class TestGetZonas:
    def test_returns_items_and_total(self, repo, db):
        zona = MagicMock()
        db.execute.return_value.scalar_one.return_value = 1
        db.execute.return_value.scalars.return_value.all.return_value = [zona]

        items, total = repo.get_zonas(db, page=1, limit=50)
        assert total == 1
        assert items == [zona]

    def test_cuenca_filter(self, repo, db):
        db.execute.return_value.scalar_one.return_value = 0
        db.execute.return_value.scalars.return_value.all.return_value = []

        items, total = repo.get_zonas(db, cuenca_filter="cuenca_a")
        assert total == 0
        assert items == []

    def test_pagination(self, repo, db):
        db.execute.return_value.scalar_one.return_value = 100
        db.execute.return_value.scalars.return_value.all.return_value = []

        items, total = repo.get_zonas(db, page=3, limit=10)
        assert total == 100


class TestDeleteZonasByCuenca:
    def test_returns_count_deleted(self, repo, db):
        db.execute.return_value.rowcount = 5
        count = repo.delete_zonas_by_cuenca(db, "cuenca_test")
        assert count == 5
        db.flush.assert_called_once()


class TestGetZonasAsGeojson:
    def test_returns_feature_collection(self, repo, db):
        row = MagicMock()
        row.id = uuid.uuid4()
        row.nombre = "Zona 1"
        row.cuenca = "cuenca_a"
        row.superficie_ha = 100.0
        row.geojson = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'
        db.execute.return_value.all.return_value = [row]

        result = repo.get_zonas_as_geojson(db)
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 1
        assert result["features"][0]["properties"]["nombre"] == "Zona 1"
        assert result["metadata"]["total"] == 1

    def test_with_bbox_filter(self, repo, db):
        db.execute.return_value.all.return_value = []
        result = repo.get_zonas_as_geojson(db, bbox=(-60.0, -30.0, -59.0, -29.0))
        assert result["metadata"]["bbox"] == [-60.0, -30.0, -59.0, -29.0]

    def test_with_cuenca_filter(self, repo, db):
        db.execute.return_value.all.return_value = []
        result = repo.get_zonas_as_geojson(db, cuenca_filter="cuenca_b")
        assert result["type"] == "FeatureCollection"

    def test_null_geojson(self, repo, db):
        row = MagicMock()
        row.id = uuid.uuid4()
        row.nombre = "Zona X"
        row.cuenca = "c"
        row.superficie_ha = 0
        row.geojson = None
        db.execute.return_value.all.return_value = [row]

        result = repo.get_zonas_as_geojson(db)
        assert result["features"][0]["geometry"] is None


class TestGetZonasForGrouping:
    def test_returns_features_with_geometry(self, repo, db):
        row = MagicMock()
        row.id = uuid.uuid4()
        row.nombre = "Zona G"
        row.cuenca = "cuenca_g"
        row.superficie_ha = 50.0
        row.geojson = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'
        db.execute.return_value.all.return_value = [row]

        result = repo.get_zonas_for_grouping(db)
        assert len(result) == 1
        assert result[0]["type"] == "Feature"

    def test_skips_null_geometry(self, repo, db):
        row = MagicMock()
        row.id = uuid.uuid4()
        row.nombre = "Zona N"
        row.cuenca = "c"
        row.superficie_ha = 0
        row.geojson = None
        db.execute.return_value.all.return_value = [row]

        result = repo.get_zonas_for_grouping(db)
        assert len(result) == 0

    def test_with_cuenca_filter(self, repo, db):
        db.execute.return_value.all.return_value = []
        result = repo.get_zonas_for_grouping(db, cuenca_filter="cuenca_x")
        assert result == []


class TestGetZonasCriticas:
    def test_returns_zones_at_risk(self, repo, db):
        zona = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [zona]

        result = repo.get_zonas_criticas(db, nivel_riesgo_min="alto")
        assert result == [zona]

    def test_uses_default_nivel(self, repo, db):
        db.execute.return_value.scalars.return_value.all.return_value = []
        result = repo.get_zonas_criticas(db)
        assert result == []

    def test_unknown_nivel_defaults_to_alto(self, repo, db):
        db.execute.return_value.scalars.return_value.all.return_value = []
        result = repo.get_zonas_criticas(db, nivel_riesgo_min="unknown_level")
        assert result == []


# ---------------------------------------------------------------------------
# IndiceHidrico
# ---------------------------------------------------------------------------


class TestGetIndicesHidricos:
    def test_returns_paginated(self, repo, db):
        ih = MagicMock()
        db.execute.return_value.scalar_one.return_value = 1
        db.execute.return_value.scalars.return_value.all.return_value = [ih]

        items, total = repo.get_indices_hidricos(db)
        assert total == 1
        assert items == [ih]

    def test_with_zona_filter(self, repo, db):
        db.execute.return_value.scalar_one.return_value = 0
        db.execute.return_value.scalars.return_value.all.return_value = []

        items, total = repo.get_indices_hidricos(db, zona_id=uuid.uuid4())
        assert total == 0


# ---------------------------------------------------------------------------
# PuntoConflicto
# ---------------------------------------------------------------------------


class TestGetConflictos:
    def test_returns_paginated(self, repo, db):
        c = MagicMock()
        db.execute.return_value.scalar_one.return_value = 3
        db.execute.return_value.scalars.return_value.all.return_value = [c]

        items, total = repo.get_conflictos(db)
        assert total == 3

    def test_with_tipo_filter(self, repo, db):
        db.execute.return_value.scalar_one.return_value = 0
        db.execute.return_value.scalars.return_value.all.return_value = []
        items, total = repo.get_conflictos(db, tipo_filter="canal_road")
        assert total == 0

    def test_with_severidad_filter(self, repo, db):
        db.execute.return_value.scalar_one.return_value = 0
        db.execute.return_value.scalars.return_value.all.return_value = []
        items, total = repo.get_conflictos(db, severidad_filter="alta")
        assert total == 0


class TestGetConflictosPorZona:
    def test_returns_empty_when_zona_not_found(self, repo, db):
        with patch.object(repo, "get_zona_by_id", return_value=None):
            result = repo.get_conflictos_por_zona(db, uuid.uuid4())
            assert result == []

    def test_returns_conflicts_in_zone(self, repo, db):
        zona = MagicMock()
        conflict = MagicMock()
        with patch.object(repo, "get_zona_by_id", return_value=zona):
            db.execute.return_value.scalars.return_value.all.return_value = [conflict]
            result = repo.get_conflictos_por_zona(db, uuid.uuid4())
            assert result == [conflict]


class TestBulkCreateConflictos:
    def test_inserts_and_returns_count(self, repo, db):
        conflictos = [
            {"tipo": "a", "geometria": "POINT(0 0)", "descripcion": "d", "severidad": "alta"},
            {"tipo": "b", "geometria": "POINT(1 1)", "descripcion": "e", "severidad": "baja"},
        ]
        count = repo.bulk_create_conflictos(db, conflictos)
        assert count == 2
        db.add_all.assert_called_once()
        db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------


class TestAlertasCrud:
    def test_deactivate_alerta_found(self, repo, db):
        alerta = MagicMock(activa=True)
        db.execute.return_value.scalar_one_or_none.return_value = alerta

        result = repo.deactivate_alerta(db, uuid.uuid4())
        assert result.activa is False
        db.flush.assert_called_once()

    def test_deactivate_alerta_not_found(self, repo, db):
        db.execute.return_value.scalar_one_or_none.return_value = None
        result = repo.deactivate_alerta(db, uuid.uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestGetDashboardInteligente:
    def test_returns_dashboard_metrics(self, repo, db):
        # Mock multiple execute calls in sequence
        db.execute.return_value.scalar_one.side_effect = [10, 500.0, 2]
        db.execute.return_value.all.return_value = [
            MagicMock(nivel_riesgo="alto", **{"__iter__": lambda s: iter(("alto", 3))}),
        ]

        # More granular mock for the nivel counts
        mock_nivel_result = MagicMock()
        mock_nivel_result.all.return_value = [("alto", 3), ("bajo", 7)]

        call_count = [0]
        original_execute = db.execute

        def side_effect_execute(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one.return_value = 10  # zonas_total
            elif call_count[0] == 2:
                result.scalar_one.return_value = 500.0  # area_total
            elif call_count[0] == 3:
                result.all.return_value = [("alto", 3), ("bajo", 7)]  # nivel counts
            elif call_count[0] == 4:
                result.scalar_one.return_value = 5  # conflictos
            elif call_count[0] == 5:
                result.scalar_one.return_value = 2  # alertas
            return result

        db.execute = MagicMock(side_effect=side_effect_execute)

        result = repo.get_dashboard_inteligente(db)
        assert "porcentaje_area_riesgo" in result
        assert "conflictos_activos" in result
        assert "alertas_activas" in result
        assert "zonas_por_nivel" in result
        assert result["zonas_por_nivel"]["alto"] == 3
        assert result["zonas_por_nivel"]["bajo"] == 7

    def test_dashboard_zero_zones(self, repo, db):
        call_count = [0]

        def side_effect_execute(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one.return_value = 0
            elif call_count[0] == 2:
                result.scalar_one.return_value = 0.0
            elif call_count[0] == 3:
                result.all.return_value = []
            elif call_count[0] == 4:
                result.scalar_one.return_value = 0
            elif call_count[0] == 5:
                result.scalar_one.return_value = 0
            return result

        db.execute = MagicMock(side_effect=side_effect_execute)
        result = repo.get_dashboard_inteligente(db)
        assert result["porcentaje_area_riesgo"] == 0.0


# ---------------------------------------------------------------------------
# Materialized Views
# ---------------------------------------------------------------------------


class TestRefreshMaterializedViews:
    def test_all_views_succeed(self, repo, db):
        db.execute = MagicMock()
        result = repo.refresh_materialized_views(db)
        assert len(result) == 3
        assert all(v == "ok" for v in result.values())
        db.commit.assert_called_once()

    def test_concurrent_fails_then_normal_succeeds(self, repo, db):
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            sql = str(args[0]) if args else ""
            if "CONCURRENTLY" in sql:
                raise Exception("no data")
            return MagicMock()

        db.execute = MagicMock(side_effect=side_effect)
        db.rollback = MagicMock()

        result = repo.refresh_materialized_views(db)
        assert all("non-concurrent" in v or "ok" in v for v in result.values())

    def test_both_refresh_methods_fail(self, repo, db):
        db.execute = MagicMock(side_effect=Exception("total failure"))
        db.rollback = MagicMock()

        result = repo.refresh_materialized_views(db)
        assert all("error" in v for v in result.values())


class TestGetDashboardStats:
    def test_returns_dict_from_matview(self, repo, db):
        row = {"zonas_total": 10, "area_total": 500.0}
        db.execute.return_value.mappings.return_value.first.return_value = row

        result = repo.get_dashboard_stats(db)
        assert result == row

    def test_returns_empty_when_no_data(self, repo, db):
        db.execute.return_value.mappings.return_value.first.return_value = None
        result = repo.get_dashboard_stats(db)
        assert result == {}


class TestGetHciPorZona:
    def test_returns_paginated(self, repo, db):
        row = {
            "zona_id": str(uuid.uuid4()),
            "zona_nombre": "Z1",
            "cuenca": "c",
            "superficie_ha": 100.0,
            "indice_final": 0.8,
            "nivel_riesgo": "alto",
            "fecha_calculo": date.today(),
        }

        db.execute.return_value.scalar_one.return_value = 1
        db.execute.return_value.mappings.return_value.all.return_value = [row]

        items, total = repo.get_hci_por_zona(db)
        assert total == 1
        assert items == [row]

    def test_with_cuenca_filter(self, repo, db):
        db.execute.return_value.scalar_one.return_value = 0
        db.execute.return_value.mappings.return_value.all.return_value = []

        items, total = repo.get_hci_por_zona(db, cuenca_filter="cuenca_x")
        assert total == 0


class TestGetAlertasResumen:
    def test_returns_row(self, repo, db):
        row = {"total_alertas": 5, "activas": 3}
        db.execute.return_value.mappings.return_value.first.return_value = row
        result = repo.get_alertas_resumen(db)
        assert result == row

    def test_returns_empty(self, repo, db):
        db.execute.return_value.mappings.return_value.first.return_value = None
        result = repo.get_alertas_resumen(db)
        assert result == {}


# ---------------------------------------------------------------------------
# Composite Zonal Stats
# ---------------------------------------------------------------------------


class TestBulkUpsertCompositeStats:
    def test_empty_list_returns_zero(self, repo, db):
        count = repo.bulk_upsert_composite_stats(db, [])
        assert count == 0

    @patch("app.domains.geo.intelligence.repository.func")
    def test_upserts_stats(self, mock_func, repo, db):
        stats = [
            {
                "zona_id": uuid.uuid4(),
                "tipo": "flood_risk",
                "fecha_calculo": date.today(),
                "mean_score": 0.7,
                "max_score": 0.9,
                "p90_score": 0.85,
                "area_high_risk_ha": 50.0,
                "weights_used": {},
            }
        ]
        db.execute.return_value.rowcount = 1
        count = repo.bulk_upsert_composite_stats(db, stats)
        assert count == 1
        db.flush.assert_called_once()


class TestGetCompositeStatsByArea:
    def test_returns_items_for_area(self, repo, db):
        stat = MagicMock()
        db.execute.return_value.scalars.return_value.unique.return_value.all.return_value = [stat]

        result = repo.get_composite_stats_by_area(db, "cuenca_a")
        assert result == [stat]

    def test_returns_empty_for_nonexistent_area(self, repo, db):
        db.execute.return_value.scalars.return_value.unique.return_value.all.return_value = []
        result = repo.get_composite_stats_by_area(db, "nonexistent")
        assert result == []

    def test_with_tipo_filter(self, repo, db):
        db.execute.return_value.scalars.return_value.unique.return_value.all.return_value = []
        result = repo.get_composite_stats_by_area(db, "cuenca_a", tipo="flood_risk")
        assert result == []

    def test_zona_principal_fallback(self, repo, db):
        stat = MagicMock()
        # First call returns empty, second (fallback) returns data
        db.execute.return_value.scalars.return_value.unique.return_value.all.side_effect = [
            [],
            [stat],
        ]
        result = repo.get_composite_stats_by_area(db, "zona_principal")
        assert result == [stat]


# ---------------------------------------------------------------------------
# Canal Suggestions
# ---------------------------------------------------------------------------


class TestInsertSuggestionsBatch:
    def test_empty_returns_zero(self, repo, db):
        count = repo.insert_suggestions_batch(db, [])
        assert count == 0

    def test_inserts_batch(self, repo, db):
        suggestions = [
            {
                "tipo": "hotspot",
                "score": 0.9,
                "batch_id": uuid.uuid4(),
            }
        ]
        count = repo.insert_suggestions_batch(db, suggestions)
        assert count == 1
        db.add_all.assert_called_once()
        db.flush.assert_called_once()


class TestGetSuggestionsByTipo:
    def test_returns_paginated(self, repo, db):
        s = MagicMock()
        db.execute.return_value.scalar_one.return_value = 1
        db.execute.return_value.scalars.return_value.all.return_value = [s]

        items, total = repo.get_suggestions_by_tipo(db, "hotspot")
        assert total == 1
        assert items == [s]

    def test_with_batch_filter(self, repo, db):
        db.execute.return_value.scalar_one.return_value = 0
        db.execute.return_value.scalars.return_value.all.return_value = []
        items, total = repo.get_suggestions_by_tipo(db, "gap", batch_id=uuid.uuid4())
        assert total == 0


class TestGetLatestBatch:
    def test_returns_batch_id(self, repo, db):
        bid = uuid.uuid4()
        db.execute.return_value.scalar_one_or_none.return_value = bid
        result = repo.get_latest_batch(db)
        assert result == bid

    def test_returns_none_when_no_data(self, repo, db):
        db.execute.return_value.scalar_one_or_none.return_value = None
        result = repo.get_latest_batch(db)
        assert result is None


class TestGetSummary:
    def test_returns_summary(self, repo, db):
        batch_id = uuid.uuid4()
        # Mock get_latest_batch
        with patch.object(repo, "get_latest_batch", return_value=batch_id):
            agg = MagicMock()
            agg.total = 10
            agg.avg_score = 0.75
            agg.created_at = datetime.now()

            tipo_row = MagicMock()
            tipo_row.tipo = "hotspot"
            tipo_row.cnt = 5

            call_count = [0]

            def side_effect(*args, **kwargs):
                call_count[0] += 1
                result = MagicMock()
                if call_count[0] == 1:
                    result.one.return_value = agg
                elif call_count[0] == 2:
                    result.all.return_value = [tipo_row]
                return result

            db.execute = MagicMock(side_effect=side_effect)

            result = repo.get_summary(db)
            assert result["batch_id"] == batch_id
            assert result["total_suggestions"] == 10
            assert result["by_tipo"]["hotspot"] == 5

    def test_returns_none_when_no_batch(self, repo, db):
        with patch.object(repo, "get_latest_batch", return_value=None):
            result = repo.get_summary(db)
            assert result is None

    def test_returns_none_when_batch_empty(self, repo, db):
        batch_id = uuid.uuid4()
        agg = MagicMock()
        agg.total = 0

        db.execute.return_value.one.return_value = agg

        result = repo.get_summary(db, batch_id=batch_id)
        assert result is None
