"""Google Earth Engine service entrypoints and compatibility wrappers."""

import ee
import json
import logging as _logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
from app.domains.geo.gee_service_layers_support import (
    CONSORCIO_COLORS,
    ensure_consorcio_bucket,
    fetch_caminos_by_consorcio,
    fetch_caminos_by_consorcio_nombre,
    fetch_layer_geojson,
    fetch_red_vial_features,
    get_available_layers_payload,
    update_breakdown,
)
from app.domains.geo.gee_service_support import (
    VIS_PRESETS,
    available_visualizations_payload,
    build_available_dates_payload,
    build_dem_download_payload,
    build_flood_comparison_payload,
    build_colored_roads,
    build_consorcio_stats,
    build_consorcios_camineros,
    build_sar_time_series_payload,
    build_sentinel1_collection,
    build_sentinel1_payload,
    build_sentinel2_collection,
    build_sentinel2_payload,
    build_sentinel2_tiles_payload,
    collection_dates,
    compute_ndwi_baselines_payload,
    get_landcover_c_payload,
    mask_clouds_s2,
)


_gee_initialized = False
_gee_init_error: str | None = None


def _assets_base() -> str:
    """Build the Earth Engine asset prefix from current settings."""
    return f"projects/{settings.gee_project_id}/assets"


def _asset_path(asset_name: str) -> str:
    """Build a fully qualified Earth Engine asset path."""
    return f"{_assets_base()}/{asset_name}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a numeric-ish value to float, returning default on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _distinct_collection_dates(collection) -> list[str]:
    """Extract distinct YYYY-MM-dd strings from an EE image collection."""
    return (
        collection.aggregate_array("system:time_start")
        .map(lambda d: ee.Date(d).format("YYYY-MM-dd"))
        .distinct()
        .getInfo()
    )


def _empty_feature_collection() -> Any:
    """Return an empty EE FeatureCollection fallback."""
    return ee.FeatureCollection(ee.List([]))


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


class GEEService:
    """Servicio principal para interactuar con GEE."""

    ASSETS_BASE = _assets_base()

    def __init__(self):
        _ensure_initialized()

        self.zona = ee.FeatureCollection(f"{self.ASSETS_BASE}/zona_cc_ampliada")
        self.caminos = ee.FeatureCollection(f"{self.ASSETS_BASE}/red_vial")

        try:
            self.canales = ee.FeatureCollection(f"{self.ASSETS_BASE}/canales")
        except Exception:
            self.canales = _empty_feature_collection()

        self.cuencas = {
            "candil": ee.FeatureCollection(f"{self.ASSETS_BASE}/candil"),
            "ml": ee.FeatureCollection(f"{self.ASSETS_BASE}/ml"),
            "noroeste": ee.FeatureCollection(f"{self.ASSETS_BASE}/noroeste"),
            "norte": ee.FeatureCollection(f"{self.ASSETS_BASE}/norte"),
        }

    def _sentinel2_collection(
        self,
        start_date: date,
        end_date: date,
        max_cloud: int,
        *,
        use_toa: bool,
    ):
        return build_sentinel2_collection(
            ee, self.zona, start_date, end_date, max_cloud, use_toa=use_toa
        )

    def _sentinel1_collection(self, start_date: date, end_date: date):
        return build_sentinel1_collection(ee, self.zona, start_date, end_date)

    def get_dem_download_url(
        self,
        geometry: ee.Geometry | None = None,
        scale: int = 30,
    ) -> Dict[str, Any]:
        return build_dem_download_payload(ee, self.zona, geometry=geometry, scale=scale)

    def get_sentinel2_tiles(
        self,
        start_date: date,
        end_date: date,
        max_cloud: int = 40,
    ) -> Dict[str, Any]:
        return build_sentinel2_tiles_payload(
            ee,
            self.zona,
            start_date=start_date,
            end_date=end_date,
            max_cloud=max_cloud,
        )


@lru_cache(maxsize=1)
def get_gee_service() -> GEEService:
    return GEEService()


def get_layer_geojson(layer_name: str) -> Dict[str, Any]:
    return fetch_layer_geojson(
        layer_name,
        ensure_initialized=_ensure_initialized,
        asset_path=_asset_path,
        ee_module=ee,
    )


def get_available_layers() -> List[Dict[str, str]]:
    return get_available_layers_payload()


def _get_red_vial_features() -> list[dict[str, Any]]:
    return fetch_red_vial_features(
        ensure_initialized=_ensure_initialized,
        asset_path=_asset_path,
        ee_module=ee,
    )


def _ensure_consorcio_bucket(
    stats_map: Dict[str, Dict[str, Any]],
    *,
    nombre: str,
    codigo: str,
) -> Dict[str, Any]:
    return ensure_consorcio_bucket(stats_map, nombre=nombre, codigo=codigo)


def _update_breakdown(
    breakdown: Dict[str, Dict[str, float | int]],
    key: str,
    length_km: float,
) -> None:
    update_breakdown(breakdown, key, length_km)


def get_consorcios_camineros() -> List[Dict[str, Any]]:
    features = _get_red_vial_features()
    return build_consorcios_camineros(features, _safe_float)


def get_caminos_by_consorcio(consorcio_codigo: str) -> Dict[str, Any]:
    return fetch_caminos_by_consorcio(
        consorcio_codigo,
        ensure_initialized=_ensure_initialized,
        asset_path=_asset_path,
        ee_module=ee,
    )


def get_caminos_by_consorcio_nombre(consorcio_nombre: str) -> Dict[str, Any]:
    return fetch_caminos_by_consorcio_nombre(
        consorcio_nombre,
        ensure_initialized=_ensure_initialized,
        asset_path=_asset_path,
        ee_module=ee,
    )


def get_caminos_con_colores() -> Dict[str, Any]:
    features = _get_red_vial_features()
    return build_colored_roads(
        features,
        colors=CONSORCIO_COLORS,
        safe_float=_safe_float,
    )


def get_estadisticas_consorcios() -> Dict[str, Any]:
    features = _get_red_vial_features()
    return build_consorcio_stats(
        features,
        ensure_bucket=_ensure_consorcio_bucket,
        update_breakdown=_update_breakdown,
        safe_float=_safe_float,
    )


class ImageExplorer:
    """Explorador de imágenes satelitales."""

    VIS_PRESETS = VIS_PRESETS

    def __init__(self):
        _ensure_initialized()
        self.assets_base = _assets_base()
        self.zona = ee.FeatureCollection(f"{self.assets_base}/zona_cc_ampliada")

    def _mask_clouds_s2(self, image: ee.Image) -> ee.Image:
        return mask_clouds_s2(image)

    def _collection_dates(self, collection) -> list[str]:
        return collection_dates(collection, _distinct_collection_dates)

    def _sentinel2_collection(
        self,
        start_date: date,
        end_date: date,
        max_cloud: int,
        *,
        use_toa: bool,
    ):
        return build_sentinel2_collection(
            ee, self.zona, start_date, end_date, max_cloud, use_toa=use_toa
        )

    def _sentinel1_collection(self, start_date: date, end_date: date):
        return build_sentinel1_collection(ee, self.zona, start_date, end_date)

    def get_sentinel2_image(
        self,
        target_date: date,
        days_buffer: int = 10,
        max_cloud: int = 40,
        visualization: str = "rgb",
        use_median: bool = False,
    ) -> Dict[str, Any]:
        return build_sentinel2_payload(
            self,
            target_date=target_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
            visualization=visualization,
            use_median=use_median,
        )

    def get_sentinel1_image(
        self,
        target_date: date,
        days_buffer: int = 10,
        visualization: str = "vv",
    ) -> Dict[str, Any]:
        return build_sentinel1_payload(
            self,
            target_date=target_date,
            days_buffer=days_buffer,
            visualization=visualization,
        )

    def get_available_dates(
        self,
        year: int,
        month: int,
        sensor: str = "sentinel2",
        max_cloud: int = 60,
    ) -> Dict[str, Any]:
        return build_available_dates_payload(
            self,
            year=year,
            month=month,
            sensor=sensor,
            max_cloud=max_cloud,
        )

    def get_flood_comparison(
        self,
        flood_date: date,
        normal_date: date,
        days_buffer: int = 10,
        max_cloud: int = 40,
    ) -> Dict[str, Any]:
        return build_flood_comparison_payload(
            self,
            flood_date=flood_date,
            normal_date=normal_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
        )

    def get_sar_time_series(
        self,
        start_date: date,
        end_date: date,
        scale: int = 100,
    ) -> Dict[str, Any]:
        return build_sar_time_series_payload(
            self,
            ee,
            start_date=start_date,
            end_date=end_date,
            scale=scale,
        )

    def get_available_visualizations(self) -> List[Dict[str, str]]:
        return available_visualizations_payload(self.VIS_PRESETS)


@lru_cache(maxsize=1)
def get_image_explorer() -> ImageExplorer:
    return ImageExplorer()


_baseline_logger = _logging.getLogger(__name__)


def compute_ndwi_baselines_gee(
    zones: list[dict],
    dry_season_months: list[int] | None = None,
    years_back: int = 3,
) -> list[dict]:
    _ensure_initialized()

    if dry_season_months is None:
        dry_season_months = [6, 7, 8]
    return compute_ndwi_baselines_payload(
        ee,
        _baseline_logger,
        zones=zones,
        dry_season_months=dry_season_months,
        years_back=years_back,
    )


def get_landcover_c_coefficient(zone_geometry: ee.Geometry) -> float | None:
    _ensure_initialized()
    return get_landcover_c_payload(ee, _baseline_logger, zone_geometry=zone_geometry)
