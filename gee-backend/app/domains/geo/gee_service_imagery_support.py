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



LANDSAT_SENSORS: Dict[str, Dict[str, Any]] = {
    "landsat8": {
        "label": "Landsat 8",
        "collection": "LANDSAT/LC08/C02/T1_TOA",
        "rgb": ["B4", "B3", "B2"],
        "false_color": ["B5", "B4", "B3"],
        "agriculture": ["B6", "B5", "B2"],
        "ndwi": ["B3", "B5"],
        "mndwi": ["B3", "B6"],
        "max": 0.35,
        "notes": None,
    },
    "landsat7": {
        "label": "Landsat 7",
        "collection": "LANDSAT/LE07/C02/T1_TOA",
        "rgb": ["B3", "B2", "B1"],
        "false_color": ["B4", "B3", "B2"],
        "agriculture": ["B5", "B4", "B1"],
        "ndwi": ["B2", "B4"],
        "mndwi": ["B2", "B5"],
        "max": 0.35,
        "notes": "Landsat 7 puede mostrar franjas/gaps por SLC-off desde 2003.",
    },
    "landsat5": {
        "label": "Landsat 5",
        "collection": "LANDSAT/LT05/C02/T1_TOA",
        "rgb": ["B3", "B2", "B1"],
        "false_color": ["B4", "B3", "B2"],
        "agriculture": ["B5", "B4", "B1"],
        "ndwi": ["B2", "B4"],
        "mndwi": ["B2", "B5"],
        "max": 0.35,
        "notes": None,
    },
}

OPTICAL_VISUALIZATION_DESCRIPTIONS: Dict[str, str] = {
    "rgb": "Color natural (RGB)",
    "falso_color": "Falso color (vegetacion en rojo)",
    "agricultura": "Agricultura / humedad (SWIR-NIR-azul)",
    "ndwi": "Indice de agua NDWI",
    "mndwi": "Indice de agua modificado MNDWI",
    "ndvi": "Indice de vegetacion NDVI",
    "inundacion": "Deteccion de agua (NDWI > 0)",
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


def build_landsat_collection(
    ee_module, zona, sensor: str, start_date: date, end_date: date, max_cloud: int
):
    cfg = LANDSAT_SENSORS[sensor]
    return (
        ee_module.ImageCollection(cfg["collection"])
        .filterBounds(zona)
        .filterDate(start_date.isoformat(), end_date.isoformat())
        .filter(ee_module.Filter.lt("CLOUD_COVER", max_cloud))
    )


def _render_landsat_image(image, cfg: Dict[str, Any], visualization: str):
    if visualization == "ndwi":
        rendered = image.normalizedDifference(cfg["ndwi"]).rename("index")
        vis_params: Dict[str, Any] = {
            "min": -0.5,
            "max": 0.5,
            "palette": ["brown", "white", "blue"],
        }
        description = OPTICAL_VISUALIZATION_DESCRIPTIONS["ndwi"]
    elif visualization == "mndwi":
        rendered = image.normalizedDifference(cfg["mndwi"]).rename("index")
        vis_params = {
            "min": -0.5,
            "max": 0.5,
            "palette": ["brown", "white", "cyan"],
        }
        description = OPTICAL_VISUALIZATION_DESCRIPTIONS["mndwi"]
    elif visualization == "ndvi":
        nir = cfg["false_color"][0]
        red = cfg["rgb"][0]
        rendered = image.normalizedDifference([nir, red]).rename("index")
        vis_params = {
            "min": -0.2,
            "max": 0.8,
            "palette": ["red", "yellow", "green", "darkgreen"],
        }
        description = OPTICAL_VISUALIZATION_DESCRIPTIONS["ndvi"]
    elif visualization == "inundacion":
        ndwi = image.normalizedDifference(cfg["ndwi"])
        rendered = ndwi.gt(0).selfMask().rename("index")
        vis_params = {"palette": ["0000FF"]}
        description = OPTICAL_VISUALIZATION_DESCRIPTIONS["inundacion"]
    else:
        band_key = {
            "falso_color": "false_color",
            "agricultura": "agriculture",
        }.get(visualization, "rgb")
        rendered = image
        vis_params = {"bands": cfg[band_key], "min": 0, "max": cfg["max"]}
        description = OPTICAL_VISUALIZATION_DESCRIPTIONS.get(
            visualization, OPTICAL_VISUALIZATION_DESCRIPTIONS["rgb"]
        )
    return rendered, vis_params, description


def _landsat_scene_metadata(props: Dict[str, Any], fallback_id: str) -> Dict[str, Any]:
    timestamp = props.get("system:time_start")
    scene_date = None
    if isinstance(timestamp, (int, float)):
        scene_date = (date(1970, 1, 1) + timedelta(milliseconds=int(timestamp))).isoformat()
    return {
        "id": props.get("system:index") or fallback_id,
        "date": scene_date,
        "cloud_cover": props.get("CLOUD_COVER"),
        "path": props.get("WRS_PATH"),
        "row": props.get("WRS_ROW"),
    }


def build_landsat_payload(
    explorer,
    *,
    sensor: str,
    target_date: date,
    days_buffer: int,
    max_cloud: int,
    visualization: str,
    use_median: bool,
) -> Dict[str, Any]:
    cfg = LANDSAT_SENSORS[sensor]
    start_date = target_date - timedelta(days=days_buffer)
    end_date = target_date + timedelta(days=days_buffer)
    collection = explorer._landsat_collection(sensor, start_date, end_date, max_cloud)

    count = collection.size().getInfo()
    if count == 0:
        return {
            "error": f"No se encontraron imagenes {cfg['label']} para la fecha seleccionada",
            "target_date": target_date.isoformat(),
            "days_buffer": days_buffer,
            "max_cloud": max_cloud,
            "sugerencia": "Intenta aumentar days_buffer o max_cloud, o probar otro Landsat/Sentinel-1.",
        }

    dates_list = explorer._collection_dates(collection)
    composition_mode = "scene"
    notes = cfg.get("notes")

    if use_median and sensor == "landsat7":
        primary = explorer._landsat_collection(
            sensor, target_date, target_date + timedelta(days=1), max_cloud
        )
        primary_count = primary.size().getInfo()
        fill_image = collection.median()
        if primary_count > 0:
            # Landsat 7 SLC-off leaves masked gaps. Preserve the selected-day
            # scene and use the temporal median only where that scene has no data.
            composite = primary.mosaic().unmask(fill_image).clip(explorer.zona)
            composition_mode = "gapfill"
            notes = (
                "Landsat 7 gap-fill: escena del dia preservada; "
                "imagenes cercanas solo rellenan franjas/gaps SLC-off."
            )
        else:
            composite = fill_image.clip(explorer.zona)
            composition_mode = "composite"
            notes = (
                "Landsat 7 compuesto temporal: no habia escena exacta del dia; "
                "se uso mediana de la ventana seleccionada."
            )
    else:
        composite = (collection.median() if use_median else collection.mosaic()).clip(explorer.zona)
        if use_median:
            composition_mode = "composite"

    image, vis_params, description = _render_landsat_image(composite, cfg, visualization)

    map_id = image.getMapId(vis_params)
    return {
        "tile_url": map_id["tile_fetcher"].url_format,
        "target_date": target_date.isoformat(),
        "dates_available": dates_list,
        "images_count": count,
        "visualization": visualization,
        "visualization_description": description,
        "sensor": cfg["label"],
        "collection": cfg["collection"],
        "composition_mode": composition_mode,
        "notes": notes,
        "days_buffer": days_buffer,
        "max_cloud": max_cloud,
    }


def build_landsat_scenes_payload(
    explorer,
    ee_module,
    *,
    sensor: str,
    target_date: date,
    days_buffer: int,
    max_cloud: int,
    visualization: str,
    limit: int = 12,
) -> Dict[str, Any]:
    cfg = LANDSAT_SENSORS[sensor]
    start_date = target_date - timedelta(days=days_buffer)
    end_date = target_date + timedelta(days=days_buffer)
    collection = explorer._landsat_collection(sensor, start_date, end_date, max_cloud).sort(
        "system:time_start"
    )
    count = collection.size().getInfo()
    if count == 0:
        return {
            "target_date": target_date.isoformat(),
            "sensor": cfg["label"],
            "collection": cfg["collection"],
            "scenes": [],
            "total": 0,
            "notes": cfg.get("notes"),
        }

    safe_limit = max(1, min(limit, 24))
    list_size = min(count, safe_limit)
    collection_list = collection.toList(list_size)
    metadata_items = collection_list.getInfo()
    scenes = []

    for index, item in enumerate(metadata_items):
        props = item.get("properties", {}) if isinstance(item, dict) else {}
        metadata = _landsat_scene_metadata(props, item.get("id", str(index)))
        raw_image = ee_module.Image(collection_list.get(index)).clip(explorer.zona)
        image, vis_params, description = _render_landsat_image(raw_image, cfg, visualization)
        map_id = image.getMapId(vis_params)
        scene_id = str(metadata["id"])
        path = metadata.get("path")
        row = metadata.get("row")
        label_parts = [metadata.get("date") or target_date.isoformat(), scene_id]
        if path is not None and row is not None:
            label_parts.append(f"P{path}/R{row}")
        scenes.append(
            {
                "id": scene_id,
                "label": " · ".join(str(part) for part in label_parts if part),
                "tile_url": map_id["tile_fetcher"].url_format,
                "target_date": metadata.get("date") or target_date.isoformat(),
                "visualization": visualization,
                "visualization_description": description,
                "sensor": cfg["label"],
                "collection": cfg["collection"],
                "images_count": 1,
                "composition_mode": "scene",
                "cloud_cover": metadata.get("cloud_cover"),
                "path": path,
                "row": row,
                "notes": cfg.get("notes"),
            }
        )

    return {
        "target_date": target_date.isoformat(),
        "sensor": cfg["label"],
        "collection": cfg["collection"],
        "scenes": scenes,
        "total": count,
        "returned": len(scenes),
        "notes": cfg.get("notes"),
    }


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
        # Effective search params so the frontend can persist and later
        # regenerate this exact tile (auditoría 2026-07-09, hallazgo 2).
        "days_buffer": days_buffer,
        "max_cloud": max_cloud,
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
        "days_buffer": days_buffer,
        "max_cloud": None,
    }


def build_available_dates_payload(
    explorer, *, year: int, month: int, sensor: str, max_cloud: int
) -> Dict[str, Any]:
    start_date = date(year, month, 1)
    end_date = date(year, month, __import__("calendar").monthrange(year, month)[1])
    end_date_exclusive = end_date + timedelta(days=1)

    normalized_sensor = sensor.lower()

    if normalized_sensor == "sentinel2":
        _, collection = explorer._sentinel2_collection(
            start_date,
            end_date_exclusive,
            max_cloud,
            use_toa=year < 2019,
        )
    elif normalized_sensor == "sentinel1":
        collection = explorer._sentinel1_collection(start_date, end_date_exclusive)
    elif normalized_sensor in LANDSAT_SENSORS:
        collection = explorer._landsat_collection(
            normalized_sensor, start_date, end_date_exclusive, max_cloud
        )
    else:
        return {
            "dates": [],
            "sensor": sensor,
            "year": year,
            "month": month,
            "total": 0,
            "error": f"Sensor no soportado: {sensor}",
        }

    dates_list = explorer._collection_dates(collection)
    return {
        "dates": dates_list if dates_list else [],
        "sensor": normalized_sensor,
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
