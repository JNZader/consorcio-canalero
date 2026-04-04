"""Unit tests for app.domains.geo.intelligence.service — service orchestration."""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# HCI Calculation
# ---------------------------------------------------------------------------


class TestCalculateHciForZone:
    @patch("app.domains.geo.intelligence.service.intel_repo")
    @patch("app.domains.geo.intelligence.service.calcular_indice_criticidad_hidrica", return_value=0.72)
    @patch("app.domains.geo.intelligence.service.clasificar_nivel_riesgo", return_value="alto")
    def test_returns_hci_result(self, mock_nivel, mock_calc, mock_repo):
        from app.domains.geo.intelligence.service import calculate_hci_for_zone

        db = MagicMock()
        zona_id = uuid.uuid4()
        mock_repo.get_zona_by_id.return_value = MagicMock(id=zona_id)
        mock_repo.create_indice_hidrico.return_value = MagicMock()

        result = calculate_hci_for_zone(
            db,
            zona_id,
            pendiente_media=0.3,
            acumulacion_media=0.5,
            twi_medio=0.6,
            proximidad_canal_m=1000.0,
            historial_inundacion=0.4,
        )

        assert result["indice_final"] == 0.72
        assert result["nivel_riesgo"] == "alto"
        assert result["zona_id"] == str(zona_id)
        assert "componentes" in result
        db.commit.assert_called_once()

    @patch("app.domains.geo.intelligence.service.intel_repo")
    def test_raises_when_zone_not_found(self, mock_repo):
        from app.domains.geo.intelligence.service import calculate_hci_for_zone

        db = MagicMock()
        mock_repo.get_zona_by_id.return_value = None

        with pytest.raises(ValueError, match="no encontrada"):
            calculate_hci_for_zone(
                db,
                uuid.uuid4(),
                pendiente_media=0.1,
                acumulacion_media=0.1,
                twi_medio=0.1,
                proximidad_canal_m=100.0,
                historial_inundacion=0.1,
            )

    @patch("app.domains.geo.intelligence.service.intel_repo")
    @patch("app.domains.geo.intelligence.service.calcular_indice_criticidad_hidrica", return_value=0.5)
    @patch("app.domains.geo.intelligence.service.clasificar_nivel_riesgo", return_value="moderado")
    def test_dist_canal_normalization_caps_at_zero(self, _nivel, mock_calc, mock_repo):
        from app.domains.geo.intelligence.service import calculate_hci_for_zone

        db = MagicMock()
        mock_repo.get_zona_by_id.return_value = MagicMock()
        mock_repo.create_indice_hidrico.return_value = MagicMock()

        calculate_hci_for_zone(
            db,
            uuid.uuid4(),
            pendiente_media=0.1,
            acumulacion_media=0.1,
            twi_medio=0.1,
            proximidad_canal_m=10000.0,  # > 5000 → dist_norm should be 0
            historial_inundacion=0.1,
        )

        # dist_canal should have been clamped to 0.0 (max(1 - 10000/5000, 0) = 0)
        call_kwargs = mock_calc.call_args
        assert call_kwargs[1]["dist_canal"] == 0.0 or call_kwargs[0][3] == 0.0


# ---------------------------------------------------------------------------
# Conflict Detection
# ---------------------------------------------------------------------------


class TestDetectConflicts:
    @patch("app.domains.geo.intelligence.service.intel_repo")
    @patch("app.domains.geo.intelligence.service.detectar_puntos_conflicto")
    def test_empty_gdf_returns_zero_conflicts(self, mock_detect, mock_repo):
        from app.domains.geo.intelligence.service import detect_conflicts

        db = MagicMock()
        empty_gdf = MagicMock()
        empty_gdf.empty = True
        mock_detect.return_value = empty_gdf

        result = detect_conflicts(
            db,
            canales_gdf=MagicMock(),
            caminos_gdf=MagicMock(),
            drenajes_gdf=MagicMock(),
            flow_acc_path="/path",
            slope_path="/path",
        )

        assert result["conflictos_detectados"] == 0
        assert result["detalle"] == []


# ---------------------------------------------------------------------------
# Runoff Simulation
# ---------------------------------------------------------------------------


class TestRunRunoffSimulation:
    @patch("app.domains.geo.intelligence.service.simular_escorrentia")
    def test_returns_geojson_result(self, mock_sim):
        from app.domains.geo.intelligence.service import run_runoff_simulation

        db = MagicMock()
        expected = {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
        mock_sim.return_value = expected

        result = run_runoff_simulation(
            db,
            punto=(-62.5, -32.5),
            lluvia_mm=50.0,
            flow_dir_path="/flow_dir.tif",
            flow_acc_path="/flow_acc.tif",
        )

        assert result == expected
        mock_sim.assert_called_once()


# ---------------------------------------------------------------------------
# Zone Generation
# ---------------------------------------------------------------------------


class TestGenerateZones:
    @patch("app.domains.geo.intelligence.service.intel_repo")
    @patch("app.domains.geo.intelligence.service.generar_zonificacion")
    def test_empty_gdf_returns_zero_zones(self, mock_gen, mock_repo):
        from app.domains.geo.intelligence.service import generate_zones

        db = MagicMock()
        empty_gdf = MagicMock()
        empty_gdf.empty = True
        mock_gen.return_value = empty_gdf

        result = generate_zones(db, dem_path="/dem.tif", flow_acc_path="/fa.tif")

        assert result["zonas_creadas"] == 0
        assert result["zonas"] == []


# ---------------------------------------------------------------------------
# Check Alerts
# ---------------------------------------------------------------------------


class TestCheckAlerts:
    @patch("app.domains.geo.intelligence.service.intel_repo")
    def test_no_critical_zones_creates_no_alerts(self, mock_repo):
        from app.domains.geo.intelligence.service import check_alerts

        db = MagicMock()
        mock_repo.get_alertas_activas.return_value = []
        mock_repo.get_zonas_criticas.return_value = []

        result = check_alerts(db)

        assert result["alertas_creadas"] == 0
        assert result["alertas_activas_total"] == 0

    @patch("app.domains.geo.intelligence.service.intel_repo")
    def test_critical_zone_creates_alert(self, mock_repo):
        from app.domains.geo.intelligence.service import check_alerts

        db = MagicMock()
        zona = MagicMock()
        zona.id = uuid.uuid4()
        zona.nombre = "Zona Test"
        zona.cuenca = "candil"

        mock_repo.get_alertas_activas.return_value = []
        mock_repo.get_zonas_criticas.side_effect = [
            [zona],  # critico
            [],      # alto
        ]

        result = check_alerts(db)

        assert result["alertas_creadas"] == 1
        mock_repo.create_alerta.assert_called_once()
        db.commit.assert_called_once()

    @patch("app.domains.geo.intelligence.service.intel_repo")
    def test_existing_alert_is_not_duplicated(self, mock_repo):
        from app.domains.geo.intelligence.service import check_alerts

        db = MagicMock()
        zona_id = uuid.uuid4()

        existing_alert = MagicMock()
        existing_alert.zona_id = zona_id

        zona = MagicMock()
        zona.id = zona_id
        zona.nombre = "Zona"
        zona.cuenca = "ml"

        mock_repo.get_alertas_activas.return_value = [existing_alert]
        mock_repo.get_zonas_criticas.side_effect = [
            [zona],  # critico — already alerted
            [],      # alto
        ]

        result = check_alerts(db)

        assert result["alertas_creadas"] == 0
        mock_repo.create_alerta.assert_not_called()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class TestGetDashboard:
    @patch("app.domains.geo.intelligence.service.intel_repo")
    def test_delegates_to_repository(self, mock_repo):
        from app.domains.geo.intelligence.service import get_dashboard

        db = MagicMock()
        expected = {"zonas": 5, "alertas": 2}
        mock_repo.get_dashboard_inteligente.return_value = expected

        result = get_dashboard(db)

        assert result == expected
        mock_repo.get_dashboard_inteligente.assert_called_once_with(db)
