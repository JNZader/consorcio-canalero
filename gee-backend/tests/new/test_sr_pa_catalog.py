"""Packaged SR PA GeoJSON must travel with the backend image."""

from __future__ import annotations

from app.domains.geo.canales_publicacion.sr_pa_catalog import (
    iter_sr_pa_features,
    sr_pa_canal_id,
    sr_pa_geojson_path,
)


def test_packaged_geojson_is_next_to_the_module() -> None:
    path = sr_pa_geojson_path()
    assert path.is_file()
    assert path.parent.name == "data"
    assert "gee-backend" in path.as_posix()


def test_catalog_includes_ca00139() -> None:
    features = iter_sr_pa_features()
    ids = {sr_pa_canal_id(feature.get("properties") or {}) for feature in features}
    assert "srpa:CA00139" in ids
    assert len(features) == 54
