"""Tests for the canales writers.

Both writers produce deterministic outputs when the ``ETL_GENERATED_AT``
environment variable is set, so we can use golden-file comparisons.  In
normal operation ``generated_at`` comes from ``datetime.utcnow()`` and is
written once per ETL run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.etl_canales.writers import (
    CanalFeature,
    IndexMeta,
    write_geojson_canales,
    write_index_json,
)

GOLDEN_GENERATED_AT = "2026-04-20T00:00:00Z"


@pytest.fixture(autouse=True)
def _deterministic_generated_at(monkeypatch: pytest.MonkeyPatch):
    """Pin the ``generated_at`` timestamp for every test in this module."""
    monkeypatch.setenv("ETL_GENERATED_AT", GOLDEN_GENERATED_AT)


def _sample_feature(i: int) -> CanalFeature:
    """Build a small deterministic CanalFeature for golden-file tests."""
    return CanalFeature(
        id=f"test-canal-{i}",
        codigo=f"X{i}",
        nombre=f"Tramo {i}",
        descripcion=None,
        estado="relevado",
        longitud_m=1000.0 + i,
        longitud_declarada_m=1000.0 + i,
        prioridad=None,
        featured=False,
        tramo_folder="TestFolder",
        source_style="sin_obra",
        coords=[(-62.5, -32.5), (-62.49 + i * 0.001, -32.49 + i * 0.001)],
    )


class TestWriteGeoJsonCanales:
    def test_writes_featurecollection_with_metadata(self, tmp_path: Path):
        features = [_sample_feature(0), _sample_feature(1)]
        out = tmp_path / "relevados.geojson"
        write_geojson_canales(features, out)

        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["type"] == "FeatureCollection"
        assert payload["metadata"]["schema_version"] == "1.0"
        assert payload["metadata"]["generated_at"] == GOLDEN_GENERATED_AT
        assert isinstance(payload["features"], list)
        assert len(payload["features"]) == 2

    def test_feature_shape(self, tmp_path: Path):
        features = [_sample_feature(0)]
        out = tmp_path / "relevados.geojson"
        write_geojson_canales(features, out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        feat = payload["features"][0]
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "LineString"
        assert feat["geometry"]["coordinates"] == [[-62.5, -32.5], [-62.49, -32.49]]
        props = feat["properties"]
        # Every frozen v1.0 property is present:
        expected_keys = {
            "id",
            "codigo",
            "nombre",
            "descripcion",
            "estado",
            "longitud_m",
            "longitud_declarada_m",
            "prioridad",
            "featured",
            "tramo_folder",
            "source_style",
        }
        assert set(props.keys()) == expected_keys
        # Explicitly verify a few:
        assert props["id"] == "test-canal-0"
        assert props["codigo"] == "X0"
        assert props["estado"] == "relevado"
        assert props["longitud_m"] == 1000.0
        assert props["prioridad"] is None

    def test_empty_features_still_valid(self, tmp_path: Path):
        out = tmp_path / "empty.geojson"
        write_geojson_canales([], out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["type"] == "FeatureCollection"
        assert payload["features"] == []


class TestWriteIndexJson:
    def test_writes_index_with_counts(self, tmp_path: Path):
        relevados_meta = [
            IndexMeta(
                id="r1",
                nombre="Canal r1",
                codigo=None,
                prioridad=None,
                longitud_m=100.0,
                featured=False,
                estado="relevado",
            ),
        ]
        propuestas_meta = [
            IndexMeta(
                id="p1",
                nombre="Propuesta p1",
                codigo="N1",
                prioridad="Alta",
                longitud_m=200.0,
                featured=True,
                estado="propuesto",
            ),
            IndexMeta(
                id="p2",
                nombre="Propuesta p2",
                codigo="N2",
                prioridad="Media",
                longitud_m=300.0,
                featured=False,
                estado="propuesto",
            ),
        ]
        out = tmp_path / "index.json"
        write_index_json(relevados_meta, propuestas_meta, out)

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload["generated_at"] == GOLDEN_GENERATED_AT
        assert payload["counts"]["relevados"] == 1
        assert payload["counts"]["propuestas"] == 2
        assert payload["counts"]["total"] == 3
        assert len(payload["relevados"]) == 1
        assert len(payload["propuestas"]) == 2
        # The relevado slot should NOT carry prioridad (absent key is cleaner).
        assert "prioridad" not in payload["relevados"][0] or payload["relevados"][0]["prioridad"] is None
        # The propuesto slot SHOULD carry prioridad.
        assert payload["propuestas"][0]["prioridad"] == "Alta"


class TestGeneratedAtOverride:
    def test_env_overrides_now(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ETL_GENERATED_AT", "1999-01-01T00:00:00Z")
        out = tmp_path / "relevados.geojson"
        write_geojson_canales([_sample_feature(0)], out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["metadata"]["generated_at"] == "1999-01-01T00:00:00Z"

    def test_no_env_produces_iso8601(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ETL_GENERATED_AT", raising=False)
        out = tmp_path / "relevados.geojson"
        write_geojson_canales([_sample_feature(0)], out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        # The default timestamp must be an ISO-8601 UTC string ending in Z.
        stamp = payload["metadata"]["generated_at"]
        assert isinstance(stamp, str) and stamp.endswith("Z") and "T" in stamp
