"""
Tests for the operational intelligence sub-module.

Covers:
- HCI formula with known inputs
- HCI edge cases (all zeros, all max, custom weights)
- Risk level classification
- Conflict detection logic with mock geometries
- Dynamic terrain classification rules
- Repository CRUD operations
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.domains.geo.intelligence.calculations import (
    DEFAULT_HCI_WEIGHTS,
    _clasificar_severidad_conflicto,
    calcular_indice_criticidad_hidrica,
    clasificar_nivel_riesgo,
    clasificar_terreno_dinamico,
)


# ══════════════════════════════════════════════
# HCI Formula Tests
# ══════════════════════════════════════════════


class TestCalcularIndiceCriticidadHidrica:
    """Tests for the Hydric Criticality Index calculation."""

    def test_known_inputs_default_weights(self):
        """All inputs at 0.5 with default weights → 50.0."""
        result = calcular_indice_criticidad_hidrica(
            pendiente=0.5,
            acumulacion=0.5,
            twi=0.5,
            dist_canal=0.5,
            hist_inundacion=0.5,
        )
        # 0.5 * (0.15+0.30+0.25+0.15+0.15) = 0.5 * 1.0 = 0.5 → 50.0
        assert result == 50.0

    def test_all_zeros(self):
        """All inputs at 0 → 0.0."""
        result = calcular_indice_criticidad_hidrica(
            pendiente=0.0,
            acumulacion=0.0,
            twi=0.0,
            dist_canal=0.0,
            hist_inundacion=0.0,
        )
        assert result == 0.0

    def test_all_max(self):
        """All inputs at 1.0 → 100.0."""
        result = calcular_indice_criticidad_hidrica(
            pendiente=1.0,
            acumulacion=1.0,
            twi=1.0,
            dist_canal=1.0,
            hist_inundacion=1.0,
        )
        assert result == 100.0

    def test_custom_weights(self):
        """Custom weights produce expected result."""
        custom = {
            "pendiente": 0.50,
            "acumulacion": 0.50,
            "twi": 0.0,
            "dist_canal": 0.0,
            "hist_inundacion": 0.0,
        }
        result = calcular_indice_criticidad_hidrica(
            pendiente=0.8,
            acumulacion=0.6,
            twi=0.9,
            dist_canal=0.1,
            hist_inundacion=0.5,
            pesos=custom,
        )
        # 0.50*0.8 + 0.50*0.6 + 0 + 0 + 0 = 0.4 + 0.3 = 0.7 → 70.0
        assert result == 70.0

    def test_heavy_acumulacion_weight(self):
        """When accumulation weight dominates, result reflects that."""
        custom = {
            "pendiente": 0.0,
            "acumulacion": 1.0,
            "twi": 0.0,
            "dist_canal": 0.0,
            "hist_inundacion": 0.0,
        }
        result = calcular_indice_criticidad_hidrica(
            pendiente=1.0,
            acumulacion=0.3,
            twi=1.0,
            dist_canal=1.0,
            hist_inundacion=1.0,
            pesos=custom,
        )
        assert result == 30.0

    def test_result_clamped_to_100(self):
        """Even with weights > 1.0 total, result is capped at 100."""
        huge_weights = {
            "pendiente": 1.0,
            "acumulacion": 1.0,
            "twi": 1.0,
            "dist_canal": 1.0,
            "hist_inundacion": 1.0,
        }
        result = calcular_indice_criticidad_hidrica(
            pendiente=1.0,
            acumulacion=1.0,
            twi=1.0,
            dist_canal=1.0,
            hist_inundacion=1.0,
            pesos=huge_weights,
        )
        assert result == 100.0

    def test_result_is_float(self):
        """Result is always a float."""
        result = calcular_indice_criticidad_hidrica(
            pendiente=0.33,
            acumulacion=0.67,
            twi=0.5,
            dist_canal=0.2,
            hist_inundacion=0.1,
        )
        assert isinstance(result, float)

    def test_default_weights_sum_to_one(self):
        """Default weights must sum to 1.0."""
        total = sum(DEFAULT_HCI_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-10

    @pytest.mark.parametrize(
        "pendiente,acumulacion,twi,dist_canal,hist,expected_min,expected_max",
        [
            (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0, 1.0, 1.0, 100.0, 100.0),
            (0.1, 0.2, 0.3, 0.4, 0.5, 0.0, 100.0),
            (0.0, 1.0, 0.0, 0.0, 0.0, 20.0, 40.0),
        ],
    )
    def test_parametrized_ranges(
        self, pendiente, acumulacion, twi, dist_canal, hist, expected_min, expected_max
    ):
        """HCI result falls within expected range."""
        result = calcular_indice_criticidad_hidrica(
            pendiente, acumulacion, twi, dist_canal, hist
        )
        assert expected_min <= result <= expected_max


# ══════════════════════════════════════════════
# Risk Level Classification Tests
# ══════════════════════════════════════════════


class TestClasificarNivelRiesgo:
    """Tests for risk level classification."""

    @pytest.mark.parametrize(
        "indice,expected",
        [
            (0.0, "bajo"),
            (10.0, "bajo"),
            (24.99, "bajo"),
            (25.0, "medio"),
            (49.99, "medio"),
            (50.0, "alto"),
            (74.99, "alto"),
            (75.0, "critico"),
            (100.0, "critico"),
        ],
    )
    def test_classification_boundaries(self, indice, expected):
        """Each boundary is correctly classified."""
        assert clasificar_nivel_riesgo(indice) == expected


# ══════════════════════════════════════════════
# Conflict Severity Tests
# ══════════════════════════════════════════════


class TestClasificarSeveridadConflicto:
    """Tests for conflict severity classification."""

    @pytest.mark.parametrize(
        "acumulacion,pendiente,expected",
        [
            (6000, 1.0, "alta"),      # Very high accumulation
            (100, 0.3, "alta"),        # Very low slope
            (3000, 3.0, "media"),      # Medium accumulation
            (100, 1.5, "media"),       # Low slope
            (1000, 3.0, "baja"),       # Normal values
        ],
    )
    def test_severity_classification(self, acumulacion, pendiente, expected):
        assert _clasificar_severidad_conflicto(acumulacion, pendiente) == expected


# ══════════════════════════════════════════════
# Dynamic Terrain Classification Tests
# ══════════════════════════════════════════════


class TestClasificarTerrenoDinamico:
    """Tests for multi-sensor terrain classification."""

    def test_empty_inputs(self):
        """All None inputs return empty result."""
        result = clasificar_terreno_dinamico(None, None, None)
        assert result["clases"] == {}
        assert result["estadisticas"] == {}

    def test_sar_water_detection(self):
        """SAR values < -15 dB are classified as water."""
        sar = np.array([[-20.0, -10.0], [-18.0, -5.0]])
        result = clasificar_terreno_dinamico(sar, None, None)

        classified = result["clasificacion"]
        assert classified[0, 0] == 1  # water
        assert classified[0, 1] == 0  # not water
        assert classified[1, 0] == 1  # water
        assert classified[1, 1] == 0  # not water

    def test_ndvi_vegetation_classification(self):
        """NDVI values correctly classify vegetation types."""
        ndvi = np.array([[0.8, 0.3], [0.1, -0.2]])
        result = clasificar_terreno_dinamico(None, ndvi, None)

        classified = result["clasificacion"]
        assert classified[0, 0] == 2  # dense vegetation (>0.5)
        assert classified[0, 1] == 4  # sparse vegetation (0.2-0.5)
        assert classified[1, 0] == 3  # bare soil (<=0.2 and >-0.1)
        assert classified[1, 1] == 0  # unclassified (<= -0.1)

    def test_sar_overrides_ndvi(self):
        """SAR water detection takes priority over NDVI."""
        sar = np.array([[-20.0, -10.0]])
        ndvi = np.array([[0.8, 0.8]])
        result = clasificar_terreno_dinamico(sar, ndvi, None)

        classified = result["clasificacion"]
        assert classified[0, 0] == 1  # water (SAR overrides NDVI)
        assert classified[0, 1] == 2  # dense veg (no SAR water)

    def test_statistics_computed(self):
        """Statistics report correct pixel counts and percentages."""
        sar = np.array([[-20.0, -10.0, -10.0, -10.0]])
        result = clasificar_terreno_dinamico(sar, None, None)

        stats = result["estadisticas"]
        assert stats["agua"]["pixeles"] == 1
        assert stats["agua"]["porcentaje"] == 25.0
        assert stats["sin_clasificar"]["pixeles"] == 3
        assert stats["sin_clasificar"]["porcentaje"] == 75.0

    def test_all_sensors_combined(self):
        """All three data sources combine correctly."""
        sar = np.array([[-20.0, -5.0, -5.0, -5.0]])
        ndvi = np.array([[0.8, 0.7, 0.3, 0.05]])
        dem = np.array([[100.0, 200.0, 150.0, 50.0]])

        result = clasificar_terreno_dinamico(sar, ndvi, dem)
        classified = result["clasificacion"]

        assert classified[0, 0] == 1  # water (SAR)
        assert classified[0, 1] == 2  # dense veg (NDVI)
        assert classified[0, 2] == 4  # sparse veg (NDVI)
        assert classified[0, 3] == 3  # bare soil (NDVI)


# ══════════════════════════════════════════════
# Repository CRUD Tests (require DB)
# ══════════════════════════════════════════════


class TestIntelligenceRepositoryCRUD:
    """Repository tests using the test database fixture.

    These tests require the `db` fixture from conftest.py which
    provides a transactional session that rolls back after each test.
    """

    def test_create_and_get_zona(self, db):
        """Create a zona and retrieve it by ID."""
        from geoalchemy2.shape import from_shape
        from shapely.geometry import box

        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = IntelligenceRepository()
        geom = from_shape(box(-64.0, -32.5, -63.5, -32.0), srid=4326)

        zona = repo.create_zona(
            db,
            nombre="Test Zone",
            geometria=geom,
            cuenca="candil",
            superficie_ha=1500.0,
        )
        db.flush()

        retrieved = repo.get_zona_by_id(db, zona.id)
        assert retrieved is not None
        assert retrieved.nombre == "Test Zone"
        assert retrieved.cuenca == "candil"
        assert retrieved.superficie_ha == 1500.0

    def test_create_indice_hidrico(self, db):
        """Create an HCI record linked to a zona."""
        from geoalchemy2.shape import from_shape
        from shapely.geometry import box

        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = IntelligenceRepository()
        geom = from_shape(box(-64.0, -32.5, -63.5, -32.0), srid=4326)

        zona = repo.create_zona(
            db,
            nombre="HCI Zone",
            geometria=geom,
            cuenca="norte",
            superficie_ha=800.0,
        )
        db.flush()

        ih = repo.create_indice_hidrico(
            db,
            zona_id=zona.id,
            fecha_calculo=date(2026, 3, 24),
            pendiente_media=0.3,
            acumulacion_media=0.7,
            twi_medio=0.5,
            proximidad_canal_m=200.0,
            historial_inundacion=0.4,
            indice_final=62.5,
            nivel_riesgo="alto",
        )
        db.flush()

        items, total = repo.get_indices_hidricos(db, zona_id=zona.id)
        assert total == 1
        assert items[0].indice_final == 62.5
        assert items[0].nivel_riesgo == "alto"

    def test_create_and_list_alertas(self, db):
        """Create alerts and list active ones."""
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = IntelligenceRepository()

        repo.create_alerta(
            db,
            tipo="umbral_superado",
            mensaje="Test alert 1",
            nivel="critico",
        )
        repo.create_alerta(
            db,
            tipo="lluvia_reciente",
            mensaje="Test alert 2",
            nivel="advertencia",
        )
        db.flush()

        alertas = repo.get_alertas_activas(db)
        assert len(alertas) == 2

    def test_deactivate_alerta(self, db):
        """Deactivating an alert removes it from active list."""
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = IntelligenceRepository()

        alerta = repo.create_alerta(
            db,
            tipo="cambio_sar",
            mensaje="SAR change detected",
            nivel="info",
        )
        db.flush()

        assert len(repo.get_alertas_activas(db)) == 1

        repo.deactivate_alerta(db, alerta.id)
        db.flush()

        assert len(repo.get_alertas_activas(db)) == 0

    def test_create_conflicto(self, db):
        """Create a conflict point and list it."""
        from geoalchemy2.shape import from_shape
        from shapely.geometry import Point

        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = IntelligenceRepository()
        geom = from_shape(Point(-63.8, -32.3), srid=4326)

        conflicto = repo.create_conflicto(
            db,
            tipo="canal_camino",
            geometria=geom,
            descripcion="Test crossing",
            severidad="media",
            acumulacion_valor=3000.0,
            pendiente_valor=1.5,
        )
        db.flush()

        items, total = repo.get_conflictos(db)
        assert total == 1
        assert items[0].tipo == "canal_camino"
        assert items[0].severidad == "media"

    def test_dashboard_empty(self, db):
        """Dashboard returns zeros when no data exists."""
        from app.domains.geo.intelligence.repository import IntelligenceRepository

        repo = IntelligenceRepository()
        dashboard = repo.get_dashboard_inteligente(db)

        assert dashboard["porcentaje_area_riesgo"] == 0.0
        assert dashboard["conflictos_activos"] == 0
        assert dashboard["alertas_activas"] == 0
        assert dashboard["zonas_por_nivel"] == {
            "bajo": 0,
            "medio": 0,
            "alto": 0,
            "critico": 0,
        }
