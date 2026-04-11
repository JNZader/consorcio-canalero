"""Automatic basin/sub-basin/point/consorcio corridor analysis."""

from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import Any, Literal

from geoalchemy2.shape import to_shape
from shapely.geometry import shape as shapely_shape
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.models import TipoGeoLayer
from app.domains.geo.repository import GeoRepository
from app.domains.geo.routing import corridor_routing

ScopeType = Literal["cuenca", "subcuenca", "consorcio", "punto", "zona"]
MAX_EXISTING_NETWORK_OVERLAP_RATIO = 0.7
MIN_PRIORITY_SCORE = 15.0
MIN_NETWORK_DISTANCE_M = 40.0
MAX_NETWORK_DISTANCE_M = 8000.0
DISTANCE_ONLY_PRIORITY_SCALE = 0.12
FLOW_ACC_HOTSPOT_THRESHOLD_PERCENTILE = 70.0


def _get_layer_path(db: Session, tipo: TipoGeoLayer) -> str | None:
    repo = GeoRepository()
    layers, _ = repo.get_layers(db, tipo_filter=tipo, page=1, limit=1)
    if layers and layers[0].archivo_path:
        return layers[0].archivo_path
    return None


def _extract_geometries(items: list[dict[str, Any]]) -> list[Any]:
    geometries: list[Any] = []
    for item in items:
        geometry = item.get("geometry")
        if geometry is None:
            continue
        try:
            geometries.append(shapely_shape(geometry) if isinstance(geometry, dict) else geometry)
        except Exception:
            continue
    return geometries


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _scope_filters(scope_type: ScopeType, scope_id: str | None) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    if scope_type == "consorcio":
        return "", params
    if scope_type == "cuenca":
        if not scope_id:
            raise NotFoundError("scope_id is required for cuenca analysis")
        params["scope_id"] = scope_id
        return "WHERE z.cuenca = :scope_id", params
    if scope_type in {"subcuenca", "zona"}:
        if not scope_id:
            raise NotFoundError("scope_id is required for subcuenca analysis")
        params["scope_id"] = scope_id
        return "WHERE z.id = CAST(:scope_id AS uuid)", params
    if not scope_id:
        raise NotFoundError("scope_id is required for point analysis")
    params["scope_id"] = scope_id
    return "WHERE z.id = CAST(:scope_id AS uuid)", params


def _resolve_point_scope(db: Session, point_lon: float, point_lat: float) -> tuple[str, str]:
    row = db.execute(
        text(
            """
            WITH picked_zone AS (
                SELECT z.id::text AS id, z.cuenca
                FROM zonas_operativas z
                WHERE z.geometria IS NOT NULL
                  AND ST_Contains(z.geometria, ST_SetSRID(ST_Point(:lon, :lat), 4326))
                ORDER BY ST_Area(z.geometria) ASC
                LIMIT 1
            )
            SELECT id, cuenca FROM picked_zone
            UNION ALL
            SELECT z.id::text AS id, z.cuenca
            FROM zonas_operativas z
            WHERE z.geometria IS NOT NULL
            ORDER BY z.geometria <-> ST_SetSRID(ST_Point(:lon, :lat), 4326)
            LIMIT 1
            """
        ),
        {"lon": point_lon, "lat": point_lat},
    ).mappings().first()

    if row is None or not row["id"] or not row["cuenca"]:
        raise NotFoundError("No se encontró una subcuenca válida para el punto seleccionado")
    return str(row["id"]), str(row["cuenca"])


def load_auto_analysis_zones(
    db: Session,
    *,
    scope_type: ScopeType,
    scope_id: str | None,
    point_lon: float | None = None,
    point_lat: float | None = None,
) -> list[dict[str, Any]]:
    """Load zones and priority signals for automatic corridor analysis."""
    anchor_zone_id: str | None = None
    if scope_type == "punto":
        if point_lon is None or point_lat is None:
            raise NotFoundError("point_lon y point_lat son obligatorios para el análisis puntual")
        anchor_zone_id, parent_cuenca = _resolve_point_scope(db, point_lon, point_lat)
        scope_type = "cuenca"
        scope_id = parent_cuenca

    if scope_type in {"subcuenca", "zona"}:
        anchor_zone_id = scope_id
        zona_scope = db.execute(
            text("SELECT cuenca FROM zonas_operativas WHERE id = CAST(:scope_id AS uuid)"),
            {"scope_id": scope_id},
        ).scalar()
        if zona_scope is None:
            raise NotFoundError("Subcuenca no encontrada para el análisis automático")
        scope_type = "cuenca"
        scope_id = str(zona_scope)

    where_clause, params = _scope_filters(scope_type, scope_id)
    rows = db.execute(
        text(
            f"""
            WITH latest_hci AS (
                SELECT DISTINCT ON (ih.zona_id)
                    ih.zona_id,
                    ih.indice_final,
                    ih.nivel_riesgo
                FROM indices_hidricos ih
                ORDER BY ih.zona_id, ih.fecha_calculo DESC
            ),
            latest_flood AS (
                SELECT DISTINCT ON (czs.zona_id)
                    czs.zona_id,
                    czs.mean_score
                FROM composite_zonal_stats czs
                WHERE czs.tipo = 'flood_risk'
                ORDER BY czs.zona_id, czs.fecha_calculo DESC
            )
            , network AS (
                SELECT ST_Union(ST_Transform(cn.geom, 32720)) AS geom
                FROM canal_network cn
                WHERE cn.geom IS NOT NULL
            )
            SELECT
                z.id::text AS id,
                z.nombre,
                z.cuenca,
                ST_AsGeoJSON(ST_PointOnSurface(z.geometria)) AS representative_point,
                ST_AsGeoJSON(z.geometria) AS geometry,
                COALESCE(latest_hci.indice_final, 0) AS hydric_score,
                latest_hci.nivel_riesgo AS risk_level,
                COALESCE(latest_flood.mean_score, 0) AS flood_score,
                ROUND(
                    (
                        (COALESCE(latest_hci.indice_final, 0) * 0.7)
                        + (COALESCE(latest_flood.mean_score, 0) * 0.3)
                    )::numeric,
                    2
                ) AS priority_score,
                CASE WHEN network.geom IS NULL THEN NULL
                     ELSE ST_AsGeoJSON(
                        ST_Transform(
                          ST_ClosestPoint(network.geom, ST_Transform(ST_PointOnSurface(z.geometria), 32720)),
                          4326
                        )
                     )
                END AS nearest_network_point,
                CASE WHEN network.geom IS NULL THEN NULL
                     ELSE ROUND(
                        ST_Distance(
                          ST_Transform(ST_PointOnSurface(z.geometria), 32720),
                          ST_ClosestPoint(network.geom, ST_Transform(ST_PointOnSurface(z.geometria), 32720))
                        )::numeric,
                        2
                     )
                END AS distance_to_network_m
            FROM zonas_operativas z
            LEFT JOIN latest_hci ON latest_hci.zona_id = z.id
            LEFT JOIN latest_flood ON latest_flood.zona_id = z.id
            CROSS JOIN network
            {where_clause}
            ORDER BY priority_score DESC, z.nombre
            LIMIT 40
            """
        ),
        params,
    ).mappings()

    zones = []
    for row in rows:
        point = json.loads(row["representative_point"]) if row["representative_point"] else None
        if not point or point.get("type") != "Point":
            continue
        nearest_network_point = (
            json.loads(row["nearest_network_point"]) if row.get("nearest_network_point") else None
        )
        zones.append(
            {
                "id": row["id"],
                "nombre": row["nombre"],
                "cuenca": row["cuenca"],
                "risk_level": row["risk_level"] or "desconocido",
                "hydric_score": float(row["hydric_score"] or 0),
                "flood_score": float(row["flood_score"] or 0),
                "priority_score": float(row["priority_score"] or 0),
                "point": point,
                "geometry": json.loads(row["geometry"]) if row.get("geometry") else None,
                "nearest_network_point": nearest_network_point,
                "distance_to_network_m": float(row["distance_to_network_m"] or 0),
            }
        )
    if not zones:
        raise NotFoundError("No zones found for automatic analysis")
    if anchor_zone_id:
        for zone in zones:
            zone["anchor"] = zone["id"] == anchor_zone_id
    return zones


def _zone_is_actionable(zone: dict[str, Any]) -> bool:
    return (
        float(zone.get("priority_score") or 0) >= MIN_PRIORITY_SCORE
        or float(zone.get("hydric_score") or 0) >= MIN_PRIORITY_SCORE
        or float(zone.get("flood_score") or 0) >= MIN_PRIORITY_SCORE
        or str(zone.get("risk_level") or "").lower() in {"alto", "critico"}
    )


def _build_suggestion_seed_candidates(
    db: Session,
    zones: list[dict[str, Any]],
    *,
    max_candidates: int,
) -> list[dict[str, Any]]:
    repo = IntelligenceRepository()
    batch_id = repo.get_latest_batch(db)
    if batch_id is None:
        return []

    zone_shapes = []
    for zone in zones:
        geometry = zone.get("geometry")
        if not geometry:
            continue
        try:
            zone_shapes.append((zone, shapely_shape(geometry)))
        except Exception:
            continue

    if not zone_shapes:
        return []

    seeds: list[dict[str, Any]] = []
    seen_zone_ids: set[str] = set()
    for tipo in ("gap", "hotspot"):
        items, _ = repo.get_suggestions_by_tipo(db, tipo, page=1, limit=max_candidates * 5, batch_id=batch_id)
        for item in items:
            if item.score is None or float(item.score) <= 0:
                continue
            if item.geometry is None:
                continue
            try:
                suggestion_geom = to_shape(item.geometry)
            except Exception:
                continue
            seed_point = suggestion_geom.representative_point()
            matched_zone = None
            for zone, zone_shape in zone_shapes:
                if zone_shape.contains(seed_point) or zone_shape.intersects(seed_point) or zone_shape.intersects(suggestion_geom):
                    matched_zone = zone
                    break
            if matched_zone is None:
                continue
            if matched_zone["id"] in seen_zone_ids:
                continue
            network_point = matched_zone.get("nearest_network_point") or {}
            network_coords = tuple(network_point.get("coordinates") or [])
            network_distance_m = float(matched_zone.get("distance_to_network_m") or 0.0)
            if len(network_coords) != 2:
                continue
            if network_distance_m < MIN_NETWORK_DISTANCE_M or network_distance_m > MAX_NETWORK_DISTANCE_M:
                continue
            seen_zone_ids.add(matched_zone["id"])
            seeds.append(
                {
                    "candidate_id": f"{matched_zone['id']}::{tipo}::network",
                    "candidate_type": f"{tipo}_to_network",
                    "source_zone_id": matched_zone["id"],
                    "source_zone_name": matched_zone["nombre"],
                    "target_zone_id": "network",
                    "target_zone_name": "Red existente",
                    "from_lon": float(seed_point.x),
                    "from_lat": float(seed_point.y),
                    "to_lon": network_coords[0],
                    "to_lat": network_coords[1],
                    "zone_pair_distance_deg": round(_distance((float(seed_point.x), float(seed_point.y)), network_coords), 6),
                    "network_distance_m": round(network_distance_m, 2),
                    "priority_score": round(max(float(matched_zone.get('priority_score') or 0), float(item.score or 0)), 2),
                    "reason": (
                        f"Descargar {tipo} detectado en {matched_zone['nombre']} "
                        f"hacia la red existente más cercana en {matched_zone['cuenca']}"
                    ),
                }
            )
            if len(seeds) >= max_candidates:
                return seeds
    return seeds


def _load_proxy_hydric_scores(
    db: Session,
    zones: list[dict[str, Any]],
) -> dict[str, float]:
    flow_acc_path = _get_layer_path(db, TipoGeoLayer.FLOW_ACC)
    if not flow_acc_path or not Path(flow_acc_path).exists():
        return {}

    try:
        import rasterio
        from rasterio.transform import rowcol
    except Exception:
        return {}

    sampled: list[tuple[str, float]] = []
    try:
        with rasterio.open(flow_acc_path) as src:
            data = src.read(1)
            nodata = src.nodata
            for zone in zones:
                coords = tuple(zone.get("point", {}).get("coordinates") or [])
                if len(coords) != 2:
                    continue
                try:
                    row, col = rowcol(src.transform, coords[0], coords[1])
                except Exception:
                    continue
                if not (0 <= row < src.height and 0 <= col < src.width):
                    continue
                value = float(data[row, col])
                if not math.isfinite(value) or (nodata is not None and value == nodata) or value <= 0:
                    continue
                sampled.append((str(zone["id"]), math.log1p(value)))
    except Exception:
        return {}

    if not sampled:
        return {}

    values = [value for _, value in sampled]
    min_value = min(values)
    max_value = max(values)
    value_span = max(max_value - min_value, 1e-9)

    proxy_scores: dict[str, float] = {}
    for zone_id, log_flow in sampled:
        zone = next((item for item in zones if str(item["id"]) == zone_id), None)
        if zone is None:
            continue
        flow_score = ((log_flow - min_value) / value_span) * 100.0
        network_distance = float(zone.get("distance_to_network_m") or 0.0)
        distance_score = min(max((network_distance - 150.0) / 25.0, 0.0), 100.0)
        proxy_scores[zone_id] = round((flow_score * 0.75) + (distance_score * 0.25), 2)
    return proxy_scores


def _build_gap_seed_candidates(
    db: Session,
    zones: list[dict[str, Any]],
    *,
    max_candidates: int,
) -> list[dict[str, Any]]:
    from app.domains.geo.intelligence.calculations import detect_coverage_gaps
    from app.domains.geo.intelligence.suggestions import _load_canal_geometries

    canal_geometries = _load_canal_geometries(db)
    if not canal_geometries:
        return []

    zones_for_gap = []
    hci_scores: dict[str, float] = {}
    zone_by_id: dict[str, dict[str, Any]] = {}
    for zone in zones:
        if not zone.get("geometry"):
            continue
        zone_id = str(zone["id"])
        zones_for_gap.append(
            {
                "id": zone_id,
                "geometry": zone["geometry"],
                "nombre": zone["nombre"],
                "cuenca": zone["cuenca"],
            }
        )
        hci_scores[zone_id] = max(
            float(zone.get("hydric_score") or 0.0),
            float(zone.get("flood_score") or 0.0),
            float(zone.get("priority_score") or 0.0),
        )
        zone_by_id[zone_id] = zone

    if not zones_for_gap:
        return []

    if not any(score >= 25.0 for score in hci_scores.values()):
        hci_scores = _load_proxy_hydric_scores(db, zones)
        if not hci_scores:
            return []

    gap_results = detect_coverage_gaps(
        zones_for_gap,
        hci_scores,
        canal_geometries,
        threshold_km=1.0,
        hci_threshold=25.0,
    )
    seeds: list[dict[str, Any]] = []
    for gap in gap_results[: max_candidates * 2]:
        zone = zone_by_id.get(str(gap.get("zone_id")))
        if zone is None:
            continue
        network_point = zone.get("nearest_network_point") or {}
        network_coords = tuple(network_point.get("coordinates") or [])
        network_distance_m = float(zone.get("distance_to_network_m") or 0.0)
        if len(network_coords) != 2:
            continue
        if network_distance_m < MIN_NETWORK_DISTANCE_M or network_distance_m > MAX_NETWORK_DISTANCE_M:
            continue
        geometry = gap.get("geometry") or {}
        coords = tuple(geometry.get("coordinates") or [])
        if len(coords) != 2:
            continue
        seeds.append(
            {
                "candidate_id": f"{zone['id']}::gapcalc::network",
                "candidate_type": "gap_to_network",
                "source_zone_id": zone["id"],
                "source_zone_name": zone["nombre"],
                "target_zone_id": "network",
                "target_zone_name": "Red existente",
                "from_lon": coords[0],
                "from_lat": coords[1],
                "to_lon": network_coords[0],
                "to_lat": network_coords[1],
                "zone_pair_distance_deg": round(_distance(coords, network_coords), 6),
                "network_distance_m": round(network_distance_m, 2),
                "priority_score": round(max(float(zone.get("priority_score") or 0), float(gap.get("hci_score") or 0)), 2),
                "reason": (
                    f"Descargar gap {gap.get('severity', 'moderado')} detectado en {zone['nombre']} "
                    f"hacia la red existente más cercana en {zone['cuenca']}"
                ),
            }
        )
        if len(seeds) >= max_candidates:
            break
    return seeds


def _build_flow_acc_hotspot_candidates(
    db: Session,
    zones: list[dict[str, Any]],
    *,
    max_candidates: int,
) -> list[dict[str, Any]]:
    flow_acc_path = _get_layer_path(db, TipoGeoLayer.FLOW_ACC)
    if not flow_acc_path or not Path(flow_acc_path).exists():
        return []

    try:
        import numpy as np
        import rasterio
        from rasterio.mask import mask
        from rasterio.warp import transform, transform_geom
        from shapely.geometry import Point
        from shapely.ops import nearest_points, unary_union
    except Exception:
        return []

    from app.domains.geo.intelligence.suggestions import _load_canal_geometries

    canal_geometries = _load_canal_geometries(db)
    canal_shapes = _extract_geometries(canal_geometries)
    if not canal_shapes:
        return []
    canal_union = unary_union(canal_shapes)

    hotspot_rows: list[dict[str, Any]] = []
    try:
        with rasterio.open(flow_acc_path) as src:
            for zone in zones:
                geometry = zone.get("geometry")
                if not geometry:
                    continue
                try:
                    zone_geom = transform_geom("EPSG:4326", src.crs, geometry)
                    clipped, clipped_transform = mask(src, [zone_geom], crop=True, filled=False)
                except Exception:
                    continue

                band = np.ma.array(clipped[0])
                if band.count() == 0:
                    continue
                filled = np.ma.filled(band.astype(float), np.nan)
                if not np.isfinite(filled).any():
                    continue
                max_value = float(np.nanmax(filled))
                if not math.isfinite(max_value) or max_value <= 0:
                    continue
                local_row, local_col = np.unravel_index(np.nanargmax(filled), filled.shape)
                hotspot_x, hotspot_y = rasterio.transform.xy(
                    clipped_transform,
                    int(local_row),
                    int(local_col),
                    offset="center",
                )
                hotspot_lon, hotspot_lat = transform(
                    src.crs,
                    "EPSG:4326",
                    [hotspot_x],
                    [hotspot_y],
                )
                hotspot_point = Point(float(hotspot_lon[0]), float(hotspot_lat[0]))
                _, nearest_canal_pt = nearest_points(hotspot_point, canal_union)
                network_distance_deg = hotspot_point.distance(nearest_canal_pt)
                network_distance_m = network_distance_deg * 111_000.0
                if network_distance_m < MIN_NETWORK_DISTANCE_M or network_distance_m > MAX_NETWORK_DISTANCE_M:
                    continue
                hotspot_rows.append(
                    {
                        "zone": zone,
                        "hotspot_point": hotspot_point,
                        "nearest_canal_point": nearest_canal_pt,
                        "max_flow_acc": round(max_value, 2),
                        "network_distance_m": round(network_distance_m, 2),
                    }
                )
    except Exception:
        return []

    if not hotspot_rows:
        return []

    max_values = [row["max_flow_acc"] for row in hotspot_rows]
    threshold = float(np.percentile(max_values, FLOW_ACC_HOTSPOT_THRESHOLD_PERCENTILE))
    filtered_rows = [row for row in hotspot_rows if row["max_flow_acc"] >= threshold]
    if not filtered_rows:
        filtered_rows = hotspot_rows

    filtered_rows.sort(
        key=lambda row: (
            -row["max_flow_acc"],
            row["network_distance_m"],
        )
    )

    candidates: list[dict[str, Any]] = []
    for row in filtered_rows:
        zone = row["zone"]
        hotspot_point = row["hotspot_point"]
        nearest_canal_pt = row["nearest_canal_point"]
        flow_score = min(max(row["max_flow_acc"] / 5000.0, 0.0), 1.0) * 100.0
        distance_score = min(max(row["network_distance_m"] / 40.0, 0.0), 100.0)
        priority_score = round((flow_score * 0.7) + (distance_score * 0.3), 2)
        candidates.append(
            {
                "candidate_id": f"{zone['id']}::flowacc::network",
                "candidate_type": "flowacc_hotspot_to_network",
                "source_zone_id": zone["id"],
                "source_zone_name": zone["nombre"],
                "target_zone_id": "network",
                "target_zone_name": "Red existente",
                "from_lon": float(hotspot_point.x),
                "from_lat": float(hotspot_point.y),
                "to_lon": float(nearest_canal_pt.x),
                "to_lat": float(nearest_canal_pt.y),
                "zone_pair_distance_deg": round(
                    _distance(
                        (float(hotspot_point.x), float(hotspot_point.y)),
                        (float(nearest_canal_pt.x), float(nearest_canal_pt.y)),
                    ),
                    6,
                ),
                "network_distance_m": row["network_distance_m"],
                "priority_score": priority_score,
                "reason": (
                    f"Descargar hotspot de escorrentía en {zone['nombre']} "
                    f"hacia la red existente más cercana "
                    f"(flow_acc={row['max_flow_acc']:.0f})"
                ),
            }
        )
        if len(candidates) >= max_candidates:
            break
    return candidates


def _build_distance_fallback_candidates(
    zones: list[dict[str, Any]],
    *,
    max_candidates: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    ranked = sorted(
        zones,
        key=lambda zone: float(zone.get("distance_to_network_m") or 0.0),
        reverse=True,
    )
    for zone in ranked:
        network_point = zone.get("nearest_network_point") or {}
        network_coords = tuple(network_point.get("coordinates") or [])
        network_distance_m = float(zone.get("distance_to_network_m") or 0.0)
        source_coords = tuple(zone.get("point", {}).get("coordinates") or [])
        if len(network_coords) != 2 or len(source_coords) != 2:
            continue
        if network_distance_m < 150.0 or network_distance_m > MAX_NETWORK_DISTANCE_M:
            continue
        priority_score = round(min(network_distance_m * DISTANCE_ONLY_PRIORITY_SCALE, 60.0), 2)
        candidates.append(
            {
                "candidate_id": f"{zone['id']}::distance::network",
                "candidate_type": "distance_to_network",
                "source_zone_id": zone["id"],
                "source_zone_name": zone["nombre"],
                "target_zone_id": "network",
                "target_zone_name": "Red existente",
                "from_lon": source_coords[0],
                "from_lat": source_coords[1],
                "to_lon": network_coords[0],
                "to_lat": network_coords[1],
                "zone_pair_distance_deg": round(_distance(source_coords, network_coords), 6),
                "network_distance_m": round(network_distance_m, 2),
                "priority_score": priority_score,
                "reason": (
                    f"Descargar {zone['nombre']} hacia la red existente más cercana "
                    f"por aislamiento territorial ({network_distance_m:.0f} m)"
                ),
            }
        )
        if len(candidates) >= max_candidates:
            break
    return candidates


def generate_auto_corridor_candidates(
    zones: list[dict[str, Any]],
    *,
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Create automatic candidate routes from actionable zones into the existing network."""
    ranked = sorted(zones, key=lambda item: item["priority_score"], reverse=True)
    proposals: list[dict[str, Any]] = []
    limit = max(max_candidates * 3, max_candidates)

    anchor_zone = next((zone for zone in ranked if zone.get("anchor")), None)
    actionable = [zone for zone in ranked if _zone_is_actionable(zone)]
    # Fallback: if no zone has computed HCI/flood/risk data (all priority scores are 0),
    # treat every zone as actionable. Without this, the analyzer produces zero proposals
    # whenever the intelligence pipeline has not yet been run for this area.
    if not actionable:
        actionable = list(ranked)
    if anchor_zone and anchor_zone not in actionable:
        actionable.insert(0, anchor_zone)

    if anchor_zone:
        anchor_coords = tuple(anchor_zone["point"]["coordinates"])
        actionable.sort(
            key=lambda zone: (
                0 if zone["id"] == anchor_zone["id"] else 1,
                _distance(anchor_coords, tuple(zone["point"]["coordinates"])),
                -zone["priority_score"],
            )
        )

    for source in actionable:
        source_coords = tuple(source["point"]["coordinates"])
        network_point = source.get("nearest_network_point") or {}
        network_coords = tuple(network_point.get("coordinates") or [])
        network_distance_m = float(source.get("distance_to_network_m") or 0.0)
        if len(network_coords) != 2:
            continue
        if network_distance_m < MIN_NETWORK_DISTANCE_M or network_distance_m > MAX_NETWORK_DISTANCE_M:
            continue

        proposals.append(
            {
                "candidate_id": f"{source['id']}::network",
                "candidate_type": "zone_to_network",
                "source_zone_id": source["id"],
                "source_zone_name": source["nombre"],
                "target_zone_id": "network",
                "target_zone_name": "Red existente",
                "from_lon": source_coords[0],
                "from_lat": source_coords[1],
                "to_lon": network_coords[0],
                "to_lat": network_coords[1],
                "zone_pair_distance_deg": round(_distance(source_coords, network_coords), 6),
                "network_distance_m": round(network_distance_m, 2),
                "priority_score": round(float(source["priority_score"] or 0), 2),
                "reason": (
                    f"Descargar {source['nombre']} ({source['risk_level']}) "
                    f"hacia la red existente más cercana en {source['cuenca']}"
                ),
            }
        )
        if len(proposals) >= limit:
            break
    return proposals


def _is_routable(result: dict[str, Any]) -> bool:
    return bool(
        result.get("summary", {}).get("edges")
        and (result.get("centerline", {}).get("features") or [])
    )


def _centerline_overlap_metrics(db: Session, result: dict[str, Any]) -> dict[str, float]:
    centerline = result.get("centerline", {})
    features = centerline.get("features") or []
    if not features:
        return {"existing_network_overlap_m": 0.0, "overlap_ratio": 0.0}

    geometries = [
        feature.get("geometry")
        for feature in features
        if isinstance(feature, dict) and feature.get("geometry")
    ]
    if not geometries:
        return {"existing_network_overlap_m": 0.0, "overlap_ratio": 0.0}

    geom_collection = {"type": "GeometryCollection", "geometries": geometries}
    row = db.execute(
        text(
            """
            WITH route AS (
                SELECT ST_Transform(
                    ST_SetSRID(ST_GeomFromGeoJSON(:route_geom), 4326),
                    32720
                ) AS geom
            ),
            network AS (
                SELECT ST_Union(ST_Transform(cn.geom, 32720)) AS geom
                FROM canal_network cn
                WHERE cn.geom IS NOT NULL
            )
            SELECT
                COALESCE(ST_Length(route.geom), 0) AS route_length_m,
                COALESCE(ST_Length(ST_Intersection(route.geom, network.geom)), 0) AS overlap_length_m
            FROM route, network
            """
        ),
        {"route_geom": json.dumps(geom_collection)},
    ).mappings().first()

    route_length_m = float(row["route_length_m"] or 0.0) if row else 0.0
    overlap_length_m = float(row["overlap_length_m"] or 0.0) if row else 0.0
    overlap_ratio = round(overlap_length_m / route_length_m, 4) if route_length_m > 0 else 0.0
    return {
        "existing_network_overlap_m": round(overlap_length_m, 2),
        "overlap_ratio": overlap_ratio,
    }


def _score_candidate(
    candidate: dict[str, Any],
    result: dict[str, Any],
    *,
    routed: bool,
) -> tuple[float, dict[str, Any]]:
    summary = result.get("summary", {})
    breakdown = summary.get("cost_breakdown", {})
    if not routed:
        return 0.0, {
            "status": "unroutable",
            "priority_score": candidate["priority_score"],
            "explanation": "No se encontró una ruta útil sobre el ámbito seleccionado.",
        }

    distance_m = float(summary.get("total_distance_m") or 0.0)
    if distance_m <= 0:
        return 0.0, {
            "status": "unroutable",
            "priority_score": candidate["priority_score"],
            "explanation": "La ruta calculada no devolvió una distancia válida para evaluar la sugerencia.",
        }
    distance_score = max(0.0, 100.0 - min(distance_m / 40.0, 100.0))
    profile_factor = float(breakdown.get("avg_profile_factor") or 1.0)
    profile_score = max(0.0, 100.0 - ((profile_factor - 1.0) * 100.0))
    hydric_score = float(breakdown.get("avg_hydric_index") or candidate["priority_score"])
    total_score = round(
        (candidate["priority_score"] * 0.45)
        + (distance_score * 0.3)
        + (profile_score * 0.15)
        + (hydric_score * 0.1),
        2,
    )
    return total_score, {
        "status": "routed",
        "priority_score": candidate["priority_score"],
        "distance_score": round(distance_score, 2),
        "profile_score": round(profile_score, 2),
        "hydric_score": round(hydric_score, 2),
        "route_distance_m": round(distance_m, 2),
        "avg_profile_factor": profile_factor,
        "avg_hydric_index": breakdown.get("avg_hydric_index"),
        "parcel_intersections": breakdown.get("parcel_intersections", 0),
        "near_parcels": breakdown.get("near_parcels", 0),
        "existing_network_overlap_m": breakdown.get("existing_network_overlap_m", 0.0),
        "overlap_ratio": breakdown.get("overlap_ratio", 0.0),
        "explanation": candidate["reason"],
    }


def auto_analyze_corridors(
    db: Session,
    *,
    scope_type: ScopeType,
    scope_id: str | None,
    point_lon: float | None = None,
    point_lat: float | None = None,
    mode: Literal["network", "raster"],
    profile: Literal["balanceado", "hidraulico", "evitar_propiedad"],
    max_candidates: int,
    corridor_width_m: float | None = None,
    alternative_count: int | None = None,
    penalty_factor: float | None = None,
    weight_overrides: dict[str, float | None] | None = None,
    include_unroutable: bool = True,
) -> dict[str, Any]:
    zones = load_auto_analysis_zones(
        db,
        scope_type=scope_type,
        scope_id=scope_id,
        point_lon=point_lon,
        point_lat=point_lat,
    )
    proposals = generate_auto_corridor_candidates(zones, max_candidates=max_candidates)
    seen_ids = {proposal["candidate_id"] for proposal in proposals}
    for builder in (
        _build_suggestion_seed_candidates,
        _build_gap_seed_candidates,
        _build_flow_acc_hotspot_candidates,
        _build_distance_fallback_candidates,
    ):
        if len(proposals) >= max_candidates:
            break
        # _build_distance_fallback_candidates does not take a `db` argument
        if builder is _build_distance_fallback_candidates:
            fallback_candidates = builder(zones, max_candidates=max_candidates)
        else:
            fallback_candidates = builder(db, zones, max_candidates=max_candidates)
        for candidate in fallback_candidates:
            if candidate["candidate_id"] in seen_ids:
                continue
            proposals.append(candidate)
            seen_ids.add(candidate["candidate_id"])
            if len(proposals) >= max_candidates:
                break

    evaluated: list[dict[str, Any]] = []
    for proposal in proposals:
        routing_error: str | None = None
        try:
            routing_result = corridor_routing(
                db,
                from_lon=proposal["from_lon"],
                from_lat=proposal["from_lat"],
                to_lon=proposal["to_lon"],
                to_lat=proposal["to_lat"],
                profile=profile,
                mode=mode,
                area_id=scope_id,
                corridor_width_m=corridor_width_m,
                alternative_count=alternative_count,
                penalty_factor=penalty_factor,
                weight_overrides=weight_overrides,
            )
        except NotFoundError as exc:
            routing_error = str(exc)
            routing_result = {
                "summary": {
                    "mode": mode,
                    "profile": profile,
                    "total_distance_m": 0.0,
                    "edges": 0,
                    "cost_breakdown": {},
                },
                "centerline": {"type": "FeatureCollection", "features": []},
                "corridor": None,
                "alternatives": [],
            }
        routed = _is_routable(routing_result)
        overlap_metrics = _centerline_overlap_metrics(db, routing_result) if routed else {
            "existing_network_overlap_m": 0.0,
            "overlap_ratio": 0.0,
        }
        routing_result.setdefault("summary", {}).setdefault("cost_breakdown", {}).update(overlap_metrics)
        score, ranking_breakdown = _score_candidate(proposal, routing_result, routed=routed)
        if routing_error:
            ranking_breakdown["routing_error"] = routing_error
        if routed and overlap_metrics["overlap_ratio"] >= MAX_EXISTING_NETWORK_OVERLAP_RATIO:
            continue
        if routed and score <= 0:
            continue
        candidate = {
            **proposal,
            "status": "routed" if routed else "unroutable",
            "score": score,
            "ranking_breakdown": ranking_breakdown,
            "routing_result": routing_result,
        }
        if routed or include_unroutable:
            evaluated.append(candidate)

    evaluated.sort(
        key=lambda item: (
            0 if item["status"] == "routed" else 1,
            -item["score"],
            item["candidate_id"],
        )
    )
    ranked = evaluated[:max_candidates]
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index

    routed_count = sum(1 for item in evaluated if item["status"] == "routed")
    avg_score = round(
        sum(item["score"] for item in evaluated if item["status"] == "routed")
        / max(routed_count, 1),
        2,
    )
    return {
        "analysis_id": str(uuid.uuid4()),
        "scope": {
            "type": scope_type,
            "id": scope_id,
            "zone_count": len(zones),
            "point": [point_lon, point_lat] if point_lon is not None and point_lat is not None else None,
        },
        "summary": {
            "mode": mode,
            "profile": profile,
            "generated_candidates": len(proposals),
            "returned_candidates": len(ranked),
            "routed_candidates": routed_count,
            "unroutable_candidates": sum(
                1 for item in evaluated if item["status"] == "unroutable"
            ),
            "avg_score": avg_score,
            "max_score": max((item["score"] for item in ranked), default=0.0),
        },
        "candidates": ranked,
        "ranking": [item["candidate_id"] for item in ranked],
        "stats": {
            "critical_zones": sum(1 for zone in zones if zone["priority_score"] >= 70),
            "scope_zone_names": [zone["nombre"] for zone in zones[:10]],
        },
    }
