"""
Tests for pure hydrological calculation functions.

Covers: kirpich_tc, ndvi_to_c, rational_method_q, classify_hydraulic_risk.
No database required — all functions are pure math.
"""

import pytest

from app.domains.geo.hydrology.calculations import (
    classify_hydraulic_risk,
    kirpich_tc,
    ndvi_to_c,
    rational_method_q,
)


# ── kirpich_tc ────────────────────────────────────────


class TestKirpichTc:
    """Concentration time via Kirpich formula."""

    def test_typical_values(self):
        """L=500 m, S=0.01 → result should be ~13.75 min (±0.5).

        Tc = 0.0195 * 500^0.77 * 0.01^-0.385 ≈ 13.75 min
        """
        result = kirpich_tc(L_m=500.0, S=0.01)
        assert abs(result - 13.75) < 0.5, f"Expected ~13.75 min, got {result:.3f}"

    def test_slope_floor_prevents_zero_division(self):
        """S=0.0 must give same result as S=0.001 (floor applied internally)."""
        result_zero = kirpich_tc(L_m=500.0, S=0.0)
        result_floor = kirpich_tc(L_m=500.0, S=0.001)
        assert result_zero == pytest.approx(result_floor)

    def test_slope_floor_negative_slope(self):
        """Negative S (data error) is also floored to 0.001."""
        result_neg = kirpich_tc(L_m=500.0, S=-0.5)
        result_floor = kirpich_tc(L_m=500.0, S=0.001)
        assert result_neg == pytest.approx(result_floor)

    def test_longer_channel_gives_longer_tc(self):
        """Longer channel → longer concentration time."""
        tc_short = kirpich_tc(L_m=200.0, S=0.005)
        tc_long = kirpich_tc(L_m=1000.0, S=0.005)
        assert tc_long > tc_short

    def test_steeper_slope_gives_shorter_tc(self):
        """Steeper slope → shorter concentration time."""
        tc_flat = kirpich_tc(L_m=500.0, S=0.001)
        tc_steep = kirpich_tc(L_m=500.0, S=0.05)
        assert tc_steep < tc_flat

    def test_returns_float(self):
        result = kirpich_tc(L_m=300.0, S=0.005)
        assert isinstance(result, float)


# ── ndvi_to_c ────────────────────────────────────────


class TestNdviToC:
    """NDVI → runoff coefficient C lookup table."""

    def test_bare_soil_low_ndvi(self):
        """NDVI < 0.15 → C = 0.80 (bare soil / urban)."""
        assert ndvi_to_c(0.1) == 0.80

    def test_sparse_vegetation(self):
        """0.15 ≤ NDVI < 0.30 → C = 0.65."""
        assert ndvi_to_c(0.2) == 0.65

    def test_moderate_vegetation_boundary(self):
        """NDVI = 0.30 (boundary) → C = 0.45 (moderate veg)."""
        assert ndvi_to_c(0.3) == 0.45

    def test_moderate_vegetation_mid(self):
        """NDVI = 0.40 (mid-range) → C = 0.45."""
        assert ndvi_to_c(0.4) == 0.45

    def test_dense_vegetation_boundary(self):
        """NDVI = 0.50 (boundary) → C = 0.25 (dense veg)."""
        assert ndvi_to_c(0.5) == 0.25

    def test_dense_vegetation_high(self):
        """NDVI = 0.80 → C = 0.25."""
        assert ndvi_to_c(0.8) == 0.25

    def test_ndvi_clamped_above_one(self):
        """NDVI > 1.0 is clamped to 1.0 → C = 0.25."""
        assert ndvi_to_c(1.5) == 0.25

    def test_ndvi_clamped_below_zero(self):
        """NDVI < 0.0 is clamped to 0.0 → C = 0.80."""
        assert ndvi_to_c(-0.3) == 0.80

    def test_returns_float(self):
        result = ndvi_to_c(0.35)
        assert isinstance(result, float)


# ── rational_method_q ────────────────────────────────


class TestRationalMethodQ:
    """Peak discharge via Rational Method."""

    def test_known_values(self):
        """C=0.5, I=20 mm/h, A=1.0 km² → Q = (0.5*20*1.0)/3.6 ≈ 2.78 m³/s."""
        result = rational_method_q(C=0.5, I_mm_h=20.0, A_km2=1.0)
        assert result == pytest.approx(2.777, abs=0.01)

    def test_zero_area_gives_zero_q(self):
        """Zero drainage area → zero discharge."""
        result = rational_method_q(C=0.8, I_mm_h=50.0, A_km2=0.0)
        assert result == pytest.approx(0.0)

    def test_higher_c_gives_higher_q(self):
        """Higher runoff coefficient → higher discharge (same I and A)."""
        q_low_c = rational_method_q(C=0.25, I_mm_h=30.0, A_km2=2.0)
        q_high_c = rational_method_q(C=0.80, I_mm_h=30.0, A_km2=2.0)
        assert q_high_c > q_low_c

    def test_larger_area_gives_higher_q(self):
        """Larger drainage area → higher discharge."""
        q_small = rational_method_q(C=0.5, I_mm_h=25.0, A_km2=1.0)
        q_large = rational_method_q(C=0.5, I_mm_h=25.0, A_km2=5.0)
        assert q_large > q_small

    def test_returns_float(self):
        result = rational_method_q(C=0.5, I_mm_h=20.0, A_km2=1.0)
        assert isinstance(result, float)


# ── classify_hydraulic_risk ───────────────────────────


class TestClassifyHydraulicRisk:
    """Hydraulic risk classification based on Q vs. canal capacity."""

    def test_sin_capacidad_when_none(self):
        """Unknown capacity → ('sin_capacidad', None)."""
        nivel, pct = classify_hydraulic_risk(Q=5.0, capacity_m3s=None)
        assert nivel == "sin_capacidad"
        assert pct is None

    def test_bajo_below_50pct(self):
        """Q=4 m³/s, capacity=10 → 40% → 'bajo'."""
        nivel, pct = classify_hydraulic_risk(Q=4.0, capacity_m3s=10.0)
        assert nivel == "bajo"
        assert pct == pytest.approx(40.0)

    def test_moderado_between_50_and_75pct(self):
        """Q=6 m³/s, capacity=10 → 60% → 'moderado'."""
        nivel, pct = classify_hydraulic_risk(Q=6.0, capacity_m3s=10.0)
        assert nivel == "moderado"
        assert pct == pytest.approx(60.0)

    def test_alto_at_85pct(self):
        """Q=8.5, capacity=10 → 85% → 'alto'."""
        nivel, pct = classify_hydraulic_risk(Q=8.5, capacity_m3s=10.0)
        assert nivel == "alto"
        assert pct == pytest.approx(85.0)

    def test_alto_at_exactly_100pct(self):
        """Q=10, capacity=10 → 100% → still 'alto' (≤ 100 boundary)."""
        nivel, pct = classify_hydraulic_risk(Q=10.0, capacity_m3s=10.0)
        assert nivel == "alto"
        assert pct == pytest.approx(100.0)

    def test_critico_above_100pct(self):
        """Q=12, capacity=10 → 120% → 'critico'."""
        nivel, pct = classify_hydraulic_risk(Q=12.0, capacity_m3s=10.0)
        assert nivel == "critico"
        assert pct == pytest.approx(120.0)

    def test_returns_tuple(self):
        result = classify_hydraulic_risk(Q=5.0, capacity_m3s=10.0)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ── Phase 4 explicit risk classification coverage ─────────────────────────
# These tests pin the exact (Q, capacity, expected_label, expected_pct)
# combinations required by the Phase 4 spec.  They deliberately overlap
# with TestClassifyHydraulicRisk above to serve as stable regression anchors.


class TestClassifyHydraulicRiskPhase4:
    """Explicit Phase-4 risk-level regression anchors."""

    def test_classify_risk_alto(self):
        """Q=8.5, cap=10.0 → ('alto', 85.0)."""
        nivel, pct = classify_hydraulic_risk(Q=8.5, capacity_m3s=10.0)
        assert nivel == "alto"
        assert pct == pytest.approx(85.0)

    def test_classify_risk_critico(self):
        """Q=12.0, cap=10.0 → ('critico', 120.0)."""
        nivel, pct = classify_hydraulic_risk(Q=12.0, capacity_m3s=10.0)
        assert nivel == "critico"
        assert pct == pytest.approx(120.0)

    def test_classify_risk_sin_capacidad(self):
        """Q=5.0, cap=None → ('sin_capacidad', None)."""
        nivel, pct = classify_hydraulic_risk(Q=5.0, capacity_m3s=None)
        assert nivel == "sin_capacidad"
        assert pct is None

    def test_classify_risk_bajo(self):
        """Q=3.0, cap=10.0 → ('bajo', 30.0)."""
        nivel, pct = classify_hydraulic_risk(Q=3.0, capacity_m3s=10.0)
        assert nivel == "bajo"
        assert pct == pytest.approx(30.0)

    def test_classify_risk_moderado(self):
        """Q=6.0, cap=10.0 → ('moderado', 60.0)."""
        nivel, pct = classify_hydraulic_risk(Q=6.0, capacity_m3s=10.0)
        assert nivel == "moderado"
        assert pct == pytest.approx(60.0)
