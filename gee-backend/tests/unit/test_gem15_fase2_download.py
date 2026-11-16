"""Unit contracts for the GEM-15 fase 2 DEM download (issue #723, S1/S2).

The fase 2 rasters MUST live beside the pipeline outputs, never inside them,
and the GEM-15 download MUST mirror the grid contract of
``processing_wbt_support.download_dem_impl`` (same region, same scale, same CRS)
so both DEMs land on the same grid before any comparison (S2 forbids comparing
raw heights across datums; grid parity is the precondition for everything else).
"""

from __future__ import annotations

import importlib

import pytest


mod = importlib.import_module("app.domains.geo.etl.gem15_fase2_download")


class FakeImage:
    def __init__(self, rec: dict, band: str | None = None):
        self._rec = rec
        self._band = band

    def select(self, band: str) -> "FakeImage":
        self._rec.setdefault("select", []).append(band)
        return FakeImage(self._rec, band)

    def clip(self, region) -> "FakeImage":
        self._rec["clip"] = region
        return self

    def getDownloadURL(self, params: dict) -> str:
        self._rec["url_params"] = params
        return "https://fake.example/download.tif"


class FakeImageCollection:
    def __init__(self, rec: dict, asset_id: str):
        self._rec = rec
        self._asset_id = asset_id

    def mosaic(self) -> FakeImage:
        self._rec["asset"] = self._asset_id
        return FakeImage(self._rec)


class FakeGeometry:
    def __init__(self, rec: dict, geojson: dict):
        self.geojson = geojson
        rec["geometry_arg"] = geojson


class FakeEE:
    def __init__(self) -> None:
        self.rec: dict = {}

    def ImageCollection(self, asset_id: str) -> FakeImageCollection:
        return FakeImageCollection(self.rec, asset_id)

    def Geometry(self, geojson: dict) -> FakeGeometry:
        return FakeGeometry(self.rec, geojson)


class FakeResponse:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        return iter(self._chunks)


class FakeRequests:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks
        self.calls: list[dict] = []

    def get(self, url: str, stream: bool = True, timeout: int = 300) -> FakeResponse:
        self.calls.append({"url": url, "stream": stream, "timeout": timeout})
        return FakeResponse(self._chunks)


class FakeSrc:
    def __init__(self, profile: dict):
        self.profile = profile

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return [[1]]


class FakeDst:
    def __init__(self, path: str, profile: dict, written: dict):
        self.path = path
        self.profile = profile
        self._written = written

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, data):
        self._written[self.path] = {"profile": self.profile, "data": data}


class FakeRasterio:
    def __init__(self):
        self.written: dict = {}

    def open(self, path: str, mode: str = "r", **profile):
        if mode == "r":
            return FakeSrc({"driver": "GTiff", "compress": None})
        return FakeDst(path, profile, self.written)


class TestFase2Paths:
    def test_paths_live_in_own_fase2_dir_not_pipeline_output(self):
        paths = mod.fase2_paths(area_id="zona_principal")
        assert set(paths) == {"glo30", "gem15"}
        for name, path in paths.items():
            assert path.startswith("/data/geo/zona_principal/fase2/")
            assert "/output/" not in path
            assert name in path
            assert path.endswith(".tif")

    def test_paths_honour_custom_base_dir(self):
        paths = mod.fase2_paths(area_id="otra", base_dir="/tmp/geo")
        assert paths["glo30"].startswith("/tmp/geo/otra/fase2/")


class TestGem15DownloadContract:
    @pytest.fixture()
    def downloaded(self, tmp_path):
        ee = FakeEE()
        requests = FakeRequests([b"raw", b"tif"])
        rasterio = FakeRasterio()
        output = str(tmp_path / "dem_gem15_raw.tif")
        result = mod.download_gem15_dtm_impl(
            ee_module=ee,
            requests_module=requests,
            rasterio_module=rasterio,
            ensure_parent_dir=lambda p: None,
            zona_geometry={"type": "Polygon", "coordinates": [[[1, 2]]]},
            output_path=output,
            scale=30,
        )
        return ee, requests, rasterio, output, result

    def test_pins_gem15_asset_and_dtm_band(self, downloaded):
        ee, *_ = downloaded
        assert ee.rec["asset"] == "projects/climate-and-sustainability/assets/gem-15_v1"
        assert "dtm" in ee.rec["select"]

    def test_grid_contract_matches_download_dem_impl(self, downloaded):
        ee, *_ = downloaded
        params = ee.rec["url_params"]
        assert params["format"] == "GEO_TIFF"
        assert params["crs"] == "EPSG:4326"
        assert params["scale"] == 30
        # region must be the ee.Geometry wrapping the SAME zona geojson
        assert ee.rec["geometry_arg"] == {"type": "Polygon", "coordinates": [[[1, 2]]]}
        assert params["region"] is ee.rec["clip"]

    def test_recompresses_and_cleans_tmp(self, downloaded, tmp_path):
        _, requests, rasterio, output, result = downloaded
        assert result == output
        assert requests.calls[0]["stream"] is True
        written = rasterio.written[output]
        assert written["profile"]["compress"] == "deflate"
        assert written["profile"]["predictor"] == 2
        assert not (tmp_path / "dem_gem15_raw.tmp.tif").exists()

    def test_scale_passthrough(self, tmp_path):
        ee = FakeEE()
        mod.download_gem15_dtm_impl(
            ee_module=ee,
            requests_module=FakeRequests([b"x"]),
            rasterio_module=FakeRasterio(),
            ensure_parent_dir=lambda p: None,
            zona_geometry={"type": "Point", "coordinates": [0, 0]},
            output_path=str(tmp_path / "a.tif"),
            scale=15,
        )
        assert ee.rec["url_params"]["scale"] == 15
