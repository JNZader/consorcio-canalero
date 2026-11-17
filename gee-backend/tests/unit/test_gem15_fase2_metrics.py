"""Unit contracts for the fase 2 ground-truth metrics (issue #723, S3).

"comparar redes derivadas vs red real (métrica: % cruces correctamente
derivados, desvío de líneas de flujo en llanura)". The 41 relevado canal
LineStrings are the truth; the derived stream rasters (T4) are the hypothesis.
Distances are measured in CELLS on the shared UTM grid so the tests stay
unit-free; the ETL main multiplies by the cell size for the doc.
"""

from __future__ import annotations

import json

import numpy
import pytest
import rasterio

mod = pytest.importorskip("app.domains.geo.etl.gem15_fase2_metrics")


def _write_streams(path, values):
    values = numpy.asarray(values, dtype="uint8")
    height, width = values.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",  # raster CRS == lines CRS: transform is identity in tests
        transform=rasterio.Affine(1.0, 0, 0, 0, -1.0, 10.0),
    ) as dst:
        dst.write(values, 1)
    return str(path)


def _geojson(tmp_path, lines):
    features = [
        {
            "type": "Feature",
            "properties": {"codigo": f"C{i}"},
            "geometry": {"type": "LineString", "coordinates": coords},
        }
        for i, coords in enumerate(lines)
    ]
    path = tmp_path / "canales.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return str(path)


class TestCanalMetrics:
    def test_distance_and_coverage_against_known_stream(self, tmp_path):
        # stream vertical en col=5 (valor 2); llanura = 1
        grid = numpy.ones((10, 12), dtype="uint8")
        grid[:, 5] = 2
        streams = _write_streams(tmp_path / "streams.tif", grid)
        # canal A a 2 celdas del cauce (x=7) y canal B pegado (x=5)
        gj = _geojson(
            tmp_path,
            [
                [[7.0, 2.0], [7.0, 8.0]],  # fila 2..8 -> puntos a distancia 2
                [[5.0, 2.0], [5.0, 8.0]],  # sobre el cauce -> distancia 0
            ],
        )
        report = mod.canal_metrics_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            distance_transform_fn=_identity_edt,
            streams_path=streams,
            canales_geojson=gj,
            spacing_cells=1.0,
            tolerance_cells=2,
        )
        assert report["n_points"] > 0
        assert report["median_cells"] == pytest.approx(1.0)
        assert report["p90_cells"] == pytest.approx(2.0)
        assert report["coverage_frac"] == pytest.approx(1.0)  # todo a <=2 celdas

    def test_far_canal_reports_large_deviation_and_low_coverage(self, tmp_path):
        grid = numpy.ones((10, 12), dtype="uint8")
        grid[:, 0] = 2  # cauce en el borde izquierdo
        streams = _write_streams(tmp_path / "streams.tif", grid)
        gj = _geojson(tmp_path, [[[9.0, 2.0], [9.0, 8.0]]])  # a 9 celdas
        report = mod.canal_metrics_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            distance_transform_fn=_identity_edt,
            streams_path=streams,
            canales_geojson=gj,
            spacing_cells=1.0,
            tolerance_cells=2,
        )
        assert report["median_cells"] == pytest.approx(9.0)
        assert report["coverage_frac"] == pytest.approx(0.0)

    def test_per_canal_breakdown_is_reported(self, tmp_path):
        grid = numpy.ones((10, 12), dtype="uint8")
        grid[:, 5] = 2
        streams = _write_streams(tmp_path / "streams.tif", grid)
        gj = _geojson(tmp_path, [[[7.0, 2.0], [7.0, 8.0]], [[5.0, 2.0], [5.0, 8.0]]])
        report = mod.canal_metrics_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            distance_transform_fn=_identity_edt,
            streams_path=streams,
            canales_geojson=gj,
            spacing_cells=1.0,
            tolerance_cells=2,
        )
        assert set(report["per_canal"].keys()) == {"C0", "C1"}
        assert report["per_canal"]["C0"]["median_cells"] == pytest.approx(2.0)
        assert report["per_canal"]["C1"]["median_cells"] == pytest.approx(0.0)


def _identity_edt(mask):
    """distance_transform_edt de scipy, para inyectar en los impl."""
    from scipy.ndimage import distance_transform_edt

    return distance_transform_edt(mask)


class TestLoadCanales:
    def test_loads_all_lines_with_codes(self, tmp_path):
        gj = _geojson(tmp_path, [[[0.0, 0.0], [1.0, 1.0]], [[2.0, 2.0], [3.0, 3.0]]])
        lines = mod.load_canal_lines(gj)
        assert [code for code, _ in lines] == ["C0", "C1"]
        assert lines[0][1][0] == [0.0, 0.0]
