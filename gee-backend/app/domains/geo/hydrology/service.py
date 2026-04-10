"""Service layer for the hydrology subdomain.

PURPOSE
-------
Quantitative peak flow estimation for a specific rainfall event date, per
operational zone (ZonaOperativa). Implements the two-step hydrological model:

    1. Kirpich formula  → time of concentration (Tc, minutes)
    2. Rational Method  → peak discharge Q (m³/s)

External data sources used at runtime:
    - Google Earth Engine / USGS SRTM  → mean slope per zone (degrees)
    - Google Earth Engine / Copernicus Sentinel-2 SR → NDVI → runoff coefficient C
    - CHIRPS daily precipitation records (stored in ``RainfallRecord``) → intensity I

HOW IT DIFFERS FROM RELATED MODULES
-------------------------------------
``app.domains.geo.hydrology`` (this module)
    Quantitative **peak flow estimation** for a specific storm event date.
    Answers: "given rainfall on date X, what is the expected discharge Q (m³/s)
    and hydraulic risk for each operational zone?"
    Result stored in ``FloodFlowResult``; risk levels are: bajo / medio / alto /
    crítico.

``app.domains.geo.hydrology`` vs. ``app.domains.geo.hydrology_static`` (TWI)
    The sibling ``hydrology.py`` module in the ``geo`` domain computes the
    **Topographic Wetness Index (TWI)** — a static terrain property that
    describes how water accumulates based on slope and upslope area.  TWI is
    computed once from DEM data and does NOT model storm events or time-varying
    rainfall.

``app.domains.ml.flood_prediction``
    Probabilistic **U-Net satellite-based flood detection** using Sentinel-1 SAR
    imagery.  Classifies individual pixels as flooded / not-flooded after a flood
    has already occurred.  Output is a spatial binary mask, NOT a discharge value.
    Complementary to this module: use ML detection for post-event mapping and
    Kirpich+Rational for pre/during-event discharge estimation.

CONCURRENCY NOTE
----------------
GEE Python SDK calls are synchronous and I/O-bound.  ``compute_flood_flow``
dispatches per-zone computations through a ``ThreadPoolExecutor`` (max 4 workers)
so that slope and NDVI fetches for different zones run concurrently.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any, Optional

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domains.geo.hydrology.calculations import (
    classify_hydraulic_risk,
    kirpich_tc,
    ndvi_to_c,
    rational_method_q,
)
from app.domains.geo.hydrology.repository import FloodFlowRepository
from app.domains.geo.hydrology.schemas import (
    FloodFlowResponse,
    ZonaFloodFlowResult,
)
from app.domains.geo.hydrology.service_support import (
    finalize_flood_flow_impl,
    get_canal_length_for_zona_impl,
    get_rainfall_intensity_impl,
    get_zona_geojson_impl,
    preload_zona_db_data_impl,
    run_gee_for_zonas_impl,
)
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.models import RainfallRecord

logger = logging.getLogger(__name__)


class FloodFlowService:
    """Orchestrates Kirpich + Método Racional flood flow estimation."""

    def __init__(self, repository: FloodFlowRepository) -> None:
        self.repository = repository

    # ── GEE helpers ──────────────────────────────────────────────────────────

    def get_slope_from_gee(self, zona_geometria: dict[str, Any]) -> float:
        """Get mean slope (degrees) for a zone geometry using GEE SRTM.

        Uses USGS/SRTMGL1_003 → ee.Terrain.slope() → reduceRegion(mean).

        Args:
            zona_geometria: GeoJSON geometry dict (Polygon) for the zone.

        Returns:
            Mean slope in degrees (float). Falls back to 0.5 if GEE returns null.

        Raises:
            RuntimeError: If GEE has not been initialized.
            ValueError: If zona_geometria is None.
        """
        if zona_geometria is None:
            raise ValueError("zona_geometria cannot be None")

        import ee

        try:
            from app.domains.geo.gee_service import _ensure_initialized

            _ensure_initialized()
        except RuntimeError:
            raise

        try:
            ee_geom = ee.Geometry(zona_geometria)
            srtm = ee.Image("USGS/SRTMGL1_003")
            slope_img = ee.Terrain.slope(srtm)
            result = slope_img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_geom,
                scale=30,
                maxPixels=1e9,
            ).getInfo()

            slope_val = result.get("slope") if result else None
            if slope_val is None:
                logger.warning(
                    "GEE returned null slope for geometry — falling back to 0.5 degrees"
                )
                return 0.5

            return float(slope_val)

        except ee.EEException as exc:
            logger.error("GEE EEException fetching slope: %s", exc)
            return 0.5

    def get_canal_length_for_zona(
        self,
        db: Session,
        zona_id: uuid.UUID,
        zona_geometria: dict[str, Any],
        superficie_ha: float,
    ) -> float:
        """Get the longest canal / waterway length (m) within a zone.

        Tries a PostGIS spatial query against a 'waterways' table first.
        Falls back to sqrt(area_m2) if the table doesn't exist or returns None.

        Args:
            db: SQLAlchemy session.
            zona_id: Zone UUID (for logging).
            zona_geometria: GeoJSON geometry dict for the zone.
            superficie_ha: Zone area in hectares (used for fallback).

        Returns:
            Longest canal length in meters (float, always > 0).
        """
        return get_canal_length_for_zona_impl(
            db=db,
            text_fn=text,
            logger=logger,
            zona_id=zona_id,
            zona_geometria=zona_geometria,
            superficie_ha=superficie_ha,
        )

    def get_ndvi_and_c(
        self,
        zona_geometria: dict[str, Any],
        fecha_referencia: date,
    ) -> tuple[float, str]:
        """Get mean NDVI via Sentinel-2 SR and convert to runoff coefficient C.

        Queries S2_SR_HARMONIZED for the 30 days prior to fecha_referencia,
        filters for < 30% cloud cover, and computes median NDVI.

        Args:
            zona_geometria: GeoJSON geometry dict (Polygon) for the zone.
            fecha_referencia: Reference date; images are searched 30 days before.

        Returns:
            Tuple (ndvi_value: float, c_source: str).
            Falls back to (0.4, "fallback_default") when no images are found.
        """
        import ee

        try:
            from app.domains.geo.gee_service import _ensure_initialized

            _ensure_initialized()
        except RuntimeError:
            logger.warning("GEE not initialized — using fallback C=0.4")
            return (0.4, "fallback_default")

        try:
            ee_geom = ee.Geometry(zona_geometria)

            # Try land cover C first (ESA WorldCover — more accurate than NDVI)
            from app.domains.geo.gee_service import get_landcover_c_coefficient

            c_landcover = get_landcover_c_coefficient(ee_geom)
            if c_landcover is not None:
                return (c_landcover, "landcover")

            # Fallback: NDVI from recent Sentinel-2
            fecha_inicio = fecha_referencia - timedelta(days=30)

            ndvi_img = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterDate(fecha_inicio.isoformat(), fecha_referencia.isoformat())
                .filterBounds(ee_geom)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                .median()
                .normalizedDifference(["B8", "B4"])
            )

            result = ndvi_img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_geom,
                scale=10,
                maxPixels=1e9,
            ).getInfo()

            ndvi_val = result.get("nd") if result else None

            if ndvi_val is None:
                logger.debug(
                    "No Sentinel-2 images found for date %s — using fallback C=0.4",
                    fecha_referencia,
                )
                return (0.4, "fallback_default")

            return (ndvi_to_c(float(ndvi_val)), "ndvi_sentinel2")

        except ee.EEException as exc:
            logger.error("GEE EEException fetching NDVI: %s", exc)
            return (0.4, "fallback_default")

    # ── Rainfall helper ──────────────────────────────────────────────────────

    def _get_rainfall_intensity(
        self,
        db: Session,
        zona_id: uuid.UUID,
        fecha_lluvia: date,
    ) -> float:
        """Fetch daily CHIRPS precipitation for zona + date and convert to mm/h.

        Assumes a 6-hour design storm for intensity conversion:
            I = precipitation_mm / 6.0

        Returns 20.0 mm/h as a safe fallback when no data is found.
        """
        return get_rainfall_intensity_impl(
            db=db,
            select_fn=select,
            rainfall_model=RainfallRecord,
            logger=logger,
            zona_id=zona_id,
            fecha_lluvia=fecha_lluvia,
        )

    # ── Zone geometry fetch ──────────────────────────────────────────────────

    def _get_zona_geojson(
        self, db: Session, zona_id: uuid.UUID
    ) -> Optional[dict[str, Any]]:
        """Fetch the PostGIS geometry of a ZonaOperativa as a GeoJSON dict."""
        return get_zona_geojson_impl(
            db=db,
            select_fn=select,
            st_as_geojson=ST_AsGeoJSON,
            zona_model=ZonaOperativa,
            json_module=json,
            zona_id=zona_id,
        )

    # ── Core orchestration ───────────────────────────────────────────────────

    async def compute_flood_flow(
        self,
        db: Session,
        zona_ids: list[uuid.UUID],
        fecha_lluvia: date,
    ) -> FloodFlowResponse:
        """Compute flood flow via Kirpich + Rational Method for multiple zones.

        Architecture: DB access is NEVER done inside the thread pool.
        SQLAlchemy sessions are not thread-safe and PostgreSQL invalidates the
        entire transaction on the first query error, breaking all subsequent
        queries on that session.

        Pipeline per zone:
            Phase A (main thread, DB):
                1. Load ZonaOperativa (nombre, geometria, superficie_ha, capacidad_m3s)
                2. Fetch GeoJSON geometry
                3. Estimate canal length (PostGIS or sqrt fallback)
                4. Fetch CHIRPS rainfall intensity (or fallback 20 mm/h)
            Phase B (thread pool, GEE only):
                5. GEE SRTM slope → S = tan(slope_rad)
                6. Sentinel-2 NDVI → C coefficient
            Phase C (main thread, compute + DB write):
                7. kirpich_tc(L_m, S) → tc_minutos
                8. rational_method_q(C, I, A) → Q (m³/s)
                9. classify_hydraulic_risk(Q, capacidad_m3s) → nivel_riesgo
                10. Upsert result to DB
        """
        _, zona_db_data, errors = preload_zona_db_data_impl(
            db=db,
            zona_ids=zona_ids,
            select_fn=select,
            zona_model=ZonaOperativa,
            get_zona_geojson=self._get_zona_geojson,
            get_canal_length_for_zona=self.get_canal_length_for_zona,
            get_rainfall_intensity=self._get_rainfall_intensity,
            fecha_lluvia=fecha_lluvia,
        )

        if not zona_db_data:
            db.rollback()
            return FloodFlowResponse(
                total_zonas=len(zona_ids),
                fecha_lluvia=fecha_lluvia,
                results=[],
                errors=errors,
            )

        gee_results = run_gee_for_zonas_impl(
            zona_db_data=zona_db_data,
            fecha_lluvia=fecha_lluvia,
            get_slope_from_gee=self.get_slope_from_gee,
            get_ndvi_and_c=self.get_ndvi_and_c,
            logger=logger,
        )

        today = date.today()
        results, compute_errors = finalize_flood_flow_impl(
            db=db,
            zona_db_data=zona_db_data,
            gee_results=gee_results,
            fecha_lluvia=fecha_lluvia,
            today=today,
            repository=self.repository,
            kirpich_tc=kirpich_tc,
            rational_method_q=rational_method_q,
            classify_hydraulic_risk=classify_hydraulic_risk,
            result_schema=ZonaFloodFlowResult,
            logger=logger,
        )
        errors.extend(compute_errors)

        return FloodFlowResponse(
                total_zonas=len(zona_ids),
                fecha_lluvia=fecha_lluvia,
                results=[],
                errors=errors,
            )

        # ── Phase B: GEE calls in thread pool (NO db session inside) ─────────
        def _gee_for_zona(zona_id: uuid.UUID) -> dict[str, Any]:
            """Run slope + NDVI GEE calls for one zone. No DB access."""
            data = zona_db_data[zona_id]
            geometria = data["geometria"]

            slope_degrees = self.get_slope_from_gee(geometria)
            slope_rad = math.radians(slope_degrees)
            S = math.tan(slope_rad)

            c_val, c_source = self.get_ndvi_and_c(geometria, fecha_lluvia)

            return {"S": S, "c_val": c_val, "c_source": c_source}

        gee_results: dict[uuid.UUID, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_zona = {
                executor.submit(_gee_for_zona, zona_id): zona_id
                for zona_id in zona_db_data
            }
            for future in as_completed(future_to_zona):
                zona_id = future_to_zona[future]
                try:
                    gee_results[zona_id] = future.result()
                except Exception as exc:
                    logger.error("flood_flow.gee_error zona=%s error=%s", zona_id, exc)
                    # GEE failed — use safe defaults so the zone is not lost
                    gee_results[zona_id] = {
                        "S": math.tan(math.radians(0.5)),
                        "c_val": 0.4,
                        "c_source": "fallback_default",
                    }

        # ── Phase C: compute + DB writes in the main thread ──────────────────
        today = date.today()
        for zona_id, db_data in zona_db_data.items():
            try:
                gee = gee_results[zona_id]
                zona = db_data["zona"]

                tc = kirpich_tc(db_data["L_m"], gee["S"])
                Q = rational_method_q(
                    gee["c_val"],
                    db_data["intensidad_mm_h"],
                    db_data["superficie_ha"] / 100.0,
                )
                nivel_riesgo, porcentaje = classify_hydraulic_risk(
                    Q, db_data["capacidad_m3s"]
                )

                self.repository.upsert(
                    db,
                    zona_id,
                    fecha_lluvia,
                    {
                        "fecha_calculo": today,
                        "tc_minutos": tc,
                        "c_escorrentia": gee["c_val"],
                        "c_source": gee["c_source"],
                        "intensidad_mm_h": db_data["intensidad_mm_h"],
                        "area_km2": db_data["superficie_ha"] / 100.0,
                        "caudal_m3s": Q,
                        "capacidad_m3s": db_data["capacidad_m3s"],
                        "porcentaje_capacidad": porcentaje,
                        "nivel_riesgo": nivel_riesgo,
                    },
                )

                results.append(
                    ZonaFloodFlowResult(
                        zona_id=zona_id,
                        zona_nombre=zona.nombre,
                        tc_minutos=tc,
                        c_escorrentia=gee["c_val"],
                        c_source=gee["c_source"],
                        intensidad_mm_h=db_data["intensidad_mm_h"],
                        area_km2=db_data["superficie_ha"] / 100.0,
                        caudal_m3s=Q,
                        capacidad_m3s=db_data["capacidad_m3s"],
                        porcentaje_capacidad=porcentaje,
                        nivel_riesgo=nivel_riesgo,
                        fecha_lluvia=fecha_lluvia,
                        fecha_calculo=today,
                    )
                )
            except Exception as exc:
                logger.error(
                    "flood_flow.compute_error zona=%s error=%s",
                    zona_id,
                    exc,
                    exc_info=True,
                )
                errors.append({"zona_id": str(zona_id), "error": str(exc)})

        db.commit()

        return FloodFlowResponse(
            total_zonas=len(zona_ids),
            fecha_lluvia=fecha_lluvia,
            results=results,
            errors=errors,
        )
