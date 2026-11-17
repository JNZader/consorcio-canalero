"""Fase 2 (issue #723), paso S3: métricas de las redes derivadas contra la
red real de canales.

La verdad de terreno son los 41 canales RELEVADOS (L3: canales + cruces; los
eventos de crecida quedaron como anexo cualitativo). Por cada DEM derivado
(streams del T4) se mide sobre la MISMA grilla:

- desvío: distancia (celdas, luego m) de puntos muestreados a lo largo de cada
  canal al cauce derivado más cercano — mediana y p90 globales y por canal.
  Este es EL número de la llanura: cuánto se desvía la línea de flujo.
- cobertura: fracción de puntos de canal con cauce derivado a <= tolerancia
  (proxy del "% cruces correctamente derivados" del issue).

Distancias en CELDAS para ser agnóstico de unidades; el main multiplica por el
tamaño de celda (30 m). Necesita scipy (está en requirements-geo y dev; correr
en geo-worker o backend dev)::

    docker compose exec geo-worker python -m app.domains.geo.etl.gem15_fase2_metrics
"""

from __future__ import annotations

import json
from typing import Any


def load_canal_lines(geojson_path: str) -> list[tuple[str, list[list[float]]]]:
    with open(geojson_path) as f:
        data: dict[str, Any] = json.load(f)
    lines = []
    for feature in data.get("features", []):
        code = str((feature.get("properties") or {}).get("codigo", feature.get("id", "?")))
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "LineString":
            lines.append((code, geometry["coordinates"]))
    return lines


def canal_metrics_impl(
    *,
    rasterio_module,
    numpy_module,
    distance_transform_fn,
    streams_path: str,
    canales_geojson: str,
    spacing_cells: float = 1.0,
    tolerance_cells: int = 2,
) -> dict:
    np = numpy_module
    with rasterio_module.open(streams_path) as src:
        streams = src.read(1)
        transform = src.transform
        crs = src.crs
        cell = abs(transform.a)
    # distancia (en celdas) de cada pixel al cauce derivado (valor 2) más cercano
    dist_grid = distance_transform_fn(streams != 2)

    from rasterio.warp import transform_geom
    from shapely.geometry import LineString

    per_canal: dict[str, dict] = {}
    all_d: list[float] = []
    for code, coords in load_canal_lines(canales_geojson):
        geom = transform_geom(
            "EPSG:4326", crs.to_string(), {"type": "LineString", "coordinates": coords}
        )
        line = LineString(geom["coordinates"])
        step = spacing_cells * cell
        n = max(int(line.length / step), 1)
        distances: list[float] = []
        height, width = streams.shape
        for i in range(n + 1):
            point = line.interpolate(line.length * i / n)
            col, row = ~transform * (point.x, point.y)
            r = min(max(int(round(row)), 0), height - 1)
            c = min(max(int(round(col)), 0), width - 1)
            distances.append(float(dist_grid[r, c]))
        per_canal[code] = {
            "n_points": len(distances),
            "median_cells": round(float(np.median(distances)), 3),
            "p90_cells": round(float(np.percentile(distances, 90)), 3),
            "coverage_frac": round(float(np.mean(np.asarray(distances) <= tolerance_cells)), 4),
        }
        all_d.extend(distances)
    arr = np.asarray(all_d)
    return {
        "n_points": int(arr.size),
        "median_cells": round(float(np.median(arr)), 3),
        "p90_cells": round(float(np.percentile(arr, 90)), 3),
        "coverage_frac": round(float(np.mean(arr <= tolerance_cells)), 4),
        "tolerance_cells": tolerance_cells,
        "per_canal": per_canal,
    }


def main() -> int:  # pragma: no cover — needs the fase 2 rasters on the volume
    import json as json_module
    from pathlib import Path

    import numpy
    import rasterio
    from scipy.ndimage import distance_transform_edt

    from app.domains.geo.etl.gem15_fase2_metrics import canal_metrics_impl
    from app.domains.geo.etl.gem15_fase2_wbt import fase2_dir

    canales = str(Path(__file__).with_name("data") / "relevados.geojson")
    out_dir = fase2_dir()
    report: dict[str, Any] = {"canales": canales}
    for suffix in ("_glo30", "_gem15"):
        streams = str(out_dir / f"streams{suffix}.tif")
        print(f"[fase2] métricas {suffix} vs red relevada")
        report[suffix] = canal_metrics_impl(
            rasterio_module=rasterio,
            numpy_module=numpy,
            distance_transform_fn=distance_transform_edt,
            streams_path=streams,
            canales_geojson=canales,
        )
    report_path = str(out_dir / "metrics_report.json")
    Path(report_path).write_text(json_module.dumps(report, indent=2))
    for suffix in ("_glo30", "_gem15"):
        m = report[suffix]
        print(
            f"[fase2] {suffix}: mediana {m['median_cells']} celdas | "
            f"p90 {m['p90_cells']} | cobertura {m['coverage_frac']:.1%} "
            f"({m['n_points']} puntos)"
        )
    print(f"[fase2] reporte: {report_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
