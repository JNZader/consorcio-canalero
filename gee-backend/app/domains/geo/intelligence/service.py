"""Service layer for the operational intelligence sub-module.

Orchestrates calculations, database persistence, and cross-cutting concerns.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

import structlog
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.calculations import (
    calcular_indice_criticidad_hidrica,
    calcular_prioridad_canal,
    calcular_riesgo_camino,
    clasificar_nivel_riesgo,
    detectar_puntos_conflicto,
    generar_zonificacion,
    simular_escorrentia,
)
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.repository import GeoRepository

logger = structlog.get_logger(__name__)

intel_repo = IntelligenceRepository()
geo_repo = GeoRepository()


# ---------------------------------------------------------------------------
# HCI Calculation
# ---------------------------------------------------------------------------


def calculate_hci_for_zone(
    db: Session,
    zona_id: uuid.UUID,
    *,
    pendiente_media: float,
    acumulacion_media: float,
    twi_medio: float,
    proximidad_canal_m: float,
    historial_inundacion: float,
    pesos: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Calculate the Hydric Criticality Index for a zone and persist the result.

    Args:
        db: Database session.
        zona_id: Target operational zone ID.
        pendiente_media: Normalized mean slope (0-1).
        acumulacion_media: Normalized mean flow accumulation (0-1).
        twi_medio: Normalized mean TWI (0-1).
        proximidad_canal_m: Average distance to nearest canal (m).
        historial_inundacion: Flood history factor (0-1).
        pesos: Optional custom weights.

    Returns:
        dict with indice_final, nivel_riesgo, and component values.
    """
    zona = intel_repo.get_zona_by_id(db, zona_id)
    if zona is None:
        raise ValueError(f"Zona operativa {zona_id} no encontrada")

    # Normalize dist_canal: closer = higher risk (inverted)
    # Assume max meaningful distance is 5000m
    dist_norm = max(1.0 - (proximidad_canal_m / 5000.0), 0.0)

    indice = calcular_indice_criticidad_hidrica(
        pendiente=pendiente_media,
        acumulacion=acumulacion_media,
        twi=twi_medio,
        dist_canal=dist_norm,
        hist_inundacion=historial_inundacion,
        pesos=pesos,
    )
    nivel = clasificar_nivel_riesgo(indice)

    ih = intel_repo.create_indice_hidrico(
        db,
        zona_id=zona_id,
        fecha_calculo=date.today(),
        pendiente_media=pendiente_media,
        acumulacion_media=acumulacion_media,
        twi_medio=twi_medio,
        proximidad_canal_m=proximidad_canal_m,
        historial_inundacion=historial_inundacion,
        indice_final=indice,
        nivel_riesgo=nivel,
    )
    db.commit()

    logger.info(
        "hci.calculated",
        zona_id=str(zona_id),
        indice=indice,
        nivel=nivel,
    )

    return {
        "zona_id": str(zona_id),
        "indice_final": indice,
        "nivel_riesgo": nivel,
        "componentes": {
            "pendiente_media": pendiente_media,
            "acumulacion_media": acumulacion_media,
            "twi_medio": twi_medio,
            "proximidad_canal_m": proximidad_canal_m,
            "historial_inundacion": historial_inundacion,
        },
    }


# ---------------------------------------------------------------------------
# Conflict Detection
# ---------------------------------------------------------------------------


def detect_conflicts(
    db: Session,
    canales_gdf: "gpd.GeoDataFrame",
    caminos_gdf: "gpd.GeoDataFrame",
    drenajes_gdf: "gpd.GeoDataFrame",
    flow_acc_path: str,
    slope_path: str,
    buffer_m: float = 50.0,
) -> dict[str, Any]:
    """Run conflict detection and persist results.

    Args:
        db: Database session.
        canales_gdf: Canal geometries.
        caminos_gdf: Road geometries.
        drenajes_gdf: Drainage geometries.
        flow_acc_path: Path to flow accumulation raster.
        slope_path: Path to slope raster.
        buffer_m: Buffer distance in meters.

    Returns:
        dict with count and summary of detected conflicts.
    """
    from geoalchemy2.shape import from_shape

    result_gdf = detectar_puntos_conflicto(
        canales_gdf=canales_gdf,
        caminos_gdf=caminos_gdf,
        drenajes_gdf=drenajes_gdf,
        flow_acc_path=flow_acc_path,
        slope_path=slope_path,
        buffer_m=buffer_m,
    )

    if result_gdf.empty:
        return {"conflictos_detectados": 0, "detalle": []}

    conflictos_data = []
    for _, row in result_gdf.iterrows():
        wkt = from_shape(row.geometry, srid=4326)
        conflictos_data.append(
            {
                "tipo": row["tipo"],
                "geometria": wkt,
                "descripcion": row["descripcion"],
                "severidad": row["severidad"],
                "acumulacion_valor": row["acumulacion_valor"],
                "pendiente_valor": row["pendiente_valor"],
            }
        )

    count = intel_repo.bulk_create_conflictos(db, conflictos_data)
    db.commit()

    logger.info("conflicts.detected", count=count)

    return {
        "conflictos_detectados": count,
        "detalle": [
            {
                "tipo": c["tipo"],
                "severidad": c["severidad"],
                "acumulacion": c["acumulacion_valor"],
                "pendiente": c["pendiente_valor"],
            }
            for c in conflictos_data
        ],
    }


# ---------------------------------------------------------------------------
# Runoff Simulation
# ---------------------------------------------------------------------------


def run_runoff_simulation(
    db: Session,
    punto: tuple[float, float],
    lluvia_mm: float,
    flow_dir_path: str,
    flow_acc_path: str,
) -> dict[str, Any]:
    """Run a runoff simulation and return GeoJSON result.

    Args:
        db: Database session (for future alert creation).
        punto: (lon, lat) starting point.
        lluvia_mm: Rainfall in mm.
        flow_dir_path: Path to D8 flow direction raster.
        flow_acc_path: Path to flow accumulation raster.

    Returns:
        GeoJSON FeatureCollection.
    """
    result = simular_escorrentia(
        flow_dir_path=flow_dir_path,
        flow_acc_path=flow_acc_path,
        punto_inicio=punto,
        lluvia_mm=lluvia_mm,
    )

    logger.info(
        "runoff.simulated",
        punto=punto,
        lluvia_mm=lluvia_mm,
        features=len(result.get("features", [])),
    )

    return result


# ---------------------------------------------------------------------------
# Zone Generation
# ---------------------------------------------------------------------------


def generate_zones(
    db: Session,
    dem_path: str,
    flow_acc_path: str,
    cuenca: str = "default",
    threshold: int = 2000,
) -> dict[str, Any]:
    """Generate operational zones from watershed delineation and persist them.

    Args:
        db: Database session.
        dem_path: Path to the DEM.
        flow_acc_path: Path to flow accumulation raster.
        cuenca: Watershed name.
        threshold: Pour point threshold.

    Returns:
        dict with zonas_creadas count and zone details.
    """
    gdf = generar_zonificacion(
        dem_path=dem_path,
        flow_acc_path=flow_acc_path,
        threshold=threshold,
    )

    if gdf.empty:
        return {"zonas_creadas": 0, "zonas": []}

    from geoalchemy2.shape import from_shape

    zonas = []
    for idx, row in gdf.iterrows():
        wkt = from_shape(row.geometry, srid=4326)
        zona = intel_repo.create_zona(
            db,
            nombre=f"{cuenca}_zona_{row.get('basin_id', idx)}",
            geometria=wkt,
            cuenca=cuenca,
            superficie_ha=row.get("superficie_ha", 0.0),
        )
        zonas.append(
            {
                "id": str(zona.id),
                "nombre": zona.nombre,
                "cuenca": zona.cuenca,
                "superficie_ha": zona.superficie_ha,
            }
        )

    db.commit()
    logger.info("zones.generated", count=len(zonas), cuenca=cuenca)

    return {"zonas_creadas": len(zonas), "zonas": zonas}


# ---------------------------------------------------------------------------
# Canal Priorities
# ---------------------------------------------------------------------------


def calculate_canal_priorities(
    db: Session,
    canales_gdf: "gpd.GeoDataFrame",
    flow_acc_path: str,
    slope_path: str,
) -> list[dict[str, Any]]:
    """Score all canals by priority and return ranked list.

    Args:
        db: Database session.
        canales_gdf: Canal geometries with at least 'id' and 'nombre' columns.
        flow_acc_path: Path to flow accumulation raster.
        slope_path: Path to slope raster.

    Returns:
        List of canal priority dicts, sorted by priority descending.
    """
    import geopandas as gpd
    from geoalchemy2.shape import to_shape

    zonas_criticas_gdf = None
    try:
        zonas_criticas = intel_repo.get_zonas_criticas(db, "alto")
        if zonas_criticas:
            geometries = [to_shape(z.geometria) for z in zonas_criticas]
            zonas_criticas_gdf = gpd.GeoDataFrame(
                geometry=geometries, crs="EPSG:4326"
            )
    except Exception:
        pass

    results = []
    for _, row in canales_gdf.iterrows():
        score = calcular_prioridad_canal(
            canal_geom=row.geometry,
            flow_acc_path=flow_acc_path,
            slope_path=slope_path,
            zonas_criticas_gdf=zonas_criticas_gdf,
        )
        results.append(
            {
                "canal_id": str(row.get("id", "")),
                "nombre": str(row.get("nombre", "")),
                "prioridad": score,
            }
        )

    results.sort(key=lambda x: x["prioridad"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Road Risks
# ---------------------------------------------------------------------------


def calculate_road_risks(
    db: Session,
    caminos_gdf: "gpd.GeoDataFrame",
    flow_acc_path: str,
    slope_path: str,
    twi_path: str,
    drainage_gdf: Optional["gpd.GeoDataFrame"] = None,
) -> list[dict[str, Any]]:
    """Score all roads by flooding risk and return ranked list.

    Args:
        db: Database session.
        caminos_gdf: Road geometries with at least 'id' and 'nombre' columns.
        flow_acc_path: Path to flow accumulation raster.
        slope_path: Path to slope raster.
        twi_path: Path to TWI raster.
        drainage_gdf: Optional drainage network geometries.

    Returns:
        List of road risk dicts, sorted by risk descending.
    """
    results = []
    for _, row in caminos_gdf.iterrows():
        score = calcular_riesgo_camino(
            camino_geom=row.geometry,
            flow_acc_path=flow_acc_path,
            slope_path=slope_path,
            twi_path=twi_path,
            drainage_gdf=drainage_gdf,
        )
        results.append(
            {
                "camino_id": str(row.get("id", "")),
                "nombre": str(row.get("nombre", "")),
                "riesgo": score,
            }
        )

    results.sort(key=lambda x: x["riesgo"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Alert Evaluation
# ---------------------------------------------------------------------------


def check_alerts(db: Session) -> dict[str, Any]:
    """Evaluate alert conditions across all zones.

    Checks:
    - Zones with HCI >= 75 (critico) → critico alert.
    - Zones with HCI >= 50 (alto) → advertencia alert.
    - Deduplication: skips zones that already have an active alert.

    Returns:
        dict with new alerts created and active total.
    """
    alertas_existentes = intel_repo.get_alertas_activas(db)
    zonas_con_alerta = {a.zona_id for a in alertas_existentes}

    nuevas = 0

    # Critical zones (HCI >= 75)
    zonas_criticas = intel_repo.get_zonas_criticas(db, "critico")
    for zona in zonas_criticas:
        if zona.id not in zonas_con_alerta:
            intel_repo.create_alerta(
                db,
                tipo="umbral_superado",
                mensaje=(
                    f"La zona '{zona.nombre}' ha superado el umbral critico "
                    f"de indice hidrico"
                ),
                nivel="critico",
                zona_id=zona.id,
                datos={"cuenca": zona.cuenca},
            )
            zonas_con_alerta.add(zona.id)
            nuevas += 1

    # Warning zones (HCI >= 50, alto level) — skip those already alerted above
    zonas_alto = intel_repo.get_zonas_criticas(db, "alto")
    for zona in zonas_alto:
        if zona.id not in zonas_con_alerta:
            intel_repo.create_alerta(
                db,
                tipo="umbral_superado",
                mensaje=(
                    f"La zona '{zona.nombre}' presenta nivel alto "
                    f"de indice hidrico"
                ),
                nivel="advertencia",
                zona_id=zona.id,
                datos={"cuenca": zona.cuenca},
            )
            zonas_con_alerta.add(zona.id)
            nuevas += 1

    if nuevas > 0:
        db.commit()

    logger.info("alerts.evaluated", nuevas=nuevas)

    return {
        "alertas_creadas": nuevas,
        "alertas_activas_total": len(alertas_existentes) + nuevas,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def get_dashboard(db: Session) -> dict[str, Any]:
    """Get the aggregated intelligence dashboard."""
    return intel_repo.get_dashboard_inteligente(db)
