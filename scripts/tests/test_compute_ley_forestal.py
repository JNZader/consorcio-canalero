"""Tests for ``compute_ley_forestal`` — two-track counts + superficie.

From spec §aggregates.json:
- Counts: aceptada_count, presentada_count, no_inscripta_count
- Superficie: sum of catastro ``Superficie_Tierra_Rural`` per bucket
- cumplimiento_pct_parcelas = aceptada/(aceptada+presentada)*100 rounded 1dp
- cumplimiento_pct_superficie = aceptada_ha/(aceptada_ha+presentada_ha)*100 rounded 1dp
- Zero-division: both pcts emit ``0`` (not NaN) and a WARN log line.
"""

from __future__ import annotations

import logging

import pytest

from scripts.etl_pilar_verde.aggregates import compute_ley_forestal


def _parcel(nro: str, ley: str, ha: float | None) -> dict:
    return {"nro_cuenta": nro, "ley_forestal": ley, "superficie_ha": ha}


class TestComputeLeyForestal:
    def test_happy_path_two_track(self):
        parcels = [
            _parcel("A", "aceptada", 100.0),
            _parcel("B", "aceptada", 200.0),
            _parcel("C", "presentada", 400.0),
            _parcel("D", "presentada", 600.0),
            _parcel("E", "no_inscripta", 50.0),
        ]
        out = compute_ley_forestal(parcels)
        assert out["aceptada_count"] == 2
        assert out["presentada_count"] == 2
        assert out["no_inscripta_count"] == 1
        assert out["aceptada_superficie_ha"] == 300.0
        assert out["presentada_superficie_ha"] == 1000.0
        assert out["cumplimiento_pct_parcelas"] == 50.0  # 2/(2+2)*100
        # 300/(300+1000)*100 = 23.076923... → rounded 1dp = 23.1
        assert out["cumplimiento_pct_superficie"] == 23.1

    def test_zero_division_parcelas_emits_zero_not_nan(self, caplog):
        out = compute_ley_forestal([])
        assert out["cumplimiento_pct_parcelas"] == 0
        assert out["cumplimiento_pct_superficie"] == 0
        # Not NaN
        assert out["cumplimiento_pct_parcelas"] == out["cumplimiento_pct_parcelas"]
        assert out["aceptada_count"] == 0
        assert out["presentada_count"] == 0

    def test_zero_division_logs_warning(self, caplog):
        caplog.set_level(logging.WARNING)
        compute_ley_forestal([])
        # Must log a WARN mentioning the zero-denominator guard.
        assert any(
            record.levelno == logging.WARNING and "zero" in record.message.lower()
            for record in caplog.records
        )

    def test_only_no_inscripta_still_emits_zero_pcts(self):
        parcels = [_parcel("A", "no_inscripta", 100.0)]
        out = compute_ley_forestal(parcels)
        assert out["aceptada_count"] == 0
        assert out["presentada_count"] == 0
        assert out["cumplimiento_pct_parcelas"] == 0
        assert out["cumplimiento_pct_superficie"] == 0

    def test_null_superficie_is_treated_as_zero(self):
        parcels = [
            _parcel("A", "aceptada", None),
            _parcel("B", "presentada", 100.0),
        ]
        out = compute_ley_forestal(parcels)
        assert out["aceptada_superficie_ha"] == 0
        assert out["presentada_superficie_ha"] == 100.0

    def test_rounding_1dp_on_both_pcts(self):
        # aceptada_count=1, presentada_count=3 → 25.0%
        # aceptada_ha=33.3, presentada_ha=66.7 → 33.3/(33.3+66.7)=33.3 → rounded 33.3
        parcels = [
            _parcel("A", "aceptada", 33.3),
            _parcel("B", "presentada", 22.2),
            _parcel("C", "presentada", 22.2),
            _parcel("D", "presentada", 22.3),
        ]
        out = compute_ley_forestal(parcels)
        assert out["cumplimiento_pct_parcelas"] == 25.0
        # All values rounded to 1dp.
        assert out["cumplimiento_pct_superficie"] == 33.3
