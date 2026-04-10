"""Support helpers for GEE imagery and image explorer payloads."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

VIS_PRESETS: Dict[str, Dict[str, Any]] = {
    "rgb": {
        "bands": ["B4", "B3", "B2"],
        "min": 0,
        "max": 3000,
        "description": "Color natural (RGB)",
    },
    "falso_color": {
        "bands": ["B8", "B4", "B3"],
        "min": 0,
        "max": 5000,
        "description": "Falso color (vegetacion en rojo)",
    },
    "agricultura": {
        "bands": ["B11", "B8", "B2"],
        "min": 0,
        "max": 5000,
        "description": "Agricultura (suelo en magenta)",
    },
    "ndwi": {
        "index": "ndwi",
        "min": -0.5,
        "max": 0.5,
        "palette": ["brown", "white", "blue"],
        "description": "Indice de agua NDWI",
    },
    "mndwi": {
        "index": "mndwi",
        "min": -0.5,
        "max": 0.5,
        "palette": ["brown", "white", "cyan"],
        "description": "Indice de agua modificado MNDWI",
    },
    "ndvi": {
        "index": "ndvi",
        "min": -0.2,
        "max": 0.8,
        "palette": ["red", "yellow", "green", "darkgreen"],
        "description": "Indice de vegetacion NDVI",
    },
    "inundacion": {
        "index": "flood",
        "palette": ["0000FF"],
        "description": "Deteccion de agua (NDWI > 0)",
    },
}


def mask_clouds_s2(image) -> Any:
    scl = image.select("SCL")
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
    return image.updateMask(mask)


def collection_dates(collection, distinct_collection_dates_fn) -> list[str]:
    dates = distinct_collection_dates_fn(collection)
    return sorted(dates) if dates else []


def build_sentinel2_collection(
    ee_module, zona, start_date: date, end_date: date, max_cloud: int, *, use_toa: bool
):
    collection_name = (
        "COPERNICUS/S2_HARMONIZED" if use_toa else "COPERNICUS/S2_SR_HARMONIZED"
    )
    collection = (
        ee_module.ImageCollection(collection_name)
        .filterBounds(zona)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee_module.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
    )
    return collection_name, collection


def build_sentinel1_collection(ee_module, zona, start_date: date, end_date: date):
    return (
        ee_module.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(zona)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee_module.Filter.eq("instrumentMode", "IW"))
        .filter(ee_module.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    )


def build_dem_download_payload(
    ee_module, zona, *, geometry=None, scale: int = 30
) -> Dict[str, Any]:
    region = geometry or zona.geometry()
    dem = ee_module.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    clipped = dem.clip(region)
    url = clipped.getDownloadURL(
        {"format": "GEO_TIFF", "scale": scale, "region": region, "crs": "EPSG:4326"}
    )
    return {
        "download_url": url,
        "scale": scale,
        "crs": "EPSG:4326",
        "image": "COPERNICUS/DEM/GLO30",
    }


def build_sentinel2_tiles_payload(
    ee_module, zona, *, start_date: date, end_date: date, max_cloud: int
) -> Dict[str, Any]:
    sentinel2 = (
        ee_module.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(zona)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee_module.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
    )
    count = sentinel2.size().getInfo()
    if count == 0:
        return {
            "error": "No se encontraron imagenes Sentinel-2",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
    map_id = (
        sentinel2.mosaic()
        .clip(zona)
        .getMapId({"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000})
    )
    return {
        "tile_url": map_id["tile_fetcher"].url_format,
        "imagenes_disponibles": count,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def build_flood_comparison_payload(
    explorer, *, flood_date: date, normal_date: date, days_buffer: int, max_cloud: int
) -> Dict[str, Any]:
    flood_result = explorer.get_sentinel2_image(
        flood_date, days_buffer, max_cloud, "inundacion"
    )
    normal_result = explorer.get_sentinel2_image(
        normal_date, days_buffer, max_cloud, "rgb"
    )
    flood_rgb = explorer.get_sentinel2_image(flood_date, days_buffer, max_cloud, "rgb")
    return {
        "flood_date": flood_date.isoformat(),
        "normal_date": normal_date.isoformat(),
        "flood_detection": flood_result,
        "flood_rgb": flood_rgb,
        "normal_rgb": normal_result,
    }


def available_visualizations_payload(
    vis_presets: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    return [
        {"id": key, "description": value["description"]}
        for key, value in vis_presets.items()
    ]


def build_sentinel2_payload(
    explorer,
    *,
    target_date: date,
    days_buffer: int,
    max_cloud: int,
    visualization: str,
    use_median: bool,
) -> Dict[str, Any]:
    start_date = target_date - timedelta(days=days_buffer)
    end_date = target_date + timedelta(days=days_buffer)

    use_toa = target_date.year < 2019
    collection_name, collection = explorer._sentinel2_collection(
        start_date,
        end_date,
        max_cloud,
        use_toa=use_toa,
    )

    count = collection.size().getInfo()
    if count == 0:
        return {
            "error": "No se encontraron imagenes para la fecha seleccionada",
            "target_date": target_date.isoformat(),
            "days_buffer": days_buffer,
            "max_cloud": max_cloud,
            "sugerencia": "Intenta aumentar days_buffer o max_cloud",
        }

    dates_list = explorer._collection_dates(collection)
    if use_toa:
        composite = collection.mosaic().clip(explorer.zona)
    else:
        masked_collection = collection.map(explorer._mask_clouds_s2)
        composite = (
            masked_collection.median().clip(explorer.zona)
            if use_median
            else masked_collection.mosaic().clip(explorer.zona)
        )

    preset = explorer.VIS_PRESETS.get(visualization, explorer.VIS_PRESETS["rgb"])
    if "index" in preset:
        if preset["index"] == "ndwi":
            image = composite.normalizedDifference(["B3", "B8"]).rename("index")
        elif preset["index"] == "mndwi":
            image = composite.normalizedDifference(["B3", "B11"]).rename("index")
        elif preset["index"] == "ndvi":
            image = composite.normalizedDifference(["B8", "B4"]).rename("index")
        else:
            ndwi = composite.normalizedDifference(["B3", "B8"])
            image = ndwi.gt(0).selfMask().rename("index")
        vis_params: Dict[str, Any] = {
            "min": preset.get("min", 0),
            "max": preset.get("max", 1),
            "palette": preset.get("palette", ["white", "blue"]),
        }
    else:
        image = composite
        vis_params = {
            "bands": preset["bands"],
            "min": preset["min"],
            "max": preset["max"],
        }

    map_id = image.getMapId(vis_params)
    return {
        "tile_url": map_id["tile_fetcher"].url_format,
        "target_date": target_date.isoformat(),
        "dates_available": dates_list,
        "images_count": count,
        "visualization": visualization,
        "visualization_description": preset["description"],
        "sensor": "Sentinel-2",
        "collection": collection_name,
    }


def build_sentinel1_payload(
    explorer,
    *,
    target_date: date,
    days_buffer: int,
    visualization: str,
) -> Dict[str, Any]:
    start_date = target_date - timedelta(days=days_buffer)
    end_date = target_date + timedelta(days=days_buffer)
    collection = explorer._sentinel1_collection(start_date, end_date)

    count = collection.size().getInfo()
    if count == 0:
        return {
            "error": "No se encontraron imagenes SAR para la fecha seleccionada",
            "target_date": target_date.isoformat(),
            "days_buffer": days_buffer,
        }

    dates_list = explorer._collection_dates(collection)
    mosaic = collection.select("VV").mosaic().clip(explorer.zona)
    if visualization == "vv_flood":
        image = mosaic.lt(-15).selfMask()
        vis_params = {"palette": ["00FFFF"]}
        description = "Deteccion de agua (SAR < -15 dB)"
    else:
        image = mosaic
        vis_params = {"min": -25, "max": 0}
        description = "Radar SAR banda VV"

    map_id = image.getMapId(vis_params)
    return {
        "tile_url": map_id["tile_fetcher"].url_format,
        "target_date": target_date.isoformat(),
        "dates_available": dates_list,
        "images_count": count,
        "visualization": visualization,
        "visualization_description": description,
        "sensor": "Sentinel-1",
        "collection": "COPERNICUS/S1_GRD",
    }


def build_available_dates_payload(
    explorer, *, year: int, month: int, sensor: str, max_cloud: int
) -> Dict[str, Any]:
    start_date = date(year, month, 1)
    end_date = date(year, month, __import__("calendar").monthrange(year, month)[1])
    end_date_exclusive = end_date + timedelta(days=1)

    if sensor == "sentinel2":
        _, collection = explorer._sentinel2_collection(
            start_date,
            end_date_exclusive,
            max_cloud,
            use_toa=year < 2019,
        )
    else:
        collection = explorer._sentinel1_collection(start_date, end_date_exclusive)

    dates_list = explorer._collection_dates(collection)
    return {
        "dates": dates_list if dates_list else [],
        "sensor": sensor,
        "year": year,
        "month": month,
        "total": len(dates_list) if dates_list else 0,
    }


def build_sar_time_series_payload(
    explorer, ee_module, *, start_date: date, end_date: date, scale: int
) -> Dict[str, Any]:
    collection = (
        ee_module.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(explorer.zona)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee_module.Filter.eq("instrumentMode", "IW"))
        .filter(ee_module.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .select("VV")
    )

    count = collection.size().getInfo()
    if count == 0:
        return {
            "dates": [],
            "vv_mean": [],
            "image_count": 0,
            "scale_m": scale,
            "warning": "No Sentinel-1 images found in date range",
        }

    def _extract_vv_mean(image):
        img_date = ee_module.Date(image.get("system:time_start")).format("YYYY-MM-dd")
        stats = image.reduceRegion(
            reducer=ee_module.Reducer.mean(),
            geometry=explorer.zona.geometry(),
            scale=scale,
            bestEffort=True,
        )
        return ee_module.Feature(None, {"date": img_date, "vv_mean": stats.get("VV")})

    features = collection.map(_extract_vv_mean)
    results = features.getInfo()["features"]
    dates: List[str] = []
    vv_mean: List[float] = []
    for feat in results:
        props = feat.get("properties", {})
        vv_val = props.get("vv_mean")
        if vv_val is not None:
            dates.append(props["date"])
            vv_mean.append(round(float(vv_val), 4))

    return {
        "dates": dates,
        "vv_mean": vv_mean,
        "image_count": len(dates),
        "scale_m": scale,
    }
