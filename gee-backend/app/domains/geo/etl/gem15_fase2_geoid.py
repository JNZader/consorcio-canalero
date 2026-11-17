"""Fase 2 (issue #723), paso S2: mover el GEM-15 de EGM96 a EGM2008 ANTES de
compararlo con GLO-30.

H_egm2008 = H_egm96 + (N_egm96 - N_egm2008)

donde N es la ondulación geoidal muestreada bilinealmente de las grillas del
CDN de PROJ. S2 prohibe comparar cotas crudas entre datums: un offset constante
se cancela en la pendiente, pero la ONDULACION de la diferencia (~0.5-1.5 m en
decenas de km) puede redirigir el flujo en una llanura como esta.

Corre dentro del contenedor backend::

    docker compose exec backend python -m app.domains.geo.etl.gem15_fase2_geoid

Las grillas (2.7 MB + 80.6 MB) no viven en el repo: se bajan UNA vez al
volumen ``/data/geo/{area_id}/fase2/grids/`` con SHA256 pineado. Un checksum
que no coincide es fallo ruidoso, no un warning.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.domains.geo.etl.gem15_fase2_download import (
    DEFAULT_AREA_ID,
    DEFAULT_GEO_BASE,
    FASE2_DIR_NAME,
)

GEOID_GRID_BASE = "https://cdn.proj.org"
GEOID_GRIDS: dict[str, dict[str, str]] = {
    "egm96": {
        "filename": "us_nga_egm96_15.tif",
        "sha256": "db493027562c9b004d7220fa881f5603adada4e1c5029b933fa7de4547b0e78d",
    },
    "egm2008": {
        "filename": "us_nga_egm08_25.tif",
        "sha256": "4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a",
    },
}


def grids_dir(*, area_id: str = DEFAULT_AREA_ID, base_dir: str = DEFAULT_GEO_BASE) -> Path:
    return Path(base_dir) / area_id / FASE2_DIR_NAME / "grids"


def _sha256_matches(hashlib_module, path: Path, expected: str) -> bool:
    digest = hashlib_module.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def ensure_geoid_grids_impl(
    *,
    requests_module,
    hashlib_module,
    grids_dir: str,
    checksums: dict[str, str] | None = None,
) -> dict[str, Path]:
    """Descarga las grillas pineadas si faltan o si el checksum no coincide.

    Fail-closed: un .tmp corrupto se borra y se levanta RuntimeError — jamás
    queda una grilla sin verificar en el volumen.
    """
    expected = {
        name: (checksums or {}).get(name, spec["sha256"]) for name, spec in GEOID_GRIDS.items()
    }
    target_dir = Path(grids_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, spec in GEOID_GRIDS.items():
        url = f"{GEOID_GRID_BASE}/{spec['filename']}"
        final = target_dir / spec["filename"]
        paths[name] = final
        if final.exists() and _sha256_matches(hashlib_module, final, expected[name]):
            continue
        # .tmp.tif (no .tmp) para que el sweeper de .tmp.tif del pipeline
        # también barra los restos de las grillas si un run muere a mitad.
        tmp = final.with_suffix(".tmp.tif")
        response = requests_module.get(url, stream=True, timeout=600)
        response.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
        if not _sha256_matches(hashlib_module, tmp, expected[name]):
            tmp.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise RuntimeError(
                f"geoid grid {spec['filename']} no coincide su SHA256 pineado ({expected[name]}) — no se usa"
            )
        tmp.replace(final)
    return paths


def bilinear_sample(
    values,
    *,
    left: float,
    top: float,
    xres: float,
    yres: float,
    xs,
    ys,
):
    """Muestreo bilinear vectorizado de una grilla regular point-registered.

    Las grillas geoid del CDN de PROJ son point-registered: el valor vive en el
    CENTRO de cada celda (1440 valores de -180.0 a 179.75 con borde en
    -180.125), no en la esquina del transform. Anclar al borde desplaza el
    muestreo media celda (~13 km en la de 15'). Fuera de rango clampea al
    borde (grilla global, AOI lejos del antimeridiano: sin wrap).
    """
    import numpy as np

    arr = np.asarray(values, dtype="float64")
    height, width = arr.shape
    col = (np.asarray(xs, dtype="float64") - left) / xres - 0.5
    row = (top - np.asarray(ys, dtype="float64")) / yres - 0.5
    col = np.clip(col, 0.0, width - 1.0)
    row = np.clip(row, 0.0, height - 1.0)
    c0 = np.floor(col).astype("int64")
    r0 = np.floor(row).astype("int64")
    c1 = np.minimum(c0 + 1, width - 1)
    r1 = np.minimum(r0 + 1, height - 1)
    fc = col - c0
    fr = row - r0
    top_row = arr[r0, c0] * (1 - fc) + arr[r0, c1] * fc
    bottom_row = arr[r1, c0] * (1 - fc) + arr[r1, c1] * fc
    return top_row * (1 - fr) + bottom_row * fr


def apply_egm96_to_egm2008_impl(
    *,
    rasterio_module,
    numpy_module,
    dem_path: str,
    egm96_grid_path: str,
    egm2008_grid_path: str,
    output_path: str,
) -> str:
    """Escribe la copia EGM2008 del DEM GEM-15 (EGM96), misma grilla y nodata."""
    np = numpy_module
    with rasterio_module.open(dem_path) as dem_src:
        dem = dem_src.read(1).astype("float64")
        dem_transform = dem_src.transform
        dem_nodata = dem_src.nodata
        profile = dem_src.profile.copy()

    height, width = dem.shape
    # Centros de pixel de un Affine regular sin rotación, flatten C-order
    # (row-major): xs se repite por fila, ys repite cada fila ancho veces.
    t = dem_transform
    col_centers = np.arange(width, dtype="float64") * t.a + t.c + t.a / 2.0
    row_centers = np.arange(height, dtype="float64") * t.e + t.f + t.e / 2.0
    xs = np.tile(col_centers, height)
    ys = np.repeat(row_centers, width)

    def _read_grid(path: str) -> tuple[Any, float, float, float, float]:
        with rasterio_module.open(path) as src:
            vals = src.read(1).astype("float64")
            t = src.transform
            return vals, t.c, t.f, abs(t.a), abs(t.e)

    egm96_vals, g96_left, g96_top, g96_xres, g96_yres = _read_grid(egm96_grid_path)
    egm08_vals, g08_left, g08_top, g08_xres, g08_yres = _read_grid(egm2008_grid_path)
    # Cada grilla se muestrea con SU PROPIA geometría — las dos del CDN difieren
    # en resolución y borde (1440x721 @0.25° vs 8640x4321 @~0.0417°). Compartir
    # la geometría de una entre ambas produce offsets de ~20 m silenciosos.
    n96 = bilinear_sample(
        egm96_vals, left=g96_left, top=g96_top, xres=g96_xres, yres=g96_yres, xs=xs, ys=ys
    ).reshape(height, width)
    n08 = bilinear_sample(
        egm08_vals, left=g08_left, top=g08_top, xres=g08_xres, yres=g08_yres, xs=xs, ys=ys
    ).reshape(height, width)

    corrected = dem + (n96 - n08)
    if dem_nodata is not None:
        mask = dem == dem_nodata
        corrected[mask] = dem_nodata
        profile["nodata"] = dem_nodata
    profile.update(dtype="float32", compress="deflate", predictor=3)
    with rasterio_module.open(output_path, "w", **profile) as dst:
        dst.write(corrected.astype("float32"), 1)
    return output_path


def main() -> int:  # pragma: no cover — needs the fase 2 rasters on the volume
    import hashlib
    import requests
    import rasterio
    import numpy

    from app.domains.geo.etl.gem15_fase2_download import fase2_paths

    paths = fase2_paths()
    dir_path = grids_dir()
    grids = ensure_geoid_grids_impl(
        requests_module=requests,
        hashlib_module=hashlib,
        grids_dir=str(dir_path),
    )
    output = str(Path(paths["gem15"]).with_name("dem_gem15_egm2008.tif"))
    print(f"[fase2] GEM-15 EGM96 -> EGM2008: {paths['gem15']} -> {output}")
    apply_egm96_to_egm2008_impl(
        rasterio_module=rasterio,
        numpy_module=numpy,
        dem_path=paths["gem15"],
        egm96_grid_path=str(grids["egm96"]),
        egm2008_grid_path=str(grids["egm2008"]),
        output_path=output,
    )
    print("[fase2] GEM-15 ya en EGM2008 — ready for T3 (debias)")
    return 0


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
