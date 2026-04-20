"""Tests for BPA aggregates — ranking, ejes, zonas intersect.

Anchors the frozen ``aggregates.json`` shape and rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.etl_pilar_verde.aggregates import (
    compute_bpa_kpis,
    compute_cobertura_historica,
    compute_ejes_distribucion,
    compute_evolucion_anual,
    compute_grilla_aggregates,
    compute_practicas_ranking,
    compute_zonas_agroforestales_intersect,
)
from scripts.etl_pilar_verde.constants import BPA_EJES, BPA_PRACTICAS
from scripts.etl_pilar_verde.join import join_bpa

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text()).get("features", [])


@pytest.fixture
def enriched_parcels():
    return join_bpa(
        _load("catastro_rural_cu.json"),
        _load("bpa_2025.json"),
        _load("agro_aceptada.json"),
        _load("agro_presentada.json"),
    )


class TestComputePracticasRanking:
    def test_returns_21_entries(self, enriched_parcels):
        ranking = compute_practicas_ranking(enriched_parcels)
        assert len(ranking) == 21

    def test_sorted_desc_by_adopcion_pct(self, enriched_parcels):
        ranking = compute_practicas_ranking(enriched_parcels)
        pcts = [row["adopcion_pct"] for row in ranking]
        assert pcts == sorted(pcts, reverse=True)

    def test_all_practicas_appear(self, enriched_parcels):
        ranking = compute_practicas_ranking(enriched_parcels)
        names = {row["nombre"] for row in ranking}
        assert names == set(BPA_PRACTICAS)

    def test_no_active_records_returns_all_zero(self):
        ranking = compute_practicas_ranking([])
        assert len(ranking) == 21
        assert all(row["adopcion_pct"] == 0 for row in ranking)

    def test_adopcion_pct_is_percentage(self, enriched_parcels):
        # Fixture active BPA records: La Sentina (activa=True), El Rosario (True),
        # San Antonio (True) = 3 active records. rotacion_gramineas is "Si"
        # in all 3 → 100.0%
        ranking = compute_practicas_ranking(enriched_parcels)
        rotacion = next(row for row in ranking if row["nombre"] == "rotacion_gramineas")
        assert rotacion["adopcion_pct"] == 100.0

    def test_inactive_records_excluded(self, enriched_parcels):
        # Los Olivos (activa=False) must NOT count in the ranking denominator.
        # capacitacion: La Sentina=Si, El Rosario=No, San Antonio=Si → 2/3 = 66.7
        ranking = compute_practicas_ranking(enriched_parcels)
        cap = next(row for row in ranking if row["nombre"] == "capacitacion")
        assert cap["adopcion_pct"] == 66.7


class TestComputeEjesDistribucion:
    def test_returns_4_ejes(self, enriched_parcels):
        dist = compute_ejes_distribucion(enriched_parcels)
        assert set(dist.keys()) == set(BPA_EJES)

    def test_percentages_are_rounded_1dp(self, enriched_parcels):
        dist = compute_ejes_distribucion(enriched_parcels)
        for value in dist.values():
            # Check value is a number, either int 0 or a rounded float.
            assert isinstance(value, (int, float))

    def test_empty_input_all_zero(self):
        dist = compute_ejes_distribucion([])
        assert dist == {"persona": 0, "planeta": 0, "prosperidad": 0, "alianza": 0}


class TestComputeBpaKpis:
    def test_explotaciones_activas_counts_only_active(self, enriched_parcels):
        # Fixture: 3 active bpa records out of 4 (Los Olivos is inactive; the
        # outside-zona record matches no catastro row, so it is dropped).
        kpis = compute_bpa_kpis(enriched_parcels, zona_superficie_ha=88307.3)
        assert kpis["explotaciones_activas"] == 3

    def test_superficie_total_uses_superficie_bpa(self, enriched_parcels):
        # 245.7 + 120.3 + 300.5 = 666.5 ha
        kpis = compute_bpa_kpis(enriched_parcels, zona_superficie_ha=88307.3)
        assert kpis["superficie_total_ha"] == 666.5

    def test_cobertura_pct_zona_is_rounded_1dp(self, enriched_parcels):
        kpis = compute_bpa_kpis(enriched_parcels, zona_superficie_ha=88307.3)
        # 666.5 / 88307.3 * 100 = 0.754... → rounded 1dp = 0.8
        assert kpis["cobertura_pct_zona"] == 0.8

    def test_zero_zona_ha_emits_zero(self, enriched_parcels):
        kpis = compute_bpa_kpis(enriched_parcels, zona_superficie_ha=0)
        assert kpis["cobertura_pct_zona"] == 0

    def test_deprecated_fields_are_dropped(self, enriched_parcels):
        """Phase 7 refinement — the 3 ranking-driven fields leave schema 1.2.

        User feedback: "top practica adoptada / no adoptada" and the full
        ranking are not actionable for the widget consumers. Drop them from
        aggregates.json entirely (schema 1.1 → 1.2).
        """
        kpis = compute_bpa_kpis(enriched_parcels, zona_superficie_ha=88307.3)
        assert "practica_top_adoptada" not in kpis
        assert "practica_top_no_adoptada" not in kpis
        assert "practicas_ranking" not in kpis


class TestComputeZonasAgroforestalesIntersect:
    def test_intersecting_zones_return_with_area(self):
        zona = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-62.7, -32.6],
                        [-62.3, -32.6],
                        [-62.3, -32.4],
                        [-62.7, -32.4],
                        [-62.7, -32.6],
                    ]
                ],
            },
        }
        zona_agroforestal_big = {
            "type": "Feature",
            "properties": {"leyenda": "11 - Sist Rio Tercero - Este"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-63.0, -33.0],
                        [-62.0, -33.0],
                        [-62.0, -32.0],
                        [-63.0, -32.0],
                        [-63.0, -33.0],
                    ]
                ],
            },
        }
        out = compute_zonas_agroforestales_intersect([zona_agroforestal_big], zona)
        assert len(out) == 1
        assert out[0]["leyenda"] == "11 - Sist Rio Tercero - Este"
        assert out[0]["superficie_ha_en_zona"] > 0

    def test_non_intersecting_zones_dropped(self):
        zona = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-62.7, -32.6],
                        [-62.3, -32.6],
                        [-62.3, -32.4],
                        [-62.7, -32.4],
                        [-62.7, -32.6],
                    ]
                ],
            },
        }
        out = compute_zonas_agroforestales_intersect(
            [
                {
                    "type": "Feature",
                    "properties": {"leyenda": "Far away"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-50.0, -20.0],
                                [-49.0, -20.0],
                                [-49.0, -19.0],
                                [-50.0, -19.0],
                                [-50.0, -20.0],
                            ]
                        ],
                    },
                }
            ],
            zona,
        )
        assert out == []


class TestComputeGrillaAggregates:
    def test_means_and_distributions_from_minimal_fixture(self):
        grilla = [
            {
                "properties": {
                    "altura_med": 200,
                    "pend_media": 3,
                    "forest_mean": 2.5,
                    "categoria": "II",
                    "drenaje": "bueno",
                }
            },
            {
                "properties": {
                    "altura_med": 210,
                    "pend_media": 4,
                    "forest_mean": 3.0,
                    "categoria": "II",
                    "drenaje": "regular",
                }
            },
        ]
        out = compute_grilla_aggregates(grilla)
        assert out["altura_med_mean"] == 205.0
        assert out["pend_media_mean"] == 3.5
        assert out["forest_mean_pct"] == 2.8
        assert out["categoria_distribution"] == {"II": 2}
        assert out["drenaje_distribution"] == {"bueno": 1, "regular": 1}

    def test_none_input_returns_defaults(self):
        out = compute_grilla_aggregates(None)
        assert out == {
            "altura_med_mean": 0,
            "pend_media_mean": 0,
            "forest_mean_pct": 0,
            "categoria_distribution": {},
            "drenaje_distribution": {},
        }


def _make_parcel(
    *,
    cuenta: str,
    bpa_2025: dict | None,
    historico: dict[str, str] | None = None,
) -> dict:
    """Minimal parcel shape used by cobertura/evolucion tests."""
    return {
        "nro_cuenta": cuenta,
        "bpa_2025": bpa_2025,
        "bpa_historico": historico or {},
    }


class TestComputeCoberturaHistorica:
    """Phase 0 addendum: 6 new KPIs exposing BPA historical coverage.

    Definitions (per user request on Batch 3):
    - ``cobertura_historica``: parcels with at least ONE year in bpa_historico
      OR with a non-null bpa_2025 (i.e. ever in the BPA registry).
    - ``abandonaron``: parcels with bpa_historico non-empty AND bpa_2025 is None
      (were in before, dropped out).
    - ``nunca``: parcels never in BPA (historico empty AND bpa_2025 None).
    """

    def test_all_four_buckets_counted(self):
        parcels = [
            # Case A — only 2025: in BPA this year, no history.
            _make_parcel(cuenta="A", bpa_2025={"activa": True}, historico={}),
            # Case B — only history: was in, dropped out (abandonaron).
            _make_parcel(cuenta="B", bpa_2025=None, historico={"2022": "x"}),
            # Case C — both: in 2025 AND has history.
            _make_parcel(
                cuenta="C",
                bpa_2025={"activa": True},
                historico={"2021": "x", "2023": "x"},
            ),
            # Case D — neither (nunca).
            _make_parcel(cuenta="D", bpa_2025=None, historico={}),
            # Extra nunca to make pcts non-trivial.
            _make_parcel(cuenta="E", bpa_2025=None, historico={}),
        ]
        out = compute_cobertura_historica(parcels)
        # cobertura_historica = A + B + C = 3 (out of 5)
        assert out["cobertura_historica_count"] == 3
        assert out["cobertura_historica_pct"] == 60.0
        # abandonaron = B = 1
        assert out["abandonaron_count"] == 1
        assert out["abandonaron_pct"] == 20.0
        # nunca = D + E = 2
        assert out["nunca_count"] == 2
        assert out["nunca_pct"] == 40.0

    def test_empty_parcels_returns_zeroes(self):
        out = compute_cobertura_historica([])
        assert out == {
            "cobertura_historica_count": 0,
            "cobertura_historica_pct": 0,
            "abandonaron_count": 0,
            "abandonaron_pct": 0,
            "nunca_count": 0,
            "nunca_pct": 0,
        }

    def test_only_2025_is_not_abandonaron(self):
        # Parcel in 2025 but no history → not abandonaron, not nunca.
        parcels = [_make_parcel(cuenta="X", bpa_2025={"activa": True}, historico={})]
        out = compute_cobertura_historica(parcels)
        assert out["cobertura_historica_count"] == 1
        assert out["abandonaron_count"] == 0
        assert out["nunca_count"] == 0


class TestComputeEvolucionAnual:
    """``evolucion_anual`` = per-year count of parcels that had a BPA record.

    Years 2019-2025 MUST always appear (even if value is 0), so the frontend
    can render a stable chart without defensive missing-year handling.
    """

    def test_all_years_always_present(self):
        parcels = [
            _make_parcel(cuenta="A", bpa_2025=None, historico={"2019": "x"}),
            _make_parcel(cuenta="B", bpa_2025=None, historico={"2024": "x"}),
        ]
        out = compute_evolucion_anual(parcels)
        # 2019-2025 MUST all be keys.
        assert set(out.keys()) == {"2019", "2020", "2021", "2022", "2023", "2024", "2025"}
        assert out["2019"] == 1
        assert out["2024"] == 1
        # Every other year SHALL appear as 0 (not missing).
        assert out["2020"] == 0
        assert out["2021"] == 0
        assert out["2022"] == 0
        assert out["2023"] == 0
        assert out["2025"] == 0

    def test_2025_counts_bpa_2025_non_null(self):
        parcels = [
            _make_parcel(cuenta="A", bpa_2025={"activa": True}, historico={}),
            _make_parcel(cuenta="B", bpa_2025={"activa": True}, historico={}),
            _make_parcel(cuenta="C", bpa_2025=None, historico={"2024": "x"}),
        ]
        out = compute_evolucion_anual(parcels)
        assert out["2025"] == 2
        assert out["2024"] == 1

    def test_parcel_with_multiple_years_counted_once_per_year(self):
        parcels = [
            _make_parcel(
                cuenta="A",
                bpa_2025={"activa": True},
                historico={"2019": "x", "2024": "x"},
            )
        ]
        out = compute_evolucion_anual(parcels)
        assert out["2019"] == 1
        assert out["2024"] == 1
        assert out["2025"] == 1
        assert out["2020"] == 0

    def test_empty_parcels_all_zero(self):
        out = compute_evolucion_anual([])
        assert out == {
            "2019": 0, "2020": 0, "2021": 0, "2022": 0,
            "2023": 0, "2024": 0, "2025": 0,
        }
