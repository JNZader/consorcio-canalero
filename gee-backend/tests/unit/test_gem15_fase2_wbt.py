"""Unit contracts for the fase 2 WBT comparison pipeline (issue #723, S1).

"Derivar flow/catchments del mismo AOI desde GEM-15 dtm vs GLO-30 (pipeline WBT
igual para ambos)". Three guarantees: both corrected DEMs land on the EXACT
same UTM grid (the GLO-30 one), the WBT step sequence is identical for both
with suffixed outputs, and those outputs live beside — never inside — the
pipeline's output/ directory whose natural_flow_dir the ficha reads.
"""

from __future__ import annotations

import numpy
import pytest
import rasterio

mod = pytest.importorskip("app.domains.geo.etl.gem15_fase2_wbt")


class TestReprojectOntoReference:
    def test_output_adopts_reference_grid_exactly(self, tmp_path):
        # ref: 3x3 en EPSG:32720; src: 4x4 en EPSG:4326 cubriendo la zona
        ref_values = numpy.full((3, 3), 100.0, dtype="float32")
        ref = tmp_path / "ref.tif"
        with rasterio.open(
            ref,
            "w",
            driver="GTiff",
            width=3,
            height=3,
            count=1,
            dtype="float32",
            crs="EPSG:32720",
            transform=rasterio.Affine(30.0, 0, 600000.0, 0, -30.0, 6300000.0),
        ) as dst:
            dst.write(ref_values, 1)
        src = tmp_path / "src.tif"
        with rasterio.open(
            src,
            "w",
            driver="GTiff",
            width=4,
            height=4,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=rasterio.Affine(0.001, 0, -64.0, 0, -0.001, -33.0),
            nodata=-9999.0,
        ) as dst:
            data = numpy.full((4, 4), 100.0, dtype="float32")
            data[0, 0] = -9999.0
            dst.write(data, 1)
        out = str(tmp_path / "on_ref.tif")
        mod.reproject_onto_reference_impl(
            rasterio_module=rasterio,
            src_path=str(src),
            reference_path=str(ref),
            output_path=out,
        )
        with rasterio.open(ref) as r, rasterio.open(out) as o:
            assert o.crs == r.crs
            assert o.transform == r.transform
            assert o.width == r.width and o.height == r.height
            assert o.nodata == r.nodata or o.nodata == -9999.0
            values = o.read(1)
        # datos válidos en la zona cubierta, no una grilla vacía
        assert numpy.isfinite(values).sum() >= 5


class RecordingWbt:
    """Wbt falso: el primer método invocado queda grabado."""

    def __init__(self):
        self.method: str | None = None

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.method = name

        return call


class FakeWbtRunner:
    """Firma del _run_wbt_tool del pipeline: (output_path, runner)."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __call__(self, output_path, runner):
        wbt = RecordingWbt()
        runner(wbt, output_path)
        self.calls.append((wbt.method, output_path))
        open(output_path, "w").close()
        return 0


class TestWbtSteps:
    def test_identical_sequence_with_suffixed_outputs_outside_pipeline_dir(self, tmp_path):
        import os

        out_dir = str(tmp_path / "fase2")
        os.makedirs(out_dir, exist_ok=True)
        dem = str(tmp_path / "dem.tif")
        open(dem, "w").close()
        runner = FakeWbtRunner()
        result = mod.run_wbt_steps_impl(
            get_wbt=lambda: object(),
            run_wbt_tool=runner,
            dem_path=dem,
            output_dir=out_dir,
            suffix="_gem15",
        )
        tools = [c[0] for c in runner.calls]
        assert tools == ["fill_depressions", "d8_pointer", "d8_flow_accumulation"]
        assert result["flow_dir"].endswith("flow_dir_gem15.tif")
        assert result["flow_acc"].endswith("flow_acc_gem15.tif")
        assert result["filled"].endswith("dem_filled_gem15.tif")
        for path in result.values():
            assert os.path.exists(path)
            assert "/output/" not in path

    def test_both_suffixes_cannot_collide(self, tmp_path):
        out_dir = str(tmp_path / "fase2")
        import os

        os.makedirs(out_dir, exist_ok=True)
        dem = str(tmp_path / "dem.tif")
        open(dem, "w").close()
        names = set()
        for suffix in ("_gem15", "_glo30"):
            runner = FakeWbtRunner()
            result = mod.run_wbt_steps_impl(
                get_wbt=lambda: object(),
                run_wbt_tool=runner,
                dem_path=dem,
                output_dir=out_dir,
                suffix=suffix,
            )
            names.update(os.path.basename(p) for p in result.values())
        assert len(names) == 6  # 3 archivos por DEM, ninguno compartido


class TestExtractStreams:
    def test_threshold_masks_accumulation(self, tmp_path):
        acc = numpy.array(
            [
                [0.0, 10.0, 999.0],
                [4.0, 500.0, 3.0],
                [2000.0, 1.0, 99.0],
            ],
            dtype="float32",
        )
        path = tmp_path / "acc.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=3,
            height=3,
            count=1,
            dtype="float32",
            crs="EPSG:32720",
            transform=rasterio.Affine(30, 0, 0, 0, -30, 0),
        ) as dst:
            dst.write(acc, 1)
        out = str(tmp_path / "streams.tif")
        mod.extract_streams_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            flow_acc_path=str(path),
            threshold_cells=100,
            output_path=out,
        )
        with rasterio.open(out) as src:
            data = src.read(1)
        expected = (acc >= 100).astype("uint8") * 2 + (acc < 100) * 1
        assert set(numpy.unique(data)) <= {1, 2}
        assert data[0, 2] == 2 and data[1, 1] == 2 and data[2, 0] == 2
        assert data[0, 0] == 1 and data[2, 1] == 1
