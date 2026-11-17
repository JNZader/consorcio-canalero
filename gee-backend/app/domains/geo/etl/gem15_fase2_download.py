"""Fase 2 (issue #723): download the GEM-15 DTM and the GLO-30 DEM of the SAME
AOI, on the SAME grid, into rasters of their own.

Runs inside the deployed backend container, like the other geo ETL modules::

    docker compose exec backend python -m app.domains.geo.etl.gem15_fase2_download

Design constraints (feature doc ``odd/tasks/gem15-fase2-hidrologia.md``):

- ``download_dem_impl`` in ``processing_wbt_support`` stays untouched and is the
  GLO-30 downloader; this module owns only the GEM-15 twin. Never retarget it.
- Grid parity comes from mirroring its exact ``getDownloadURL`` contract (same
  region wrapper, same scale, EPSG:4326): with one ``scale`` for both sources
  the two GeoTIFFs land on the same grid, which is the precondition for every
  later comparison step (S2 forbids comparing heights that differ by datum).
- Outputs live under ``/data/geo/{area_id}/fase2/`` — beside, never inside, the
  pipeline's ``output/`` directory whose ``natural_flow_dir_{area_id}`` raster
  the canal-catchment ficha reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

GEM15_ASSET = "projects/climate-and-sustainability/assets/gem-15_v1"
GEM15_BAND = "dtm"
FASE2_DIR_NAME = "fase2"
DEFAULT_GEO_BASE = "/data/geo"
DEFAULT_AREA_ID = "zona_principal"
#: GEM-15 is 15 m native but rides the comparison at 30 m — same rationale as
#: the fase 1 profile series: this is a comparison, not a product.
COMPARISON_SCALE_M = 30


def fase2_paths(
    *, area_id: str = DEFAULT_AREA_ID, base_dir: str = DEFAULT_GEO_BASE
) -> dict[str, str]:
    fase2_dir = Path(base_dir) / area_id / FASE2_DIR_NAME
    return {
        "glo30": str(fase2_dir / "dem_glo30_raw.tif"),
        "gem15": str(fase2_dir / "dem_gem15_raw.tif"),
    }


def download_gem15_dtm_impl(
    *,
    ee_module,
    requests_module,
    rasterio_module,
    ensure_parent_dir,
    zona_geometry: dict[str, Any],
    output_path: str,
    scale: int = COMPARISON_SCALE_M,
) -> str:
    """GEM-15 twin of ``processing_wbt_support.download_dem_impl``.

    Same structure on purpose: select the band, clip to the zone, fetch the
    GeoTIFF by URL, recompress, drop the ``.tmp``. Any drift from that contract
    breaks grid parity with the GLO-30 side, so the two implementations are
    meant to stay line-for-line comparable.
    """
    dtm = ee_module.ImageCollection(GEM15_ASSET).mosaic().select(GEM15_BAND)
    region = ee_module.Geometry(zona_geometry)
    clipped = dtm.clip(region)
    url = clipped.getDownloadURL(
        {"format": "GEO_TIFF", "scale": scale, "region": region, "crs": "EPSG:4326"}
    )
    ensure_parent_dir(output_path)
    tmp_path = str(Path(output_path).with_suffix(".tmp.tif"))
    response = requests_module.get(url, stream=True, timeout=300)
    response.raise_for_status()
    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    with rasterio_module.open(tmp_path) as src:
        data = src.read(1)
        profile = src.profile.copy()
        profile.update(compress="deflate", predictor=2)
        # GEE rellena los huecos del asset con -9999 SIN declararlo como
        # nodata. Sin esta declaración, el sentinel viaja crudo por toda la
        # cadena (geoid lo corrompe sumándole la corrección) y WBT falla
        # SILENCIOSAMENTE (exit 0 sin archivo) sobre el DEM — verificado en el
        # contenedor el 2026-11-17. El gemelo GLO-30 no lo necesita: su AOI
        # viene cubierto y sin huecos.
        if profile.get("nodata") is None and data.min() <= -9999:
            profile["nodata"] = -9999.0
        with rasterio_module.open(output_path, "w", **profile) as dst:
            dst.write(src.read())
    Path(tmp_path).unlink(missing_ok=True)
    return output_path


def main() -> int:  # pragma: no cover — needs GEE credentials and the volume
    import ee
    import rasterio
    import requests

    from app.domains.geo.gee_service import get_gee_service
    from app.domains.geo.processing import _ensure_parent_dir
    from app.domains.geo.processing_wbt_support import download_dem_impl

    gee_svc = get_gee_service()
    zona_geometry = gee_svc.zona.geometry().getInfo()

    paths = fase2_paths()
    print(f"[fase2] GLO-30  -> {paths['glo30']}")
    download_dem_impl(
        ee_module=ee,
        requests_module=requests,
        rasterio_module=rasterio,
        ensure_parent_dir=_ensure_parent_dir,
        zona_geometry=zona_geometry,
        output_path=paths["glo30"],
        scale=COMPARISON_SCALE_M,
    )
    print(f"[fase2] GEM-15  -> {paths['gem15']}")
    download_gem15_dtm_impl(
        ee_module=ee,
        requests_module=requests,
        rasterio_module=rasterio,
        ensure_parent_dir=_ensure_parent_dir,
        zona_geometry=zona_geometry,
        output_path=paths["gem15"],
        scale=COMPARISON_SCALE_M,
    )
    print("[fase2] both DEMs on the same grid — ready for T2 (geoid)")
    return 0


if __name__ == "__main__":  # pragma: no cover — module entry point
    raise SystemExit(main())
