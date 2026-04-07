"""
Google Earth Engine Service — extracted into the geo domain.

Provides access to GEE assets and satellite imagery visualization.
Initialization is lazy: GEE is only initialized on first call, not on import.

Funcionalidades:
- Acceso a capas vectoriales (cuencas, caminos)
- Visualizacion de imagenes Sentinel-2 y Sentinel-1
- Explorador de imagenes satelitales
- Estadisticas de red vial por consorcio caminero
"""

import calendar
import ee
import json
import logging as _logging
import statistics as _statistics
from datetime import date, datetime as _datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings


# =========================================================================
# LAZY INITIALIZATION
# =========================================================================

_gee_initialized = False
_gee_init_error: str | None = None


def _ensure_initialized() -> None:
    """Lazy-init GEE on first call. Raises RuntimeError if init failed before."""
    global _gee_initialized, _gee_init_error

    if _gee_initialized:
        return

    if _gee_init_error:
        raise RuntimeError(f"GEE no disponible: {_gee_init_error}")

    try:
        # Option 1: key file on disk
        if settings.gee_key_file_path:
            key_path = Path(settings.gee_key_file_path)
            if key_path.exists():
                credentials = ee.ServiceAccountCredentials(
                    email=None,
                    key_file=str(key_path),
                )
                ee.Initialize(credentials, project=settings.gee_project_id)
                _gee_initialized = True
                return

        # Option 2: JSON string in env var
        if settings.gee_service_account_key:
            key_json = settings.gee_service_account_key
            key_data = json.loads(key_json)
            credentials = ee.ServiceAccountCredentials(
                email=key_data["client_email"],
                key_data=key_json,
            )
            ee.Initialize(credentials, project=settings.gee_project_id)
            _gee_initialized = True
            return

        # Option 3: default auth (local development)
        ee.Initialize(project=settings.gee_project_id)
        _gee_initialized = True

    except Exception as exc:
        _gee_init_error = str(exc)
        raise ValueError(
            "No se pudo inicializar GEE. "
            "Verifica credenciales o conectividad del servicio"
        ) from exc


def is_initialized() -> bool:
    """Check whether GEE has been successfully initialized."""
    return _gee_initialized


# =========================================================================
# GEE SERVICE — satellite imagery & tile generation
# =========================================================================


class GEEService:
    """
    Servicio para interactuar con Google Earth Engine.
    Proporciona acceso a assets y visualizacion de imagenes.
    """

    ASSETS_BASE = f"projects/{settings.gee_project_id}/assets"

    def __init__(self):
        _ensure_initialized()

        self.zona = ee.FeatureCollection(f"{self.ASSETS_BASE}/zona_cc_ampliada")
        self.caminos = ee.FeatureCollection(f"{self.ASSETS_BASE}/red_vial")

        try:
            self.canales = ee.FeatureCollection(f"{self.ASSETS_BASE}/canales")
        except Exception:
            self.canales = ee.FeatureCollection(ee.List([]))

        self.cuencas = {
            "candil": ee.FeatureCollection(f"{self.ASSETS_BASE}/candil"),
            "ml": ee.FeatureCollection(f"{self.ASSETS_BASE}/ml"),
            "noroeste": ee.FeatureCollection(f"{self.ASSETS_BASE}/noroeste"),
            "norte": ee.FeatureCollection(f"{self.ASSETS_BASE}/norte"),
        }

    def get_dem_download_url(
        self,
        geometry: ee.Geometry | None = None,
        scale: int = 30,
    ) -> Dict[str, Any]:
        """Get a download URL for the Copernicus GLO-30 DEM clipped to a geometry.

        Args:
            geometry: Optional ee.Geometry to clip. Defaults to self.zona.
            scale: Pixel resolution in meters (default 30).

        Returns:
            Dict with download_url, scale, and crs.
        """
        region = geometry or self.zona.geometry()
        dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
        clipped = dem.clip(region)

        url = clipped.getDownloadURL(
            {
                "format": "GEO_TIFF",
                "scale": scale,
                "region": region,
                "crs": "EPSG:4326",
            }
        )

        return {
            "download_url": url,
            "scale": scale,
            "crs": "EPSG:4326",
            "image": "COPERNICUS/DEM/GLO30",
        }

    def get_sentinel2_tiles(
        self,
        start_date: date,
        end_date: date,
        max_cloud: int = 40,
    ) -> Dict[str, Any]:
        """Obtener URL de tiles Sentinel-2 RGB para visualizacion."""
        sentinel2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(self.zona)
            .filterDate(start_date.isoformat(), end_date.isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
        )

        count = sentinel2.size().getInfo()
        if count == 0:
            return {
                "error": "No se encontraron imagenes Sentinel-2",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }

        mosaic = sentinel2.mosaic().clip(self.zona)
        vis_params = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}
        map_id = mosaic.getMapId(vis_params)

        return {
            "tile_url": map_id["tile_fetcher"].url_format,
            "imagenes_disponibles": count,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }


@lru_cache(maxsize=1)
def get_gee_service() -> GEEService:
    """Obtener instancia del servicio GEE (singleton)."""
    return GEEService()


# =========================================================================
# LAYER GEOJSON EXPORT
# =========================================================================


def get_layer_geojson(layer_name: str) -> Dict[str, Any]:
    """Obtener GeoJSON de una capa desde GEE assets."""
    _ensure_initialized()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    layer_mapping = {
        "zona": f"{assets_base}/zona_cc_ampliada",
        "candil": f"{assets_base}/candil",
        "ml": f"{assets_base}/ml",
        "noroeste": f"{assets_base}/noroeste",
        "norte": f"{assets_base}/norte",
        "caminos": f"{assets_base}/red_vial",
    }

    if layer_name not in layer_mapping:
        raise ValueError(
            f"Capa '{layer_name}' no encontrada. Disponibles: {list(layer_mapping.keys())}"
        )

    fc = ee.FeatureCollection(layer_mapping[layer_name])
    return fc.getInfo()


def get_available_layers() -> List[Dict[str, str]]:
    """Obtener lista de capas disponibles en GEE."""
    return [
        {
            "id": "zona",
            "nombre": "Zona Consorcio",
            "descripcion": "Limite del area del consorcio",
        },
        {
            "id": "candil",
            "nombre": "Cuenca Candil",
            "descripcion": "Cuenca hidrografica Candil",
        },
        {"id": "ml", "nombre": "Cuenca ML", "descripcion": "Cuenca hidrografica ML"},
        {
            "id": "noroeste",
            "nombre": "Cuenca Noroeste",
            "descripcion": "Cuenca hidrografica Noroeste",
        },
        {
            "id": "norte",
            "nombre": "Cuenca Norte",
            "descripcion": "Cuenca hidrografica Norte",
        },
        {
            "id": "caminos",
            "nombre": "Red Vial",
            "descripcion": "Red de caminos rurales",
        },
    ]


# =========================================================================
# RED VIAL POR CONSORCIO CAMINERO
# =========================================================================

CONSORCIO_COLORS = [
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#46f0f0",
    "#f032e6",
    "#bcf60c",
    "#fabebe",
    "#008080",
    "#e6beff",
    "#9a6324",
    "#fffac8",
    "#800000",
    "#aaffc3",
    "#808000",
    "#ffd8b1",
    "#000075",
    "#808080",
    "#000000",
]


def get_consorcios_camineros() -> List[Dict[str, Any]]:
    """Obtener lista de consorcios camineros unicos de la red vial."""
    _ensure_initialized()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")
    features = caminos.getInfo()["features"]

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
        lzn = props.get("lzn", 0)
        if lzn:
            try:
                consorcios_map[ccn]["longitud_total_km"] += float(lzn)
            except (ValueError, TypeError):
                pass

    consorcios = list(consorcios_map.values())
    consorcios.sort(key=lambda x: x["nombre"])
    return consorcios


def get_caminos_by_consorcio(consorcio_codigo: str) -> Dict[str, Any]:
    """Obtener caminos filtrados por consorcio caminero (codigo ccc)."""
    _ensure_initialized()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")
    filtered = caminos.filter(ee.Filter.eq("ccc", consorcio_codigo))
    geojson = filtered.getInfo()

    num_features = len(geojson.get("features", []))
    if num_features == 0:
        filtered = caminos.filter(ee.Filter.eq("ccc", consorcio_codigo.upper()))
        geojson = filtered.getInfo()

    return geojson


def get_caminos_by_consorcio_nombre(consorcio_nombre: str) -> Dict[str, Any]:
    """Obtener caminos filtrados por nombre de consorcio caminero (ccn)."""
    _ensure_initialized()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")
    filtered = caminos.filter(ee.Filter.eq("ccn", consorcio_nombre))
    return filtered.getInfo()


def get_caminos_con_colores() -> Dict[str, Any]:
    """Obtener red vial con colores asignados por consorcio caminero."""
    _ensure_initialized()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")
    features = caminos.getInfo()["features"]

    consorcios_unicos: List[str] = []
    for feature in features:
        ccn = feature.get("properties", {}).get("ccn", "Sin consorcio")
        if ccn not in consorcios_unicos:
            consorcios_unicos.append(ccn)

    consorcios_unicos.sort()

    color_map: Dict[str, str] = {}
    for i, ccn in enumerate(consorcios_unicos):
        color_map[ccn] = CONSORCIO_COLORS[i % len(CONSORCIO_COLORS)]

    stats_map: Dict[str, Dict[str, Any]] = {}
    for ccn in consorcios_unicos:
        ccc = ""
        for f in features:
            if f.get("properties", {}).get("ccn") == ccn:
                ccc = f.get("properties", {}).get("ccc", "")
                break
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
        lzn = props.get("lzn", 0)
        if lzn:
            try:
                stats_map[ccn]["longitud_km"] += float(lzn)
            except (ValueError, TypeError):
                pass

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


def get_estadisticas_consorcios() -> Dict[str, Any]:
    """Obtener estadisticas de kilometros por consorcio caminero."""
    _ensure_initialized()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")
    features = caminos.getInfo()["features"]

    stats: Dict[str, Dict[str, Any]] = {}

    for feature in features:
        props = feature.get("properties", {})
        ccn = props.get("ccn", "Sin consorcio")
        ccc = props.get("ccc", "N/A")

        if ccn not in stats:
            stats[ccn] = {
                "nombre": ccn,
                "codigo": ccc,
                "tramos": 0,
                "longitud_km": 0.0,
                "por_jerarquia": {},
                "por_superficie": {},
            }

        stats[ccn]["tramos"] += 1

        lzn = props.get("lzn", 0)
        if lzn:
            try:
                stats[ccn]["longitud_km"] += float(lzn)
            except (ValueError, TypeError):
                pass

        jerarquia = props.get("hct", "Desconocido")
        if jerarquia not in stats[ccn]["por_jerarquia"]:
            stats[ccn]["por_jerarquia"][jerarquia] = {"tramos": 0, "km": 0.0}
        stats[ccn]["por_jerarquia"][jerarquia]["tramos"] += 1
        if lzn:
            try:
                stats[ccn]["por_jerarquia"][jerarquia]["km"] += float(lzn)
            except (ValueError, TypeError):
                pass

        superficie = props.get("rst", "Desconocido")
        if superficie not in stats[ccn]["por_superficie"]:
            stats[ccn]["por_superficie"][superficie] = {"tramos": 0, "km": 0.0}
        stats[ccn]["por_superficie"][superficie]["tramos"] += 1
        if lzn:
            try:
                stats[ccn]["por_superficie"][superficie]["km"] += float(lzn)
            except (ValueError, TypeError):
                pass

    for ccn in stats:
        stats[ccn]["longitud_km"] = round(stats[ccn]["longitud_km"], 2)
        for j in stats[ccn]["por_jerarquia"]:
            stats[ccn]["por_jerarquia"][j]["km"] = round(
                stats[ccn]["por_jerarquia"][j]["km"], 2
            )
        for s in stats[ccn]["por_superficie"]:
            stats[ccn]["por_superficie"][s]["km"] = round(
                stats[ccn]["por_superficie"][s]["km"], 2
            )

    consorcios_lista = list(stats.values())
    consorcios_lista.sort(key=lambda x: -x["longitud_km"])

    total_tramos = sum(c["tramos"] for c in consorcios_lista)
    total_km = round(sum(c["longitud_km"] for c in consorcios_lista), 2)

    return {
        "consorcios": consorcios_lista,
        "totales": {
            "consorcios": len(consorcios_lista),
            "tramos": total_tramos,
            "longitud_km": total_km,
        },
    }


# =========================================================================
# IMAGE EXPLORER
# =========================================================================


class ImageExplorer:
    """
    Explorador de imagenes satelitales para la zona del consorcio.
    Permite visualizar Sentinel-2 (RGB, indices) y Sentinel-1 (SAR).
    """

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

    def __init__(self):
        _ensure_initialized()
        self.assets_base = f"projects/{settings.gee_project_id}/assets"
        self.zona = ee.FeatureCollection(f"{self.assets_base}/zona_cc_ampliada")

    def _mask_clouds_s2(self, image: ee.Image) -> ee.Image:
        scl = image.select("SCL")
        mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return image.updateMask(mask)

    def get_sentinel2_image(
        self,
        target_date: date,
        days_buffer: int = 10,
        max_cloud: int = 40,
        visualization: str = "rgb",
        use_median: bool = False,
    ) -> Dict[str, Any]:
        """Obtener tiles de imagen Sentinel-2 para una fecha especifica."""
        start_date = target_date - timedelta(days=days_buffer)
        end_date = target_date + timedelta(days=days_buffer)

        use_toa = target_date.year < 2019
        collection_name = (
            "COPERNICUS/S2_HARMONIZED" if use_toa else "COPERNICUS/S2_SR_HARMONIZED"
        )

        collection = (
            ee.ImageCollection(collection_name)
            .filterBounds(self.zona)
            .filterDate(start_date.isoformat(), end_date.isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
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

        dates_list = (
            collection.aggregate_array("system:time_start")
            .map(lambda d: ee.Date(d).format("YYYY-MM-dd"))
            .distinct()
            .getInfo()
        )

        if use_toa:
            composite = collection.mosaic().clip(self.zona)
        else:
            masked_collection = collection.map(self._mask_clouds_s2)
            if use_median:
                composite = masked_collection.median().clip(self.zona)
            else:
                composite = masked_collection.mosaic().clip(self.zona)

        preset = self.VIS_PRESETS.get(visualization, self.VIS_PRESETS["rgb"])

        if "index" in preset:
            if preset["index"] == "ndwi":
                image = composite.normalizedDifference(["B3", "B8"]).rename("index")
            elif preset["index"] == "mndwi":
                image = composite.normalizedDifference(["B3", "B11"]).rename("index")
            elif preset["index"] == "ndvi":
                image = composite.normalizedDifference(["B8", "B4"]).rename("index")
            elif preset["index"] == "flood":
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
            "dates_available": sorted(dates_list),
            "images_count": count,
            "visualization": visualization,
            "visualization_description": preset["description"],
            "sensor": "Sentinel-2",
            "collection": collection_name,
        }

    def get_sentinel1_image(
        self,
        target_date: date,
        days_buffer: int = 10,
        visualization: str = "vv",
    ) -> Dict[str, Any]:
        """Obtener tiles de imagen Sentinel-1 (SAR) para una fecha especifica."""
        start_date = target_date - timedelta(days=days_buffer)
        end_date = target_date + timedelta(days=days_buffer)

        collection = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(self.zona)
            .filterDate(start_date.isoformat(), end_date.isoformat())
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        )

        count = collection.size().getInfo()
        if count == 0:
            return {
                "error": "No se encontraron imagenes SAR para la fecha seleccionada",
                "target_date": target_date.isoformat(),
                "days_buffer": days_buffer,
            }

        dates_list = (
            collection.aggregate_array("system:time_start")
            .map(lambda d: ee.Date(d).format("YYYY-MM-dd"))
            .distinct()
            .getInfo()
        )

        mosaic = collection.select("VV").mosaic().clip(self.zona)

        vis_params: Dict[str, Any]
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
            "dates_available": sorted(dates_list),
            "images_count": count,
            "visualization": visualization,
            "visualization_description": description,
            "sensor": "Sentinel-1",
            "collection": "COPERNICUS/S1_GRD",
        }

    def get_available_dates(
        self,
        year: int,
        month: int,
        sensor: str = "sentinel2",
        max_cloud: int = 60,
    ) -> Dict[str, Any]:
        """Get list of dates with available imagery for a given month.

        This is a lightweight query — only retrieves dates, not full images.
        """
        start_date = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = date(year, month, last_day)
        # GEE filterDate is exclusive on end, so add one day
        end_date_exclusive = end_date + timedelta(days=1)

        if sensor == "sentinel2":
            use_toa = year < 2019
            collection_name = (
                "COPERNICUS/S2_HARMONIZED" if use_toa else "COPERNICUS/S2_SR_HARMONIZED"
            )
            collection = (
                ee.ImageCollection(collection_name)
                .filterBounds(self.zona)
                .filterDate(start_date.isoformat(), end_date_exclusive.isoformat())
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
            )
        else:
            collection = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(self.zona)
                .filterDate(start_date.isoformat(), end_date_exclusive.isoformat())
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            )

        dates_list = (
            collection.aggregate_array("system:time_start")
            .map(lambda d: ee.Date(d).format("YYYY-MM-dd"))
            .distinct()
            .sort()
            .getInfo()
        )

        return {
            "dates": sorted(dates_list) if dates_list else [],
            "sensor": sensor,
            "year": year,
            "month": month,
            "total": len(dates_list) if dates_list else 0,
        }

    def get_flood_comparison(
        self,
        flood_date: date,
        normal_date: date,
        days_buffer: int = 10,
        max_cloud: int = 40,
    ) -> Dict[str, Any]:
        """Comparar imagen de inundacion con imagen normal."""
        flood_result = self.get_sentinel2_image(
            flood_date, days_buffer, max_cloud, "inundacion"
        )
        normal_result = self.get_sentinel2_image(
            normal_date, days_buffer, max_cloud, "rgb"
        )
        flood_rgb = self.get_sentinel2_image(flood_date, days_buffer, max_cloud, "rgb")

        return {
            "flood_date": flood_date.isoformat(),
            "normal_date": normal_date.isoformat(),
            "flood_detection": flood_result,
            "flood_rgb": flood_rgb,
            "normal_rgb": normal_result,
        }

    def get_sar_time_series(
        self,
        start_date: date,
        end_date: date,
        scale: int = 100,
    ) -> Dict[str, Any]:
        """Compute mean VV backscatter time series over the zona geometry.

        Filters Sentinel-1 GRD IW VV collection by date range,
        then for each image computes the zonal mean VV via reduceRegion.

        Returns:
            Dict with dates, vv_mean, image_count, scale_m.
        """
        collection = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(self.zona)
            .filterDate(start_date.isoformat(), end_date.isoformat())
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
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

        def _extract_vv_mean(image: ee.Image) -> ee.Feature:
            """Map function: compute mean VV over zona for a single image."""
            img_date = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd")
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=self.zona.geometry(),
                scale=scale,
                bestEffort=True,
            )
            return ee.Feature(
                None,
                {"date": img_date, "vv_mean": stats.get("VV")},
            )

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

    def get_available_visualizations(self) -> List[Dict[str, str]]:
        """Obtener lista de visualizaciones disponibles."""
        return [
            {"id": k, "description": v["description"]}
            for k, v in self.VIS_PRESETS.items()
        ]


@lru_cache(maxsize=1)
def get_image_explorer() -> ImageExplorer:
    """Obtener instancia del explorador de imagenes (singleton)."""
    return ImageExplorer()


# =========================================================================
# NDWI BASELINE — dry-season historical reference per zona
# =========================================================================


_baseline_logger = _logging.getLogger(__name__)


def compute_ndwi_baselines_gee(
    zones: list[dict],
    dry_season_months: list[int] | None = None,
    years_back: int = 3,
) -> list[dict]:
    """Compute NDWI mean and std per zona using S2 dry-season historical data.

    For each zone, queries COPERNICUS/S2_SR_HARMONIZED filtered to the given
    dry-season months over the last ``years_back`` years, computes per-image
    mean NDWI, then returns mean and std across images.

    Args:
        zones: List of dicts with 'id', 'nombre', 'ee_geometry' keys.
        dry_season_months: Month numbers (1-12). Default [6, 7, 8] (austral winter).
        years_back: How many years of history to use (default 3).

    Returns:
        List of dicts: {zona_id, ndwi_mean, ndwi_std, sample_count}.
        Zones that fail GEE queries are silently skipped (logged as warnings).
    """
    _ensure_initialized()

    if dry_season_months is None:
        dry_season_months = [6, 7, 8]

    now = _datetime.utcnow()
    start_dt = now.replace(year=now.year - years_back)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = now.strftime("%Y-%m-%d")

    # Build month filter (OR across selected months)
    month_filters = [ee.Filter.calendarRange(m, m, "month") for m in dry_season_months]
    month_filter = (
        ee.Filter.Or(*month_filters) if len(month_filters) > 1 else month_filters[0]
    )

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start_str, end_str)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .filter(month_filter)
        .map(lambda img: img.normalizedDifference(["B3", "B8"]).rename("ndwi"))
    )

    results = []

    for zone in zones:
        try:
            geometry = zone["ee_geometry"]

            def _get_mean(img: ee.Image) -> ee.Feature:
                val = img.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geometry,
                    scale=10,
                    maxPixels=1e9,
                ).get("ndwi")
                return ee.Feature(None, {"ndwi": val})

            ndwi_values = (
                collection.map(_get_mean)
                .filter(ee.Filter.notNull(["ndwi"]))
                .aggregate_array("ndwi")
                .getInfo()
            )

            if not ndwi_values:
                _baseline_logger.warning(
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
                    "ndwi_std": round(
                        max(std_val, 0.001), 4
                    ),  # floor std to avoid div/0
                    "sample_count": len(ndwi_values),
                }
            )

        except Exception as exc:
            _baseline_logger.warning(
                "compute_ndwi_baselines: failed for zone %s: %s", zone.get("id"), exc
            )

    return results


# =========================================================================
# LAND COVER C COEFFICIENT — ESA WorldCover → runoff coefficient
# =========================================================================


def get_landcover_c_coefficient(zone_geometry: ee.Geometry) -> float | None:
    """Get runoff coefficient C from ESA WorldCover v200 for a zone.

    Uses area-weighted mean of per-pixel C values derived from the 10m
    ESA/WorldCover/v200 land cover classification.

    C coefficient mapping for rural Argentine NE (Mesopotamia/Chaco):
        10  Trees/Forest        → 0.20
        20  Shrubland           → 0.35
        30  Grassland           → 0.40
        40  Cropland            → 0.55
        50  Built-up            → 0.75
        60  Bare/Sparse         → 0.65
        70  Snow/Ice            → 0.10
        80  Open Water          → 0.05
        90  Herbaceous Wetland  → 0.15
        95  Mangroves           → 0.20
       100  Moss/Lichen         → 0.30

    Args:
        zone_geometry: ee.Geometry for the zone of interest.

    Returns:
        Float C value in [0, 1], or None if the GEE call fails.
    """
    _ensure_initialized()

    try:
        # C values × 100 to work with integer remap (avoids float precision issues)
        class_values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]
        c_x100 = [20, 35, 40, 55, 75, 65, 10, 5, 15, 20, 30]

        lc_image = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
        c_band = lc_image.remap(class_values, c_x100, defaultValue=40).rename("c_x100")

        result = (
            c_band.reduceRegion(
                reducer=ee.Reducer.mean(),
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
        _baseline_logger.warning("get_landcover_c_coefficient failed: %s", exc)
        return None
