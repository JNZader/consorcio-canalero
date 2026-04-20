"""Integration tests for the main orchestrator — data-quality gates.

Tests exit codes and the "all-or-nothing" write contract: if any REQUIRED
layer returns zero features, NO output files are created.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.etl_pilar_verde import main as main_mod
from scripts.etl_pilar_verde.constants import (
    AGRO_ACEPTADA,
    AGRO_GRILLA,
    AGRO_PRESENTADA,
    BPA_LAYERS,
    EXIT_OK,
    EXIT_REQUIRED_LAYER_EMPTY,
    EXIT_ZONA_MISSING,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _build_outputs(tmp_path: Path) -> dict[str, Path]:
    base_capas = tmp_path / "capas"
    base_data = tmp_path / "data"
    return {
        "zona_ampliada": base_capas / "zona_ampliada.geojson",
        "bpa_2025": base_capas / "bpa_2025.geojson",
        "agro_aceptada": base_capas / "agro_aceptada.geojson",
        "agro_presentada": base_capas / "agro_presentada.geojson",
        "agro_zonas": base_capas / "agro_zonas.geojson",
        "porcentaje_forestacion": base_capas / "porcentaje_forestacion.geojson",
        "bpa_enriched": base_data / "bpa_enriched.json",
        "bpa_history": base_data / "bpa_history.json",
        "aggregates": base_data / "aggregates.json",
    }


@pytest.fixture
def fetcher_factory():
    """Build a fetch_layer replacement that returns empty for chosen layers."""

    def _factory(empty_layers: set[str]) -> Any:
        layer_payloads = {
            BPA_LAYERS[2025]: _load_fixture("bpa_2025.json"),
            AGRO_ACEPTADA: _load_fixture("agro_aceptada.json"),
            AGRO_PRESENTADA: _load_fixture("agro_presentada.json"),
            AGRO_GRILLA: _load_fixture("agro_grilla_dist5.json"),
        }

        def _fake(type_names: str, bbox_22174, **kwargs):
            if type_names in empty_layers:
                return {"type": "FeatureCollection", "features": []}
            return layer_payloads.get(
                type_names, {"type": "FeatureCollection", "features": []}
            )

        return _fake

    return _factory


class TestRequiredLayerEmpty:
    def test_empty_bpa_2025_exits_1(self, tmp_path, monkeypatch, fetcher_factory):
        outputs = _build_outputs(tmp_path)
        monkeypatch.setattr(
            main_mod,
            "fetch_layer",
            fetcher_factory({BPA_LAYERS[2025]}),
        )
        monkeypatch.setattr(
            main_mod,
            "_fetch_and_clip",
            _wrap_fetch_and_clip(fetcher_factory({BPA_LAYERS[2025]})),
        )

        code = main_mod.run_etl(
            kml_path=FIXTURES / "zona_ampliada_tiny.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
        )

        assert code == EXIT_REQUIRED_LAYER_EMPTY
        # All-or-nothing: NO output files should exist.
        for path in outputs.values():
            assert not path.exists(), f"unexpected output written: {path}"

    def test_empty_aceptada_exits_1(self, tmp_path, monkeypatch, fetcher_factory):
        outputs = _build_outputs(tmp_path)
        monkeypatch.setattr(
            main_mod,
            "_fetch_and_clip",
            _wrap_fetch_and_clip(fetcher_factory({AGRO_ACEPTADA})),
        )
        code = main_mod.run_etl(
            kml_path=FIXTURES / "zona_ampliada_tiny.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
        )
        assert code == EXIT_REQUIRED_LAYER_EMPTY
        for path in outputs.values():
            assert not path.exists()

    def test_empty_presentada_exits_1(self, tmp_path, monkeypatch, fetcher_factory):
        outputs = _build_outputs(tmp_path)
        monkeypatch.setattr(
            main_mod,
            "_fetch_and_clip",
            _wrap_fetch_and_clip(fetcher_factory({AGRO_PRESENTADA})),
        )
        code = main_mod.run_etl(
            kml_path=FIXTURES / "zona_ampliada_tiny.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
        )
        assert code == EXIT_REQUIRED_LAYER_EMPTY
        for path in outputs.values():
            assert not path.exists()

    def test_missing_kml_exits_4(self, tmp_path):
        outputs = _build_outputs(tmp_path)
        code = main_mod.run_etl(
            kml_path=tmp_path / "nonexistent.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
        )
        assert code == EXIT_ZONA_MISSING

    def test_happy_path_writes_all_9_outputs(
        self, tmp_path, monkeypatch, fetcher_factory
    ):
        outputs = _build_outputs(tmp_path)
        monkeypatch.setattr(
            main_mod,
            "_fetch_and_clip",
            _wrap_fetch_and_clip(fetcher_factory(set())),
        )

        code = main_mod.run_etl(
            kml_path=FIXTURES / "zona_ampliada_tiny.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
            generated_at="2026-04-20T00:00:00Z",
        )

        assert code == EXIT_OK
        for key, path in outputs.items():
            assert path.exists(), f"missing output: {key} at {path}"
            assert path.stat().st_size > 0

    def test_happy_path_outputs_have_schema_version(
        self, tmp_path, monkeypatch, fetcher_factory
    ):
        outputs = _build_outputs(tmp_path)
        monkeypatch.setattr(
            main_mod,
            "_fetch_and_clip",
            _wrap_fetch_and_clip(fetcher_factory(set())),
        )

        main_mod.run_etl(
            kml_path=FIXTURES / "zona_ampliada_tiny.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
            generated_at="2026-04-20T00:00:00Z",
        )

        # bpa_enriched.json is a plain dict with schema_version at top level.
        enriched = json.loads(outputs["bpa_enriched"].read_text())
        assert enriched["schema_version"] == "1.0"
        assert enriched["generated_at"] == "2026-04-20T00:00:00Z"
        assert "parcels" in enriched

        aggregates = json.loads(outputs["aggregates"].read_text())
        # Phase 0 addendum bumped aggregates.json to 1.1 (additive — 6 new
        # historical KPIs + evolucion_anual under bpa). Other files stay at 1.0.
        assert aggregates["schema_version"] == "1.1"
        assert "ley_forestal" in aggregates
        assert "bpa" in aggregates
        # Historical KPIs must exist under bpa in v1.1 — even if empty.
        bpa = aggregates["bpa"]
        assert "cobertura_historica_count" in bpa
        assert "cobertura_historica_pct" in bpa
        assert "abandonaron_count" in bpa
        assert "abandonaron_pct" in bpa
        assert "nunca_count" in bpa
        assert "nunca_pct" in bpa
        assert "evolucion_anual" in bpa
        # evolucion_anual must cover 2019-2025.
        assert set(bpa["evolucion_anual"].keys()) == {
            "2019", "2020", "2021", "2022", "2023", "2024", "2025",
        }

        # GeoJSON outputs have metadata nested.
        bpa_geo = json.loads(outputs["bpa_2025"].read_text())
        assert bpa_geo["type"] == "FeatureCollection"
        assert bpa_geo["metadata"]["schema_version"] == "1.0"
        assert len(bpa_geo["features"]) >= 1


class TestGrillaAggregatesWiring:
    """Anomaly #2 fix — agro_grilla_dist5 must be fetched and its aggregates
    populated.  Previously the orchestrator called ``compute_grilla_aggregates(None)``
    unconditionally, so the grilla block in ``aggregates.json`` was all zeros.
    """

    def test_grilla_aggregates_populated_when_fetch_enabled(
        self, tmp_path, monkeypatch, fetcher_factory
    ):
        outputs = _build_outputs(tmp_path)
        monkeypatch.setattr(
            main_mod,
            "_fetch_and_clip",
            _wrap_fetch_and_clip(fetcher_factory(set())),
        )

        code = main_mod.run_etl(
            kml_path=FIXTURES / "zona_ampliada_tiny.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
            fetch_grilla=True,
            generated_at="2026-04-20T00:00:00Z",
        )
        assert code == EXIT_OK
        aggregates = json.loads(outputs["aggregates"].read_text())
        grilla = aggregates["grilla_aggregates"]
        # Sentinel from the 3-feature fixture: altura_med_mean = (200+210+190)/3 = 200.0
        assert grilla["altura_med_mean"] == 200.0
        # pend_media_mean = (3+4+2)/3 = 3.0
        assert grilla["pend_media_mean"] == 3.0
        # forest_mean_pct = (2.5+3.5+4.0)/3 = 3.333 → 3.3 rounded 1dp
        assert grilla["forest_mean_pct"] == 3.3
        assert grilla["categoria_distribution"] == {"II": 2, "III": 1}
        assert grilla["drenaje_distribution"] == {"bueno": 2, "regular": 1}

    def test_grilla_aggregates_empty_when_fetch_disabled(
        self, tmp_path, monkeypatch, fetcher_factory
    ):
        outputs = _build_outputs(tmp_path)
        monkeypatch.setattr(
            main_mod,
            "_fetch_and_clip",
            _wrap_fetch_and_clip(fetcher_factory(set())),
        )
        code = main_mod.run_etl(
            kml_path=FIXTURES / "zona_ampliada_tiny.kml",
            catastro_path=FIXTURES / "catastro_rural_cu.json",
            output_files=outputs,
            fetch_historical_bpa=False,
            fetch_zonas_agroforestales=False,
            fetch_forestacion=False,
            fetch_grilla=False,
            generated_at="2026-04-20T00:00:00Z",
        )
        assert code == EXIT_OK
        aggregates = json.loads(outputs["aggregates"].read_text())
        grilla = aggregates["grilla_aggregates"]
        # Default "disabled" semantic — all zeros, empty distributions.
        assert grilla["altura_med_mean"] == 0
        assert grilla["categoria_distribution"] == {}


def _wrap_fetch_and_clip(fetcher):
    """Replace _fetch_and_clip with a stub that uses the given fake fetcher."""
    from scripts.etl_pilar_verde.clip import clip_to_zona

    def _stub(type_names, bbox_22174, zona):
        payload = fetcher(type_names, bbox_22174)
        features = payload.get("features") or []
        return clip_to_zona(features, zona_polygon_feature=zona)

    return _stub
