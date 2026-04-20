"""Tests for ``join_bpa`` — catastro x bpa_2025 x agro aceptada/presentada.

Two invariants from the spec:
1. Parcel WITHOUT a BPA match emits ``bpa_2025 = None`` EXACTLY (not ``{}``).
2. Parcel in BOTH aceptada and presentada resolves to ``ley_forestal = "aceptada"``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.etl_pilar_verde.join import build_bpa_history, join_bpa

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    payload = json.loads((FIXTURES / name).read_text())
    return payload.get("features", [])


@pytest.fixture
def catastro():
    return _load("catastro_rural_cu.json")


@pytest.fixture
def bpa_2025():
    return _load("bpa_2025.json")


@pytest.fixture
def aceptada():
    return _load("agro_aceptada.json")


@pytest.fixture
def presentada():
    return _load("agro_presentada.json")


class TestJoinBpa:
    def test_parcel_with_bpa_match_has_bpa_object(self, catastro, bpa_2025, aceptada, presentada):
        parcels = join_bpa(catastro, bpa_2025, aceptada, presentada)
        la_sentina = next(p for p in parcels if p["nro_cuenta"] == "150115736126")
        assert la_sentina["bpa_2025"] is not None
        assert la_sentina["bpa_2025"]["n_explotacion"] == "La Sentina"
        # 21 practicas present (spec enumeration)
        assert len(la_sentina["bpa_2025"]["practicas"]) == 21
        # 4 ejes
        assert set(la_sentina["bpa_2025"]["ejes"].keys()) == {
            "persona",
            "planeta",
            "prosperidad",
            "alianza",
        }

    def test_parcel_without_bpa_emits_none_exactly(self, catastro, bpa_2025, aceptada, presentada):
        # 150115736700 is in catastro but NOT in any BPA fixture → bpa_2025 None
        parcels = join_bpa(catastro, bpa_2025, aceptada, presentada)
        sin_bpa = next(p for p in parcels if p["nro_cuenta"] == "150115736700")
        assert sin_bpa["bpa_2025"] is None
        # Key exists — must not be missing and must not be an empty dict.
        assert "bpa_2025" in sin_bpa
        assert sin_bpa["bpa_2025"] != {}

    def test_aceptada_wins_over_presentada_on_overlap(self, catastro, bpa_2025, aceptada, presentada):
        # 150115736126 appears in BOTH aceptada and presentada fixtures.
        parcels = join_bpa(catastro, bpa_2025, aceptada, presentada)
        la_sentina = next(p for p in parcels if p["nro_cuenta"] == "150115736126")
        assert la_sentina["ley_forestal"] == "aceptada"

    def test_presentada_only_parcel_is_marked_presentada(self, catastro, bpa_2025, aceptada, presentada):
        # 150115736999 is only in presentada.
        parcels = join_bpa(catastro, bpa_2025, aceptada, presentada)
        only_presentada = next(p for p in parcels if p["nro_cuenta"] == "150115736999")
        assert only_presentada["ley_forestal"] == "presentada"
        assert only_presentada["bpa_2025"] is None

    def test_parcel_without_any_ley_inscription_is_no_inscripta(self, catastro, bpa_2025, aceptada, presentada):
        # 150115736700 is in catastro but not in aceptada/presentada/bpa.
        parcels = join_bpa(catastro, bpa_2025, aceptada, presentada)
        sin_inscripcion = next(p for p in parcels if p["nro_cuenta"] == "150115736700")
        assert sin_inscripcion["ley_forestal"] == "no_inscripta"

    def test_superficie_is_carried_from_catastro(self, catastro, bpa_2025, aceptada, presentada):
        parcels = join_bpa(catastro, bpa_2025, aceptada, presentada)
        la_sentina = next(p for p in parcels if p["nro_cuenta"] == "150115736126")
        assert la_sentina["superficie_ha"] == 245.7

    def test_all_catastro_parcels_emit_exactly_one_row(self, catastro, bpa_2025, aceptada, presentada):
        parcels = join_bpa(catastro, bpa_2025, aceptada, presentada)
        cuentas = [p["nro_cuenta"] for p in parcels]
        assert len(cuentas) == len(set(cuentas))  # no duplicates
        # We have 6 catastro parcels in the fixture.
        assert len(parcels) == 6

    def test_cuenta_normalization_joins_across_whitespace_quirks(
        self, catastro, bpa_2025, aceptada, presentada
    ):
        # Inject whitespace noise into a catastro row — join must still succeed.
        catastro_noisy = [dict(f) for f in catastro]
        catastro_noisy[0] = {
            **catastro_noisy[0],
            "properties": {
                **catastro_noisy[0]["properties"],
                "Nro_Cuenta": "  150115736126  ",
            },
        }
        parcels = join_bpa(catastro_noisy, bpa_2025, aceptada, presentada)
        la_sentina = next(p for p in parcels if p["nro_cuenta"] == "150115736126")
        assert la_sentina["bpa_2025"] is not None

    def test_superficie_is_converted_from_m2_to_ha(
        self, catastro, bpa_2025, aceptada, presentada
    ):
        """Anomaly #1 fix — IDECor catastro publishes Superficie_Tierra_Rural
        in m², despite the naming suggesting ha. The join MUST divide by
        10 000 so downstream consumers (aggregates, enriched JSON) see
        correct hectare values.

        Fixture parcel La Sentina has Superficie_Tierra_Rural=2_457_000 (m²),
        which is 245.7 ha.  The join must emit ``superficie_ha == 245.7``,
        NOT 2_457_000.
        """
        # Build a synthetic catastro row with an unambiguous m² value — larger
        # than any plausible ha figure, so the division is provable.
        synthetic = {
            "type": "Feature",
            "properties": {
                "Nomenclatura": "15-01-01-01-999999",
                "Tipo_Parcela": "RURAL",
                "Nro_Cuenta": "999999999999",
                "departamento": "MARCOS JUAREZ",
                "pedania": "Test Pedania",
                # 2 457 000 m² = 245.7 ha — the same hectares as La Sentina.
                "Superficie_Tierra_Rural": 2_457_000,
                "Valuacion_Tierra_Rural": 0,
                "desig_oficial": "Synthetic M2 Parcel",
            },
            "geometry": catastro[0]["geometry"],
        }
        parcels = join_bpa(
            [synthetic], bpa_2025, aceptada, presentada
        )
        assert len(parcels) == 1
        row = parcels[0]
        # Load-bearing assertion — this is the anomaly we are fixing.
        assert row["superficie_ha"] == 245.7


class TestBuildBpaHistory:
    def test_flattens_by_cuenta_across_years(self):
        # Minimal fixture — synthesise two year snapshots.
        bpa_2024 = [
            {
                "properties": {
                    "cuenta": "150115736126",
                    "n_explotacion": "La Sentina",
                }
            }
        ]
        bpa_2023 = [
            {
                "properties": {
                    "cuenta": "150115736126",
                    "n_explotacion": "La Sentina S.A.",
                }
            }
        ]
        history = build_bpa_history({2024: bpa_2024, 2023: bpa_2023})
        assert history["150115736126"] == {
            "2024": "La Sentina",
            "2023": "La Sentina S.A.",
        }

    def test_excludes_2025(self):
        # 2025 lives in bpa_enriched.json, never in history.json.
        bpa_2025 = [
            {
                "properties": {
                    "cuenta": "150115736126",
                    "n_explotacion": "La Sentina",
                }
            }
        ]
        history = build_bpa_history({2025: bpa_2025})
        assert history == {}

    def test_cuenta_without_name_is_skipped(self):
        bpa_2024 = [{"properties": {"cuenta": "150115736126", "n_explotacion": None}}]
        history = build_bpa_history({2024: bpa_2024})
        assert history == {}

    def test_missing_years_never_appear_as_null(self):
        bpa_2024 = [
            {"properties": {"cuenta": "150115736126", "n_explotacion": "La Sentina"}}
        ]
        history = build_bpa_history({2024: bpa_2024, 2023: [], 2022: []})
        # The spec says missing years MUST NOT appear as null.
        assert history["150115736126"] == {"2024": "La Sentina"}
        assert "2023" not in history["150115736126"]
