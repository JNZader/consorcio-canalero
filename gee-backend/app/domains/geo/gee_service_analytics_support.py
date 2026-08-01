"""Support helpers for GEE road-network stats and analytical payloads."""

from __future__ import annotations

import statistics as _statistics
from datetime import datetime as _datetime
from typing import Any, Dict, List


def build_consorcios_camineros(features: list[dict[str, Any]], safe_float) -> List[Dict[str, Any]]:
    consorcios_map: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties", {})
        ccn = props.get("ccn", "Sin consorcio")
        ccc = props.get("ccc", "N/A")

        if ccn not in consorcios_map:
            consorcios_map[ccn] = {
                "nombre": ccn,
                "codigo": ccc,
                "tramos": 0,
                "longitud_total_km": 0.0,
            }

        consorcios_map[ccn]["tramos"] += 1
        consorcios_map[ccn]["longitud_total_km"] += safe_float(props.get("lzn", 0))

    consorcios = list(consorcios_map.values())
    consorcios.sort(key=lambda x: x["nombre"])
    return consorcios


def build_colored_roads(
    features: list[dict[str, Any]],
    *,
    colors: list[str],
    safe_float,
) -> Dict[str, Any]:
    consorcios_unicos: List[str] = []
    for feature in features:
        ccn = feature.get("properties", {}).get("ccn", "Sin consorcio")
        if ccn not in consorcios_unicos:
            consorcios_unicos.append(ccn)

    consorcios_unicos.sort()
    color_map = {ccn: colors[i % len(colors)] for i, ccn in enumerate(consorcios_unicos)}

    stats_map: Dict[str, Dict[str, Any]] = {}
    for ccn in consorcios_unicos:
        ccc = next(
            (
                feature.get("properties", {}).get("ccc", "")
                for feature in features
                if feature.get("properties", {}).get("ccn") == ccn
            ),
            "",
        )
        stats_map[ccn] = {
            "nombre": ccn,
            "codigo": ccc,
            "color": color_map[ccn],
            "tramos": 0,
            "longitud_km": 0.0,
        }

    for feature in features:
        props = feature.get("properties", {})
        ccn = props.get("ccn", "Sin consorcio")
        feature["properties"]["color"] = color_map.get(ccn, "#888888")
        stats_map[ccn]["tramos"] += 1
        stats_map[ccn]["longitud_km"] += safe_float(props.get("lzn", 0))

    for ccn in stats_map:
        stats_map[ccn]["longitud_km"] = round(stats_map[ccn]["longitud_km"], 2)

    consorcios_lista = list(stats_map.values())
    consorcios_lista.sort(key=lambda x: x["nombre"])

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "total_tramos": len(features),
            "total_consorcios": len(consorcios_unicos),
            "total_km": round(sum(c["longitud_km"] for c in consorcios_lista), 2),
        },
        "consorcios": consorcios_lista,
    }


def build_consorcio_stats(
    features, *, ensure_bucket, update_breakdown, safe_float
) -> Dict[str, Any]:
    stats: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties", {})
        ccn = props.get("ccn", "Sin consorcio")
        ccc = props.get("ccc", "N/A")
        bucket = ensure_bucket(stats, nombre=ccn, codigo=ccc)
        bucket["tramos"] += 1

        length_km = safe_float(props.get("lzn", 0))
        bucket["longitud_km"] += length_km
        update_breakdown(bucket["por_jerarquia"], props.get("hct", "Desconocido"), length_km)
        update_breakdown(bucket["por_superficie"], props.get("rst", "Desconocido"), length_km)

    for ccn in stats:
        stats[ccn]["longitud_km"] = round(stats[ccn]["longitud_km"], 2)
        for key in stats[ccn]["por_jerarquia"]:
            stats[ccn]["por_jerarquia"][key]["km"] = round(
                stats[ccn]["por_jerarquia"][key]["km"], 2
            )
        for key in stats[ccn]["por_superficie"]:
            stats[ccn]["por_superficie"][key]["km"] = round(
                stats[ccn]["por_superficie"][key]["km"], 2
            )

    consorcios_lista = list(stats.values())
    consorcios_lista.sort(key=lambda x: -x["longitud_km"])

    return {
        "consorcios": consorcios_lista,
        "totales": {
            "consorcios": len(consorcios_lista),
            "tramos": sum(c["tramos"] for c in consorcios_lista),
            "longitud_km": round(sum(c["longitud_km"] for c in consorcios_lista), 2),
        },
    }


def compute_ndwi_baselines_payload(
    ee_module,
    logger,
    *,
    zones: list[dict],
    dry_season_months: list[int],
    years_back: int,
) -> list[dict]:
    now = _datetime.utcnow()
    start_dt = now.replace(year=now.year - years_back)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = now.strftime("%Y-%m-%d")

    month_filters = [ee_module.Filter.calendarRange(m, m, "month") for m in dry_season_months]
    month_filter = (
        ee_module.Filter.Or(*month_filters) if len(month_filters) > 1 else month_filters[0]
    )

    collection = (
        ee_module.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start_str, end_str)
        .filter(ee_module.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .filter(month_filter)
        .map(lambda img: img.normalizedDifference(["B3", "B8"]).rename("ndwi"))
    )

    results = []
    for zone in zones:
        try:
            geometry = zone["ee_geometry"]

            def _get_mean(img):
                val = img.reduceRegion(
                    reducer=ee_module.Reducer.mean(),
                    geometry=geometry,
                    scale=10,
                    maxPixels=1e9,
                ).get("ndwi")
                return ee_module.Feature(None, {"ndwi": val})

            ndwi_values = (
                collection.map(_get_mean)
                .filter(ee_module.Filter.notNull(["ndwi"]))
                .aggregate_array("ndwi")
                .getInfo()
            )
            if not ndwi_values:
                logger.warning(
                    "compute_ndwi_baselines: no dry-season images for zone %s",
                    zone["id"],
                )
                continue
            mean_val = _statistics.mean(ndwi_values)
            std_val = _statistics.stdev(ndwi_values) if len(ndwi_values) > 1 else 0.05
            results.append(
                {
                    "zona_id": str(zone["id"]),
                    "ndwi_mean": round(mean_val, 4),
                    "ndwi_std": round(max(std_val, 0.001), 4),
                    "sample_count": len(ndwi_values),
                }
            )
        except Exception as exc:
            logger.warning("compute_ndwi_baselines: failed for zone %s: %s", zone.get("id"), exc)
    return results


# ── CHIRPS precipitation normals ─────────────────────────────────────────

CHIRPS_COLLECTION_ID = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_NORMAL_START_YEAR = 1991
CHIRPS_NORMAL_END_YEAR = 2020
CHIRPS_NORMAL_PERIOD = "1991-2020"
# CHIRPS native resolution is 0.05° (~5.5 km). The raw GEE download stays at
# native scale; the warp to EPSG:32720 at 5 000 m happens in the ETL runner
# (etl/generate_chirps_normals.py), never here.
CHIRPS_NATIVE_SCALE_M = 5566


def export_chirps_monthly_normals_payload(
    ee_module,
    logger,
    *,
    region: dict,
    start_year: int = CHIRPS_NORMAL_START_YEAR,
    end_year: int = CHIRPS_NORMAL_END_YEAR,
    scale: int = CHIRPS_NATIVE_SCALE_M,
) -> List[Dict[str, Any]]:
    """Build the CHIRPS monthly precipitation normals and resolve a GEE
    download URL for each.

    Twelve monthly normals (January-December) plus one annual total, clipped to
    ``region``. For month *m* the normal is the mean, across the years
    ``[start_year, end_year]``, of that month's daily-precipitation sum — i.e.
    mean accumulated millimetres for that month over the normals period. The
    annual normal is the sum of the twelve monthly normals.

    This is the GEE-side export step ONLY: it computes the images and resolves a
    ``getDownloadURL`` per output. Downloading the bytes, warping to EPSG:32720
    at 5 000 m and registering the rasters as ``geo_layers`` rows are the ETL
    runner's job (``etl/generate_chirps_normals.py``), not this helper's.

    Returns 13 descriptors ``{"mes": 1..12 | "anual", "download_url": <url>}`` in
    calendar order (the annual total last).
    """
    if start_year > end_year:
        raise ValueError(f"start_year ({start_year}) must be <= end_year ({end_year})")
    geometry = ee_module.Geometry(region)
    collection = ee_module.ImageCollection(CHIRPS_COLLECTION_ID).filterDate(
        f"{start_year}-01-01", f"{end_year + 1}-01-01"
    )

    def _monthly_normal(month: int):
        # Sum each year's daily precipitation for this month, then average the
        # per-year sums across the normals period -> mean monthly millimetres.
        yearly_sums = [
            collection.filter(ee_module.Filter.calendarRange(year, year, "year"))
            .filter(ee_module.Filter.calendarRange(month, month, "month"))
            .sum()
            for year in range(start_year, end_year + 1)
        ]
        return ee_module.ImageCollection(yearly_sums).mean().rename("precip_mm").clip(geometry)

    monthly_images = [_monthly_normal(month) for month in range(1, 13)]
    annual_image = (
        ee_module.ImageCollection(monthly_images).sum().rename("precip_mm").clip(geometry)
    )

    outputs: List[tuple[Any, Any]] = [
        (month, image) for month, image in zip(range(1, 13), monthly_images)
    ]
    outputs.append(("anual", annual_image))

    descriptors: List[Dict[str, Any]] = []
    for mes, image in outputs:
        url = image.getDownloadURL(
            {
                "format": "GEO_TIFF",
                "scale": scale,
                "region": geometry,
                "crs": "EPSG:4326",
            }
        )
        descriptors.append({"mes": mes, "download_url": url})
    logger.info(
        "export_chirps_monthly_normals: resolved %d download URLs (period %s-%s)",
        len(descriptors),
        start_year,
        end_year,
    )
    return descriptors


def get_landcover_c_payload(ee_module, logger, *, zone_geometry) -> float | None:
    try:
        class_values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        c_x100 = [20, 35, 40, 55, 75, 65, 10, 5, 15, 20, 30]
        lc_image = ee_module.ImageCollection("ESA/WorldCover/v200").first().select("Map")
        c_band = lc_image.remap(class_values, c_x100, defaultValue=40).rename("c_x100")
        result = (
            c_band.reduceRegion(
                reducer=ee_module.Reducer.mean(),
                geometry=zone_geometry,
                scale=10,
                maxPixels=1e9,
            )
            .get("c_x100")
            .getInfo()
        )
        if result is None:
            return None
        return round(float(result) / 100.0, 3)
    except Exception as exc:
        logger.warning("get_landcover_c_coefficient failed: %s", exc)
        return None
