"""Fase 2 (issue #723), paso S2b: debias regional del GEM-15 contra GLO-30
sobre terreno estable.

El offset regional hay que MEDIRLO, no asumirlo (el paper no trae número para
Córdoba; la literatura reporta -4.8..+1.9 m según la zona). Receta:

1. Máscara de terreno estable: celdas cuyo rango focal 3x3 (max-min en la
   ventana) está por debajo de un umbral EN AMBOS DEMs — la llanura limpia.
   Canales, terraplenes y alcantarillas quedan afuera por construcción.
2. offset = mediana de (GEM-15@EGM2008 - GLO-30) SOLO en celdas estables. La
   mediana (con su MAD reportada) es robusta al ruido que igual se cuela.
3. dem_gem15_debiased.tif = GEM-15@EGM2008 - offset — alineado verticalmente
   a GLO-30 para la comparación hidrológica (T4).

Corre dentro del contenedor backend::

    docker compose exec backend python -m app.domains.geo.etl.gem15_fase2_debias
"""

from __future__ import annotations

import json
from pathlib import Path

#: Rango focal 3x3 (metros) por debajo del cual una celda cuenta como terreno
#: estable. La llanura relevada es submétrica a escala de ventana; canales y
#: terraplenes la superan con holgura.
STABLE_WINDOW_RANGE_M = 2.0
#: Mínimo de celdas estables para confiar en la mediana. Con menos, el offset
#: no es medición, es anécdota.
MIN_STABLE_CELLS = 1000


def stable_mask(values, *, window_range_m: float, nodata=None):
    """Celdas cuyo rango en la ventana 3x3 (en este DEM) es bajo.

    El anillo exterior no tiene ventana completa -> False, igual que el nodata.
    """
    import numpy as np

    arr = np.asarray(values, dtype="float64")
    height, width = arr.shape
    valid = np.ones((height, width), dtype=bool)
    if nodata is not None:
        valid &= arr != nodata
    pads = np.pad(arr, 1, mode="edge")
    window_max = np.full((height, width), -np.inf)
    window_min = np.full((height, width), np.inf)
    for dr in range(3):
        for dc in range(3):
            view = pads[dr : dr + height, dc : dc + width]
            window_max = np.maximum(window_max, view)
            window_min = np.minimum(window_min, view)
    focal_range = window_max - window_min
    edge = np.zeros((height, width), dtype=bool)
    edge[1:-1, 1:-1] = True
    return valid & edge & (focal_range < window_range_m)


def compute_debias_offset_impl(
    *,
    rasterio_module,
    numpy_module,
    glo30_path: str,
    gem15_path: str,
    window_range_m: float = STABLE_WINDOW_RANGE_M,
    min_stable_cells: int = MIN_STABLE_CELLS,
) -> dict:
    np = numpy_module
    with rasterio_module.open(glo30_path) as src:
        glo30 = src.read(1).astype("float64")
        glo_nodata = src.nodata
    with rasterio_module.open(gem15_path) as src:
        gem15 = src.read(1).astype("float64")
        gem_nodata = src.nodata
    if glo30.shape != gem15.shape:
        raise RuntimeError(
            f"grillas distintas: GLO-30 {glo30.shape} vs GEM-15 {gem15.shape} — mismo AOI y mismo scale (T1)"
        )
    stable = stable_mask(glo30, window_range_m=window_range_m, nodata=glo_nodata) & stable_mask(
        gem15, window_range_m=window_range_m, nodata=gem_nodata
    )
    diff = gem15 - glo30
    stable_diff = diff[stable]
    if stable_diff.size < min_stable_cells:
        raise RuntimeError(
            f"solo {stable_diff.size} celdas estables (< {min_stable_cells}): "
            "el offset no es medible con esta mascara — revisar window_range_m"
        )
    offset = float(np.median(stable_diff))
    mad = float(np.median(np.abs(stable_diff - offset)))
    return {
        "offset_m": round(offset, 4),
        "mad_m": round(mad, 4),
        "stable_cells": int(stable_diff.size),
        "total_cells": int(diff.size),
        "stable_fraction": round(float(stable_diff.size) / float(diff.size), 4),
        "window_range_m": window_range_m,
    }


def apply_debias_impl(
    *,
    rasterio_module,
    numpy_module,
    gem15_path: str,
    offset_m: float,
    output_path: str,
) -> str:
    with rasterio_module.open(gem15_path) as src:
        data = src.read(1)
        profile = src.profile.copy()
    corrected = data.astype("float64") - offset_m
    if profile.get("nodata") is not None:
        corrected[data == profile["nodata"]] = profile["nodata"]
    # predictor=2: el 3 (float) rompe el lector GeoTIFF de WhiteboxTools
    profile.update(dtype="float32", compress="deflate", predictor=2)
    with rasterio_module.open(output_path, "w", **profile) as dst:
        dst.write(corrected.astype("float32"), 1)
    return output_path


def main() -> int:  # pragma: no cover — needs the fase 2 rasters on the volume
    import numpy
    import rasterio

    from app.domains.geo.etl.gem15_fase2_download import fase2_paths

    paths = fase2_paths()
    gem15_egm2008 = str(Path(paths["gem15"]).with_name("dem_gem15_egm2008.tif"))
    debiased = str(Path(paths["gem15"]).with_name("dem_gem15_debiased.tif"))
    report_path = str(Path(paths["gem15"]).with_name("debias_report.json"))
    report = compute_debias_offset_impl(
        rasterio_module=rasterio,
        numpy_module=numpy,
        glo30_path=paths["glo30"],
        gem15_path=gem15_egm2008,
    )
    apply_debias_impl(
        rasterio_module=rasterio,
        numpy_module=numpy,
        gem15_path=gem15_egm2008,
        offset_m=report["offset_m"],
        output_path=debiased,
    )
    Path(report_path).write_text(json.dumps(report, indent=2))
    print(
        f"[fase2] offset regional: {report['offset_m']} m (MAD {report['mad_m']} m, "
        f"{report['stable_cells']} celdas estables = {report['stable_fraction']:.1%})"
    )
    print(f"[fase2] -> {debiased} | reporte: {report_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
