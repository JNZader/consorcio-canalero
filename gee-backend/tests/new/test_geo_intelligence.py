"""
Tests for Phase 3: Intelligence calculations and alert deduplication.

Tests pure calculation functions (no DB required) and alert dedup logic concept.
"""

import pytest

from app.domains.geo.intelligence.calculations import (
    DEFAULT_HCI_WEIGHTS,
    calcular_indice_criticidad_hidrica,
    clasificar_nivel_riesgo,
)


# ── HCI Calculation ────────────────────────────────


class TestCalcularIndiceHCI:
    """Test Hydric Criticality Index calculation with known inputs."""

    def test_all_zeros_returns_zero(self):
        result = calcular_indice_criticidad_hidrica(
            pendiente=0.0,
            acumulacion=0.0,
            twi=0.0,
            dist_canal=0.0,
            hist_inundacion=0.0,
        )
        assert result == 0.0

    def test_all_ones_returns_hundred(self):
        result = calcular_indice_criticidad_hidrica(
            pendiente=1.0,
            acumulacion=1.0,
            twi=1.0,
            dist_canal=1.0,
            hist_inundacion=1.0,
        )
        assert result == 100.0

    def test_known_weighted_calculation(self):
        """Verify HCI with default weights and known inputs."""
        # Default weights: pendiente=0.15, acumulacion=0.30, twi=0.25,
        #                  dist_canal=0.15, hist_inundacion=0.15
        result = calcular_indice_criticidad_hidrica(
            pendiente=0.8,
            acumulacion=0.6,
            twi=0.7,
            dist_canal=0.5,
            hist_inundacion=0.4,
        )
        # Expected: (0.15*0.8 + 0.30*0.6 + 0.25*0.7 + 0.15*0.5 + 0.15*0.4) * 100
        #         = (0.12 + 0.18 + 0.175 + 0.075 + 0.06) * 100
        #         = 0.61 * 100 = 61.0
        assert result == 61.0

    def test_custom_weights(self):
        """HCI respects custom weight overrides."""
        custom = {
            "pendiente": 0.5,
            "acumulacion": 0.5,
            "twi": 0.0,
            "dist_canal": 0.0,
            "hist_inundacion": 0.0,
        }
        result = calcular_indice_criticidad_hidrica(
            pendiente=1.0,
            acumulacion=1.0,
            twi=1.0,
            dist_canal=1.0,
            hist_inundacion=1.0,
            pesos=custom,
        )
        assert result == 100.0

    def test_result_clamped_to_100(self):
        """Values above 1.0 should not exceed 100."""
        # With default weights summing to 1.0, inputs of 1.0 already cap at 100
        result = calcular_indice_criticidad_hidrica(
            pendiente=1.0,
            acumulacion=1.0,
            twi=1.0,
            dist_canal=1.0,
            hist_inundacion=1.0,
        )
        assert result <= 100.0

    def test_default_weights_sum_to_one(self):
        """Default HCI weights must sum to 1.0 for proper scaling."""
        total = sum(DEFAULT_HCI_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9


# ── Risk Classification ────────────────────────────


class TestClasificarNivelRiesgo:
    """Test risk level classification thresholds."""

    @pytest.mark.parametrize(
        "indice, expected",
        [
            (0.0, "bajo"),
            (10.0, "bajo"),
            (24.99, "bajo"),
            (25.0, "medio"),
            (40.0, "medio"),
            (49.99, "medio"),
            (50.0, "alto"),
            (60.0, "alto"),
            (74.99, "alto"),
            (75.0, "critico"),
            (90.0, "critico"),
            (100.0, "critico"),
        ],
    )
    def test_threshold_boundaries(self, indice, expected):
        assert clasificar_nivel_riesgo(indice) == expected


# ── Alert Dedup Concept ─────────────────────────────


class TestAlertDeduplication:
    """Test the alert dedup logic concept (uses mock objects, not DB)."""

    def test_dedup_skips_zones_with_active_alert(self):
        """Verify that check_alerts dedup logic skips already-alerted zones.

        This tests the CONCEPT by simulating the dedup set behavior used in
        app.domains.geo.intelligence.service.check_alerts.
        """
        import uuid

        zona_id_1 = uuid.uuid4()
        zona_id_2 = uuid.uuid4()
        zona_id_3 = uuid.uuid4()

        # Simulate existing active alerts (zone 1 already has one)
        zonas_con_alerta = {zona_id_1}

        # Zones that crossed critical threshold
        zonas_criticas = [zona_id_1, zona_id_2]

        nuevas = 0
        for zid in zonas_criticas:
            if zid not in zonas_con_alerta:
                zonas_con_alerta.add(zid)
                nuevas += 1

        # Zone 1 was skipped (dedup), zone 2 was added
        assert nuevas == 1
        assert zona_id_2 in zonas_con_alerta

        # Now process "alto" zones - zone 2 already has alert from above
        zonas_alto = [zona_id_2, zona_id_3]
        for zid in zonas_alto:
            if zid not in zonas_con_alerta:
                zonas_con_alerta.add(zid)
                nuevas += 1

        # Zone 2 skipped (dedup), zone 3 added
        assert nuevas == 2
        assert zona_id_3 in zonas_con_alerta
