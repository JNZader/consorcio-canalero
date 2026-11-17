"""Fase 2 (issue #723), paso S1b: mismo pipeline WBT sobre ambos DEMs
corregidos, en grilla común, con salidas propias.

Ambos rasters llegan aquí ya corregidos (T2 datum + T3 debias). La regla de
oro: la comparabilidad viene de que los DOS corran EXACTAMENTE lo mismo sobre
la MISMA grilla — la UTM del GLO-30 reproyectado primero; el GEM-15 se
reproyecta SOBRE esa grilla (no sobre su propio calculate_default_transform).

Secuencia por DEM (la del pipeline productivo, sin roto ni extracción de
cuencas, que en fase 2 se hace por pour-points en T5):
fill_depressions -> d8_pointer -> d8_flow_accumulation(cells)

Salidas bajo /data/geo/{area_id}/fase2/ con sufijos _gem15/_glo30 — NUNCA en
output/ ni pisando natural_flow_dir_{area_id} (restricción del feature doc).

Corre dentro del contenedor backend::

    docker compose exec backend python -m app.domains.geo.etl.gem15_fase2_wbt
"""

from __future__ import annotations

from pathlib import Path

from app.domains.geo.etl.gem15_fase2_download import (
    DEFAULT_AREA_ID,
    DEFAULT_GEO_BASE,
    FASE2_DIR_NAME,
)

#: Umbral de celdas de acumulación para trazar cauces (T5 lo afina contra la
#: red real; este es el punto de partida del setting del pipeline).
STREAM_THRESHOLD_CELLS = 100


def fase2_dir(*, area_id: str = DEFAULT_AREA_ID, base_dir: str = DEFAULT_GEO_BASE) -> Path:
    return Path(base_dir) / area_id / FASE2_DIR_NAME


def reproject_onto_reference_impl(
    *,
    rasterio_module,
    src_path: str,
    reference_path: str,
    output_path: str,
) -> str:
    """Reproyecta src EXACTAMENTE sobre la grilla del reference (bilinear).

    La grilla destino no se calcula: se copia del reference — mismo transform,
    mismo tamaño, mismo CRS. Sin esto cada DEM tendría su propia grilla y las
    redes derivadas no serían comparables celda a celda.
    """
    from rasterio.warp import Resampling, reproject as rio_reproject

    with rasterio_module.open(reference_path) as ref:
        ref_profile = ref.profile.copy()
        dst_transform = ref.transform
        dst_crs = ref.crs
        width, height = ref.width, ref.height
    with rasterio_module.open(src_path) as src:
        src_data = src.read(1)
        src_nodata = src.nodata
    ref_profile.update(dtype="float32", compress="deflate", predictor=3)
    if src_nodata is not None:
        ref_profile["nodata"] = src_nodata
    dst_data = numpy_empty(rasterio_module, (height, width))
    rio_reproject(
        source=src_data,
        destination=dst_data,
        src_transform=src_transform_of(rasterio_module, src_path),
        src_crs=src_crs_of(rasterio_module, src_path),
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=src_nodata,
        dst_nodata=src_nodata if src_nodata is not None else -9999.0,
    )
    with rasterio_module.open(output_path, "w", **ref_profile) as dst:
        dst.write(dst_data.astype("float32"), 1)
    return output_path


def numpy_empty(rasterio_module, shape):
    import numpy as np

    return np.empty(shape, dtype="float32")


def src_transform_of(rasterio_module, path):
    with rasterio_module.open(path) as src:
        return src.transform


def src_crs_of(rasterio_module, path):
    with rasterio_module.open(path) as src:
        return src.crs


def run_wbt_steps_impl(
    *,
    get_wbt,
    run_wbt_tool,
    dem_path: str,
    output_dir: str,
    suffix: str,
) -> dict[str, str]:
    """Secuencia WBT idéntica para ambos DEMs, salidas sufijadas.

    Usa el run_wbt_tool del pipeline (que EXIGE exit 0 + archivo en disco —
    contrato anti fallo silencioso de processing_wbt_support).
    """
    filled = str(Path(output_dir) / f"dem_filled{suffix}.tif")
    flow_dir = str(Path(output_dir) / f"flow_dir{suffix}.tif")
    flow_acc = str(Path(output_dir) / f"flow_acc{suffix}.tif")
    run_wbt_tool(filled, lambda wbt, path: wbt.fill_depressions(dem_path, path))
    run_wbt_tool(flow_dir, lambda wbt, path: wbt.d8_pointer(filled, path))
    run_wbt_tool(
        flow_acc, lambda wbt, path: wbt.d8_flow_accumulation(flow_dir, path, out_type="cells")
    )
    return {"filled": filled, "flow_dir": flow_dir, "flow_acc": flow_acc}


def extract_streams_impl(
    *,
    rasterio_module,
    numpy_module,
    flow_acc_path: str,
    threshold_cells: int,
    output_path: str,
) -> str:
    """flow_acc >= threshold -> 2 (cauce), si no 1 (llanura). uint8 para tiles."""
    np = numpy_module
    with rasterio_module.open(flow_acc_path) as src:
        acc = src.read(1)
        profile = src.profile.copy()
    streams = np.where(acc >= threshold_cells, 2, 1).astype("uint8")
    profile.update(dtype="uint8", nodata=None, compress="deflate")
    with rasterio_module.open(output_path, "w", **profile) as dst:
        dst.write(streams, 1)
    return output_path


def main() -> int:  # pragma: no cover — needs the fase 2 rasters and WBT in the container
    import rasterio
    import numpy

    from app.domains.geo.etl.gem15_fase2_download import fase2_paths
    from app.domains.geo.processing import _get_wbt, _run_wbt_tool as run_wbt_tool, reproject_to_utm

    paths = fase2_paths()
    out_dir = fase2_dir()
    gem15_debiased = str(Path(paths["gem15"]).with_name("dem_gem15_debiased.tif"))

    glo30_utm = str(out_dir / "dem_glo30_utm.tif")
    print(f"[fase2] GLO-30 -> UTM: {glo30_utm}")
    reproject_to_utm(paths["glo30"], glo30_utm)

    gem15_utm = str(out_dir / "dem_gem15_utm.tif")
    print(f"[fase2] GEM-15 debiased -> grilla del GLO-30: {gem15_utm}")
    reproject_onto_reference_impl(
        rasterio_module=rasterio,
        src_path=gem15_debiased,
        reference_path=glo30_utm,
        output_path=gem15_utm,
    )

    for suffix, dem in (("_glo30", glo30_utm), ("_gem15", gem15_utm)):
        print(f"[fase2] WBT {suffix}: fill -> d8 -> accum")
        result = run_wbt_steps_impl(
            get_wbt=_get_wbt,
            run_wbt_tool=run_wbt_tool,
            dem_path=dem,
            output_dir=str(out_dir),
            suffix=suffix,
        )
        streams = str(out_dir / f"streams{suffix}.tif")
        extract_streams_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            flow_acc_path=result["flow_acc"],
            threshold_cells=STREAM_THRESHOLD_CELLS,
            output_path=streams,
        )
        print(f"[fase2] {suffix}: {result['flow_dir']} | streams -> {streams}")
    print("[fase2] ambos pipelines listos — ready for T5 (métricas vs red real)")
    return 0


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
