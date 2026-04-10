"""
pgRouting service for canal network analysis.

Provides shortest path, betweenness centrality, and flood propagation
analysis on the canal network graph stored in PostGIS.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.domains.geo.routing_raster_support import (
    build_raster_route_feature_collection,
    raster_corridor_routing,
)
from app.domains.geo.routing_support import (
    RoutingProfileName,
    build_corridor_export_feature_collection as _build_corridor_export_feature_collection,
    merge_edge_factors,
    resolve_profile_edge_factors,
    resolve_routing_profile,
    summarize_profile_breakdown,
)

logger = logging.getLogger(__name__)


def build_corridor_export_feature_collection(
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    return _build_corridor_export_feature_collection(result_payload)


def import_canals_from_geojson(
    db: Session, geojson_path: str, tipo: str = "canal"
) -> int:
    """Import canal LineStrings from a GeoJSON file into canal_network table.

    Args:
        db: Database session.
        geojson_path: Path to the GeoJSON file.
        tipo: Type label for the imported canals.

    Returns:
        Number of features imported.
    """
    path = Path(geojson_path)
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    data = json.loads(path.read_text())
    features = data.get("features", [])

    count = 0
    for feat in features:
        geom_type = feat["geometry"]["type"]
        if geom_type not in ("LineString", "MultiLineString"):
            continue

        props = feat.get("properties", {})
        nombre = props.get("name") or props.get("nombre") or props.get("NAME") or tipo
        geom_json = json.dumps(feat["geometry"])

        db.execute(
            text("""
                INSERT INTO canal_network (nombre, tipo, geom, cost, reverse_cost)
                VALUES (
                    :nombre,
                    :tipo,
                    ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326),
                    ST_Length(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326), 32720)),
                    ST_Length(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326), 32720))
                )
            """),
            {"nombre": nombre, "tipo": tipo, "geom": geom_json},
        )
        count += 1

    db.commit()
    return count


def build_topology(db: Session, tolerance: float = 0.0001) -> dict[str, Any]:
    """Build pgRouting topology from canal_network edges.

    Must be called after importing canals. Creates the vertices table
    and populates source/target columns.

    Args:
        db: Database session.
        tolerance: Snapping tolerance for connecting edges.

    Returns:
        Dict with vertex_count and edge_count.
    """
    # pgr_createTopology requires the_geom column name
    # We need to copy geom to the_geom or use geom directly
    db.execute(text("UPDATE canal_network SET the_geom = geom WHERE the_geom IS NULL;"))
    db.commit()

    db.execute(
        text("SELECT pgr_createTopology('canal_network', :tol, 'the_geom', 'id');"),
        {"tol": tolerance},
    )
    db.commit()

    vertex_count = db.execute(
        text("SELECT count(*) FROM canal_network_vertices_pgr;")
    ).scalar()
    edge_count = db.execute(
        text("SELECT count(*) FROM canal_network WHERE source IS NOT NULL;")
    ).scalar()

    return {"vertex_count": vertex_count, "edge_count": edge_count}


def shortest_path(
    db: Session,
    source_id: int,
    target_id: int,
) -> list[dict[str, Any]]:
    """Find shortest path between two nodes using Dijkstra.

    Args:
        db: Database session.
        source_id: Source vertex ID.
        target_id: Target vertex ID.

    Returns:
        List of edges in the path with geometry.
    """
    rows = db.execute(
        text("""
            SELECT
                d.seq,
                d.path_seq,
                d.node,
                d.edge,
                d.cost,
                d.agg_cost,
                ST_AsGeoJSON(cn.geom)::json AS geometry,
                cn.nombre
            FROM pgr_dijkstra(
                'SELECT id, source, target, cost, reverse_cost FROM canal_network',
                :source,
                :target,
                directed := false
            ) AS d
            LEFT JOIN canal_network cn ON d.edge = cn.id
            WHERE d.edge > 0
            ORDER BY d.path_seq;
        """),
        {"source": source_id, "target": target_id},
    ).fetchall()

    return [
        {
            "seq": r.seq,
            "path_seq": r.path_seq,
            "node": r.node,
            "edge": r.edge,
            "cost": round(r.cost, 2),
            "agg_cost": round(r.agg_cost, 2),
            "geometry": r.geometry,
            "nombre": r.nombre,
        }
        for r in rows
    ]


def shortest_path_with_penalties(
    db: Session,
    source_id: int,
    target_id: int,
    edge_penalties: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    """Find shortest path applying optional cost multipliers to specific edges."""
    edge_penalties = edge_penalties or {}

    rows = db.execute(
        text("""
            SELECT
                d.seq,
                d.path_seq,
                d.node,
                d.edge,
                d.cost,
                d.agg_cost,
                ST_AsGeoJSON(cn.geom)::json AS geometry,
                cn.nombre
            FROM pgr_dijkstra(
                $$
                SELECT
                    id,
                    source,
                    target,
                    cost * COALESCE(:penalties ->> id::text, '1')::double precision AS cost,
                    reverse_cost * COALESCE(:penalties ->> id::text, '1')::double precision AS reverse_cost
                FROM canal_network
                $$,
                :source,
                :target,
                directed := false
            ) AS d
            LEFT JOIN canal_network cn ON d.edge = cn.id
            WHERE d.edge > 0
            ORDER BY d.path_seq;
        """),
        {
            "source": source_id,
            "target": target_id,
            "penalties": json.dumps({str(k): v for k, v in edge_penalties.items()}),
        },
    ).fetchall()

    return [
        {
            "seq": r.seq,
            "path_seq": r.path_seq,
            "node": r.node,
            "edge": r.edge,
            "cost": round(r.cost, 2),
            "agg_cost": round(r.agg_cost, 2),
            "geometry": r.geometry,
            "nombre": r.nombre,
        }
        for r in rows
    ]


def build_route_feature_collection(route: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a GeoJSON FeatureCollection for a route."""
    features = []
    for edge in route:
        geometry = edge.get("geometry")
        if not geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "edge_id": edge.get("edge"),
                    "nombre": edge.get("nombre"),
                    "cost": edge.get("cost"),
                    "agg_cost": edge.get("agg_cost"),
                    "path_seq": edge.get("path_seq"),
                },
                "geometry": geometry,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def build_corridor_polygon(
    route: list[dict[str, Any]], width_m: float
) -> dict[str, Any] | None:
    """Build a corridor polygon as a buffer around the merged route geometry."""
    lines = [
        shape(edge["geometry"])
        for edge in route
        if edge.get("geometry") and edge["geometry"].get("type") == "LineString"
    ]
    if not lines:
        return None

    merged = unary_union(lines)
    width_deg = max(width_m / 111_320, 1e-6)
    corridor = merged.buffer(width_deg)
    return {
        "type": "Feature",
        "properties": {
            "corridor_width_m": width_m,
            "edge_ids": [
                edge.get("edge") for edge in route if edge.get("edge") is not None
            ],
        },
        "geometry": mapping(corridor),
    }


def summarize_route(route: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a route for API responses."""
    total_distance = route[-1]["agg_cost"] if route else 0.0
    return {
        "total_distance_m": round(float(total_distance), 2),
        "edges": len(route),
        "edge_ids": [
            edge.get("edge") for edge in route if edge.get("edge") is not None
        ],
    }


def compute_route_alternatives(
    db: Session,
    source_id: int,
    target_id: int,
    *,
    base_route: list[dict[str, Any]],
    alternative_count: int,
    penalty_factor: float,
    base_edge_factors: dict[int, float] | None = None,
) -> list[list[dict[str, Any]]]:
    """Compute alternative routes by penalizing previously used edges."""
    alternatives: list[list[dict[str, Any]]] = []
    used_edge_ids = {
        edge["edge"] for edge in base_route if edge.get("edge") is not None
    }
    base_edge_factors = base_edge_factors or {}

    for _ in range(max(alternative_count, 0)):
        penalties = {edge_id: penalty_factor for edge_id in used_edge_ids}
        route = shortest_path_with_penalties(
            db,
            source_id,
            target_id,
            merge_edge_factors(base_edge_factors, penalties),
        )
        route_edge_ids = {
            edge["edge"] for edge in route if edge.get("edge") is not None
        }
        if not route or not route_edge_ids or route_edge_ids == used_edge_ids:
            break
        alternatives.append(route)
        used_edge_ids.update(route_edge_ids)

    return alternatives


def corridor_routing(
    db: Session,
    *,
    from_lon: float,
    from_lat: float,
    to_lon: float,
    to_lat: float,
    profile: RoutingProfileName = "balanceado",
    mode: str = "network",
    area_id: str | None = None,
    corridor_width_m: float | None = None,
    alternative_count: int | None = None,
    penalty_factor: float | None = None,
    weight_overrides: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Compute a network or raster corridor routing response."""
    resolved = resolve_routing_profile(
        profile,
        corridor_width_m=corridor_width_m,
        alternative_count=alternative_count,
        penalty_factor=penalty_factor,
    )

    if mode == "raster":
        raster_result = raster_corridor_routing(
            db,
            from_lon=from_lon,
            from_lat=from_lat,
            to_lon=to_lon,
            to_lat=to_lat,
            profile=profile,
            corridor_width_m=float(resolved["corridor_width_m"]),
            area_id=area_id,
            weight_overrides=weight_overrides,
        )
        pseudo_route = [
            {
                "edge": None,
                "path_seq": 1,
                "cost": raster_result["total_distance_m"],
                "agg_cost": raster_result["total_distance_m"],
                "nombre": "Raster corridor path",
                "geometry": mapping(raster_result["line"]),
            }
        ]
        return {
            "source": {
                "id": "raster-source",
                "geometry": {"type": "Point", "coordinates": [from_lon, from_lat]},
            },
            "target": {
                "id": "raster-target",
                "geometry": {"type": "Point", "coordinates": [to_lon, to_lat]},
            },
            "summary": {
                "mode": "raster",
                "profile": resolved["profile"],
                "total_distance_m": raster_result["total_distance_m"],
                "edges": 1,
                "corridor_width_m": resolved["corridor_width_m"],
                "penalty_factor": resolved["penalty_factor"],
                "cost_breakdown": {
                    "profile": profile,
                    **raster_result["cost_meta"],
                },
            },
            "centerline": build_raster_route_feature_collection(raster_result["line"]),
            "corridor": build_corridor_polygon(
                pseudo_route, float(resolved["corridor_width_m"])
            ),
            "alternatives": [],
        }

    source = find_nearest_vertex(db, from_lon, from_lat)
    target = find_nearest_vertex(db, to_lon, to_lat)

    if not source or not target:
        raise NotFoundError("No vertices found near the given coordinates")

    profile_factors, profile_meta = resolve_profile_edge_factors(db, profile)
    base_route = shortest_path_with_penalties(
        db,
        source["id"],
        target["id"],
        edge_penalties=profile_factors,
    )
    centerline = build_route_feature_collection(base_route)
    corridor = build_corridor_polygon(base_route, float(resolved["corridor_width_m"]))
    summary = summarize_route(base_route) | {
        "mode": "network",
        "profile": resolved["profile"],
        "corridor_width_m": resolved["corridor_width_m"],
        "penalty_factor": resolved["penalty_factor"],
        "cost_breakdown": summarize_profile_breakdown(
            base_route, profile, profile_factors, profile_meta
        ),
    }

    alternatives = []
    for rank, route in enumerate(
        compute_route_alternatives(
            db,
            source["id"],
            target["id"],
            base_route=base_route,
            alternative_count=int(resolved["alternative_count"]),
            penalty_factor=float(resolved["penalty_factor"]),
            base_edge_factors=profile_factors,
        ),
        start=1,
    ):
        route_summary = summarize_route(route)
        alternatives.append(
            {
                "rank": rank,
                **route_summary,
                "geojson": build_route_feature_collection(route),
            }
        )

    return {
        "source": source,
        "target": target,
        "summary": summary,
        "centerline": centerline,
        "corridor": corridor,
        "alternatives": alternatives,
    }


def find_nearest_vertex(db: Session, lon: float, lat: float) -> dict[str, Any] | None:
    """Find the nearest vertex in the canal network to a given coordinate.

    Args:
        db: Database session.
        lon: Longitude.
        lat: Latitude.

    Returns:
        Dict with vertex id and distance, or None.
    """
    row = db.execute(
        text("""
            SELECT
                id,
                ST_AsGeoJSON(the_geom)::json AS geometry,
                ST_Distance(
                    ST_Transform(the_geom, 32720),
                    ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 32720)
                ) AS distance_m
            FROM canal_network_vertices_pgr
            ORDER BY the_geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
            LIMIT 1;
        """),
        {"lon": lon, "lat": lat},
    ).first()

    if not row:
        return None

    return {
        "id": row.id,
        "geometry": row.geometry,
        "distance_m": round(row.distance_m, 2),
    }
