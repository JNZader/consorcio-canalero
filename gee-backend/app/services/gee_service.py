"""
Google Earth Engine Service.
Provides access to GEE assets and satellite imagery visualization.

Funcionalidades:
- Acceso a capas vectoriales (cuencas, caminos)
- Visualizacion de imagenes Sentinel-2
- Explorador de imagenes satelitales
"""

import ee
import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional, Dict, Any, List
from pathlib import Path

from app.config import settings


# Global flag to track initialization
_gee_initialized = False


def initialize_gee() -> None:
    """
    Inicializar Google Earth Engine con Service Account.

    Requiere:
    1. Service Account de Google Cloud con acceso a GEE
    2. JSON key del service account
    3. Service account registrado en GEE
    """
    global _gee_initialized

    if _gee_initialized:
        return

    # Opcion 1: Archivo de credenciales (key_file parameter)
    if settings.gee_key_file_path:
        key_path = Path(settings.gee_key_file_path)
        if key_path.exists():
            # Usar key_file en lugar de key_data para archivos JSON
            credentials = ee.ServiceAccountCredentials(
                email=None,  # Se extrae automaticamente del archivo
                key_file=str(key_path),
            )
            ee.Initialize(credentials, project=settings.gee_project_id)
            _gee_initialized = True
            return

    # Opcion 2: Variable de entorno con JSON string
    if settings.gee_service_account_key:
        # key_data espera el JSON como string, no como dict
        key_json = settings.gee_service_account_key
        key_data = json.loads(key_json)
        credentials = ee.ServiceAccountCredentials(
            email=key_data["client_email"],
            key_data=key_json,  # Pasar el string original, no el dict
        )
        ee.Initialize(credentials, project=settings.gee_project_id)
        _gee_initialized = True
        return

    # Opcion 3: Autenticacion por defecto (para desarrollo local)
    try:
        ee.Initialize(project=settings.gee_project_id)
        _gee_initialized = True
        return
    except Exception:
        pass

    raise ValueError(
        "No se encontraron credenciales de GEE. "
        "Configura GEE_KEY_FILE_PATH o GEE_SERVICE_ACCOUNT_KEY"
    )


class GEEService:
    """
    Servicio para interactuar con Google Earth Engine.
    Proporciona acceso a assets y visualizacion de imagenes.
    """

    # Assets paths en GEE
    ASSETS_BASE = f"projects/{settings.gee_project_id}/assets"

    def __init__(self):
        """Inicializar servicio y cargar assets."""
        if not _gee_initialized:
            initialize_gee()

        # Cargar assets vectoriales
        self.zona = ee.FeatureCollection(f"{self.ASSETS_BASE}/zona_cc_ampliada")
        self.caminos = ee.FeatureCollection(f"{self.ASSETS_BASE}/red_vial")

        # Capa de canales (se asume asset llamado 'canales')
        try:
            self.canales = ee.FeatureCollection(f"{self.ASSETS_BASE}/canales")
        except Exception:
            # Fallback a una coleccion vacia si aun no existe el asset
            self.canales = ee.FeatureCollection(ee.List([]))

        # Cuencas
        self.cuencas = {
            "candil": ee.FeatureCollection(f"{self.ASSETS_BASE}/candil"),
            "ml": ee.FeatureCollection(f"{self.ASSETS_BASE}/ml"),
            "noroeste": ee.FeatureCollection(f"{self.ASSETS_BASE}/noroeste"),
            "norte": ee.FeatureCollection(f"{self.ASSETS_BASE}/norte"),
        }

    def get_sentinel2_tiles(
        self,
        start_date: date,
        end_date: date,
        max_cloud: int = 40,
    ) -> Dict[str, Any]:
        """
        Obtener URL de tiles Sentinel-2 RGB para visualizacion.

        Returns:
            Dict con URL de tiles y metadata
        """
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
# FUNCIONES PARA EXPORTAR CAPAS COMO GEOJSON
# =========================================================================

def get_layer_geojson(layer_name: str) -> Dict[str, Any]:
    """
    Obtener GeoJSON de una capa desde GEE assets.

    Args:
        layer_name: Nombre de la capa (zona, candil, ml, noroeste, norte, caminos)

    Returns:
        GeoJSON FeatureCollection
    """
    if not _gee_initialized:
        initialize_gee()

    assets_base = f"projects/{settings.gee_project_id}/assets"

    # Mapeo de nombres a assets
    layer_mapping = {
        "zona": f"{assets_base}/zona_cc_ampliada",
        "candil": f"{assets_base}/candil",
        "ml": f"{assets_base}/ml",
        "noroeste": f"{assets_base}/noroeste",
        "norte": f"{assets_base}/norte",
        "caminos": f"{assets_base}/red_vial",
    }

    if layer_name not in layer_mapping:
        raise ValueError(f"Capa '{layer_name}' no encontrada. Disponibles: {list(layer_mapping.keys())}")

    asset_path = layer_mapping[layer_name]

    # Cargar FeatureCollection desde GEE
    fc = ee.FeatureCollection(asset_path)

    # Convertir a GeoJSON
    geojson = fc.getInfo()

    return geojson


def get_available_layers() -> List[Dict[str, str]]:
    """
    Obtener lista de capas disponibles en GEE.

    Returns:
        Lista de capas con nombre y descripcion
    """
    return [
        {"id": "zona", "nombre": "Zona Consorcio", "descripcion": "Limite del area del consorcio"},
        {"id": "candil", "nombre": "Cuenca Candil", "descripcion": "Cuenca hidrografica Candil"},
        {"id": "ml", "nombre": "Cuenca ML", "descripcion": "Cuenca hidrografica ML"},
        {"id": "noroeste", "nombre": "Cuenca Noroeste", "descripcion": "Cuenca hidrografica Noroeste"},
        {"id": "norte", "nombre": "Cuenca Norte", "descripcion": "Cuenca hidrografica Norte"},
        {"id": "caminos", "nombre": "Red Vial", "descripcion": "Red de caminos rurales"},
    ]


# =========================================================================
# FUNCIONES PARA RED VIAL POR CONSORCIO CAMINERO
# =========================================================================

def get_consorcios_camineros() -> List[Dict[str, Any]]:
    """
    Obtener lista de consorcios camineros unicos de la red vial.

    Returns:
        Lista de consorcios con codigo (ccc), nombre (ccn) y cantidad de tramos
    """
    if not _gee_initialized:
        initialize_gee()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")

    # Obtener valores unicos de ccn (nombre consorcio) y ccc (codigo)
    # Usamos aggregate_array para obtener todos los valores y luego procesamos
    features = caminos.getInfo()["features"]

    # Agrupar por consorcio
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
        # Sumar longitud si existe (lzn = longitud en km)
        lzn = props.get("lzn", 0)
        if lzn:
            try:
                consorcios_map[ccn]["longitud_total_km"] += float(lzn)
            except (ValueError, TypeError):
                pass

    # Convertir a lista y ordenar por nombre
    consorcios = list(consorcios_map.values())
    consorcios.sort(key=lambda x: x["nombre"])

    return consorcios


def get_caminos_by_consorcio(consorcio_codigo: str) -> Dict[str, Any]:
    """
    Obtener caminos filtrados por consorcio caminero.

    Args:
        consorcio_codigo: Codigo del consorcio (ccc) ej: "CC269"

    Returns:
        GeoJSON FeatureCollection con los caminos del consorcio
    """
    if not _gee_initialized:
        initialize_gee()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")

    # Filtrar por codigo de consorcio (ccc)
    # El codigo viene como "CC269", pero en el asset puede estar diferente
    filtered = caminos.filter(ee.Filter.eq("ccc", consorcio_codigo))

    # Convertir a GeoJSON
    geojson = filtered.getInfo()

    # Agregar metadata
    num_features = len(geojson.get("features", []))
    if num_features == 0:
        # Intentar busqueda case-insensitive
        filtered = caminos.filter(
            ee.Filter.eq("ccc", consorcio_codigo.upper())
        )
        geojson = filtered.getInfo()
        num_features = len(geojson.get("features", []))

    return geojson


def get_caminos_by_consorcio_nombre(consorcio_nombre: str) -> Dict[str, Any]:
    """
    Obtener caminos filtrados por nombre de consorcio caminero.

    Args:
        consorcio_nombre: Nombre del consorcio (ccn) ej: "C.C. 269 - SAN MARCOS SUD"

    Returns:
        GeoJSON FeatureCollection con los caminos del consorcio
    """
    if not _gee_initialized:
        initialize_gee()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")

    # Filtrar por nombre de consorcio (ccn)
    filtered = caminos.filter(ee.Filter.eq("ccn", consorcio_nombre))

    # Convertir a GeoJSON
    geojson = filtered.getInfo()

    return geojson


# Paleta de colores para consorcios camineros (colores distinguibles)
CONSORCIO_COLORS = [
    "#e6194b",  # rojo
    "#3cb44b",  # verde
    "#4363d8",  # azul
    "#f58231",  # naranja
    "#911eb4",  # purpura
    "#46f0f0",  # cyan
    "#f032e6",  # magenta
    "#bcf60c",  # lima
    "#fabebe",  # rosa
    "#008080",  # teal
    "#e6beff",  # lavanda
    "#9a6324",  # marron
    "#fffac8",  # beige
    "#800000",  # granate
    "#aaffc3",  # menta
    "#808000",  # oliva
    "#ffd8b1",  # melocoton
    "#000075",  # azul marino
    "#808080",  # gris
    "#000000",  # negro
]


def get_caminos_con_colores() -> Dict[str, Any]:
    """
    Obtener red vial con colores asignados por consorcio caminero.

    Cada feature incluye una propiedad 'color' basada en su consorcio.

    Returns:
        Dict con:
        - geojson: FeatureCollection con propiedad 'color' en cada feature
        - consorcios: Lista de consorcios con su color asignado y estadisticas
    """
    if not _gee_initialized:
        initialize_gee()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")

    # Obtener todos los features
    features = caminos.getInfo()["features"]

    # Obtener lista unica de consorcios y asignar colores
    consorcios_unicos: List[str] = []
    for feature in features:
        ccn = feature.get("properties", {}).get("ccn", "Sin consorcio")
        if ccn not in consorcios_unicos:
            consorcios_unicos.append(ccn)

    # Ordenar para consistencia
    consorcios_unicos.sort()

    # Crear mapa de consorcio -> color
    color_map: Dict[str, str] = {}
    for i, ccn in enumerate(consorcios_unicos):
        color_map[ccn] = CONSORCIO_COLORS[i % len(CONSORCIO_COLORS)]

    # Estadisticas por consorcio
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

    # Agregar color a cada feature y calcular estadisticas
    for feature in features:
        props = feature.get("properties", {})
        ccn = props.get("ccn", "Sin consorcio")

        # Agregar color al feature
        feature["properties"]["color"] = color_map.get(ccn, "#888888")

        # Actualizar estadisticas
        stats_map[ccn]["tramos"] += 1
        lzn = props.get("lzn", 0)
        if lzn:
            try:
                stats_map[ccn]["longitud_km"] += float(lzn)
            except (ValueError, TypeError):
                pass

    # Redondear longitudes
    for ccn in stats_map:
        stats_map[ccn]["longitud_km"] = round(stats_map[ccn]["longitud_km"], 2)

    # Convertir stats a lista ordenada por nombre
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
    """
    Obtener estadisticas de kilometros por consorcio caminero.

    Returns:
        Dict con estadisticas por consorcio y totales
    """
    if not _gee_initialized:
        initialize_gee()

    assets_base = f"projects/{settings.gee_project_id}/assets"
    caminos = ee.FeatureCollection(f"{assets_base}/red_vial")

    features = caminos.getInfo()["features"]

    # Agrupar por consorcio
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

        # Longitud
        lzn = props.get("lzn", 0)
        if lzn:
            try:
                stats[ccn]["longitud_km"] += float(lzn)
            except (ValueError, TypeError):
                pass

        # Por jerarquia (hct)
        jerarquia = props.get("hct", "Desconocido")
        if jerarquia not in stats[ccn]["por_jerarquia"]:
            stats[ccn]["por_jerarquia"][jerarquia] = {"tramos": 0, "km": 0.0}
        stats[ccn]["por_jerarquia"][jerarquia]["tramos"] += 1
        if lzn:
            try:
                stats[ccn]["por_jerarquia"][jerarquia]["km"] += float(lzn)
            except (ValueError, TypeError):
                pass

        # Por tipo de superficie (rst)
        superficie = props.get("rst", "Desconocido")
        if superficie not in stats[ccn]["por_superficie"]:
            stats[ccn]["por_superficie"][superficie] = {"tramos": 0, "km": 0.0}
        stats[ccn]["por_superficie"][superficie]["tramos"] += 1
        if lzn:
            try:
                stats[ccn]["por_superficie"][superficie]["km"] += float(lzn)
            except (ValueError, TypeError):
                pass

    # Redondear y ordenar
    for ccn in stats:
        stats[ccn]["longitud_km"] = round(stats[ccn]["longitud_km"], 2)
        for j in stats[ccn]["por_jerarquia"]:
            stats[ccn]["por_jerarquia"][j]["km"] = round(stats[ccn]["por_jerarquia"][j]["km"], 2)
        for s in stats[ccn]["por_superficie"]:
            stats[ccn]["por_superficie"][s]["km"] = round(stats[ccn]["por_superficie"][s]["km"], 2)

    consorcios_lista = list(stats.values())
    consorcios_lista.sort(key=lambda x: -x["longitud_km"])  # Ordenar por km desc

    # Calcular totales
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
# EXPLORADOR DE IMAGENES SATELITALES
# Permite ver imagenes de fechas especificas con diferentes visualizaciones
# =========================================================================

class ImageExplorer:
    """
    Explorador de imagenes satelitales para la zona del consorcio.
    Permite visualizar Sentinel-2 (RGB, indices) y Sentinel-1 (SAR).
    """

    # Presets de visualizacion para Sentinel-2
    VIS_PRESETS = {
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
        """Inicializar explorador."""
        if not _gee_initialized:
            initialize_gee()

        self.assets_base = f"projects/{settings.gee_project_id}/assets"
        self.zona = ee.FeatureCollection(f"{self.assets_base}/zona_cc_ampliada")

    def _mask_clouds_s2(self, image: ee.Image) -> ee.Image:
        """Aplicar mascara de nubes a imagen Sentinel-2."""
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
        """
        Obtener tiles de imagen Sentinel-2 para una fecha especifica.

        Args:
            target_date: Fecha objetivo
            days_buffer: Dias antes/despues para buscar imagenes
            max_cloud: Porcentaje maximo de nubes
            visualization: Tipo de visualizacion (rgb, falso_color, ndwi, etc.)
            use_median: Usar mediana en lugar de mosaico (mejor cobertura)

        Returns:
            Dict con tile_url y metadata
        """
        start_date = target_date - timedelta(days=days_buffer)
        end_date = target_date + timedelta(days=days_buffer)

        # Para fechas anteriores a 2019, usar S2_HARMONIZED (TOA)
        use_toa = target_date.year < 2019
        collection_name = "COPERNICUS/S2_HARMONIZED" if use_toa else "COPERNICUS/S2_SR_HARMONIZED"

        # Filtrar coleccion
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

        # Obtener fechas disponibles
        dates_list = collection.aggregate_array("system:time_start").map(
            lambda d: ee.Date(d).format("YYYY-MM-dd")
        ).distinct().getInfo()

        # Crear composicion
        if use_toa:
            composite = collection.mosaic().clip(self.zona)
        else:
            masked_collection = collection.map(self._mask_clouds_s2)
            if use_median:
                composite = masked_collection.median().clip(self.zona)
            else:
                composite = masked_collection.mosaic().clip(self.zona)

        # Obtener preset de visualizacion
        preset = self.VIS_PRESETS.get(visualization, self.VIS_PRESETS["rgb"])

        # Generar imagen segun el tipo
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

            vis_params = {
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

        # Generar tiles
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
        """
        Obtener tiles de imagen Sentinel-1 (SAR) para una fecha especifica.

        Args:
            target_date: Fecha objetivo
            days_buffer: Dias antes/despues para buscar imagenes
            visualization: vv, vh, vv_flood (deteccion de agua)

        Returns:
            Dict con tile_url y metadata
        """
        start_date = target_date - timedelta(days=days_buffer)
        end_date = target_date + timedelta(days=days_buffer)

        # Filtrar coleccion
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

        # Obtener fechas disponibles
        dates_list = collection.aggregate_array("system:time_start").map(
            lambda d: ee.Date(d).format("YYYY-MM-dd")
        ).distinct().getInfo()

        # Crear mosaico
        mosaic = collection.select("VV").mosaic().clip(self.zona)

        # Visualizacion
        if visualization == "vv_flood":
            # Deteccion de agua: valores < -15 dB
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

    def get_flood_comparison(
        self,
        flood_date: date,
        normal_date: date,
        days_buffer: int = 10,
        max_cloud: int = 40,
    ) -> Dict[str, Any]:
        """
        Comparar imagen de inundacion con imagen normal.

        Args:
            flood_date: Fecha de inundacion
            normal_date: Fecha de referencia (sin inundacion)
            days_buffer: Dias de buffer
            max_cloud: Max nubes

        Returns:
            Dict con tiles de ambas fechas y comparacion
        """
        flood_result = self.get_sentinel2_image(
            flood_date, days_buffer, max_cloud, "inundacion"
        )
        normal_result = self.get_sentinel2_image(
            normal_date, days_buffer, max_cloud, "rgb"
        )

        # Tambien obtener RGB de inundacion
        flood_rgb = self.get_sentinel2_image(
            flood_date, days_buffer, max_cloud, "rgb"
        )

        return {
            "flood_date": flood_date.isoformat(),
            "normal_date": normal_date.isoformat(),
            "flood_detection": flood_result,
            "flood_rgb": flood_rgb,
            "normal_rgb": normal_result,
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
