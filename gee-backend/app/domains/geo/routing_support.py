"""Support helpers for corridor routing profiles and network analytics."""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

RoutingProfileName = Literal["balanceado", "hidraulico", "evitar_propiedad"]

ROUTING_PROFILE_DEFAULTS: dict[RoutingProfileName, dict[str, float | int]] = {
    "balanceado": {
        "corridor_width_m": 50.0,
        "alternative_count": 2,
        "penalty_factor": 3.0,
    },
    "hidraulico": {
        "corridor_width_m": 80.0,
        "alternative_count": 1,
        "penalty_factor": 2.0,
    },
    "evitar_propiedad": {
        "corridor_width_m": 40.0,
        "alternative_count": 3,
        "penalty_factor": 5.0,
    },
}


def resolve_routing_profile(
    profile: RoutingProfileName = "balanceado",
    *,
    corridor_width_m: float | None = None,
    alternative_count: int | None = None,
    penalty_factor: float | None = None,
) -> dict[str, float | int | str]:
    defaults = ROUTING_PROFILE_DEFAULTS[profile]
    return {
        "profile": profile,
        "corridor_width_m": float(
            corridor_width_m
            if corridor_width_m is not None
            else defaults["corridor_width_m"]
        ),
        "alternative_count": int(
            alternative_count
            if alternative_count is not None
            else defaults["alternative_count"]
        ),
        "penalty_factor": float(
            penalty_factor if penalty_factor is not None else defaults["penalty_factor"]
        ),
    }


def _load_property_edge_factors(db: Session) -> tuple[dict[int, float], dict[str, Any]]:
    try:
        rows = db.execute(
            text("""
                SELECT
                    cn.id AS edge_id,
                    COUNT(*) FILTER (
                        WHERE ST_Intersects(cn.geom, pc.geometria)
                    ) AS parcel_intersections,
                    COUNT(*) FILTER (
                        WHERE ST_DWithin(
                            ST_Transform(cn.geom, 32720),
                            ST_Transform(pc.geometria, 32720),
                            30
                        )
                    ) AS near_parcels
                FROM canal_network cn
                LEFT JOIN parcelas_catastro pc
                    ON ST_DWithin(
                        ST_Transform(cn.geom, 32720),
                        ST_Transform(pc.geometria, 32720),
                        30
                    )
                GROUP BY cn.id
            """)
        ).mappings()
        factors: dict[int, float] = {}
        total_intersections = 0
        total_near = 0

        for row in rows:
            intersections = int(row["parcel_intersections"] or 0)
            near_parcels = int(row["near_parcels"] or 0)
            factor = (
                1.0
                + min(intersections * 0.45, 1.5)
                + min(max(near_parcels - intersections, 0) * 0.1, 0.4)
            )
            if factor > 1.0:
                factors[int(row["edge_id"])] = round(factor, 4)
            total_intersections += intersections
            total_near += near_parcels

        return factors, {
            "parcel_intersections": total_intersections,
            "near_parcels": total_near,
        }
    except Exception:
        logger.warning("routing.property_edge_factors_failed", exc_info=True)
        return {}, {"parcel_intersections": 0, "near_parcels": 0}


def _load_hydraulic_edge_factors(
    db: Session,
) -> tuple[dict[int, float], dict[str, Any]]:
    try:
        rows = db.execute(
            text("""
                WITH latest_hci AS (
                    SELECT ih.zona_id, ih.indice_final
                    FROM indices_hidricos ih
                    JOIN (
                        SELECT zona_id, MAX(fecha_calculo) AS max_fecha
                        FROM indices_hidricos
                        GROUP BY zona_id
                    ) latest
                      ON latest.zona_id = ih.zona_id
                     AND latest.max_fecha = ih.fecha_calculo
                )
                SELECT
                    cn.id AS edge_id,
                    AVG(latest_hci.indice_final) AS avg_hci
                FROM canal_network cn
                LEFT JOIN zonas_operativas zo
                    ON ST_Intersects(cn.geom, zo.geometria)
                LEFT JOIN latest_hci
                    ON latest_hci.zona_id = zo.id
                GROUP BY cn.id
            """)
        ).mappings()
        factors: dict[int, float] = {}
        hci_values: list[float] = []

        for row in rows:
            avg_hci = float(row["avg_hci"]) if row["avg_hci"] is not None else None
            if avg_hci is None:
                continue
            hci_values.append(avg_hci)
            factor = max(0.72, 1.0 - min(avg_hci, 100.0) / 250.0)
            if factor != 1.0:
                factors[int(row["edge_id"])] = round(factor, 4)

        return factors, {
            "avg_hydric_index": round(sum(hci_values) / len(hci_values), 2)
            if hci_values
            else None,
            "hydraulic_edge_count": len(hci_values),
        }
    except Exception:
        logger.warning("routing.hydraulic_edge_factors_failed", exc_info=True)
        return {}, {"avg_hydric_index": None, "hydraulic_edge_count": 0}


def _blend_factor(base: float, target: float, weight: float) -> float:
    return round(base + (target - base) * weight, 4)


def resolve_profile_edge_factors(
    db: Session, profile: RoutingProfileName
) -> tuple[dict[int, float], dict[str, Any]]:
    property_factors, property_meta = _load_property_edge_factors(db)
    hydraulic_factors, hydraulic_meta = _load_hydraulic_edge_factors(db)
    edge_ids = set(property_factors) | set(hydraulic_factors)
    factors: dict[int, float] = {}

    for edge_id in edge_ids:
        property_factor = property_factors.get(edge_id, 1.0)
        hydraulic_factor = hydraulic_factors.get(edge_id, 1.0)

        if profile == "hidraulico":
            factor = hydraulic_factor
        elif profile == "evitar_propiedad":
            factor = property_factor
        else:
            factor = _blend_factor(1.0, property_factor, 0.45) * _blend_factor(
                1.0, hydraulic_factor, 0.55
            )

        if factor != 1.0:
            factors[edge_id] = round(factor, 4)

    return factors, {
        "profile": profile,
        **property_meta,
        **hydraulic_meta,
        "profile_edge_count": len(factors),
    }


def merge_edge_factors(*factor_maps: dict[int, float]) -> dict[int, float]:
    merged: dict[int, float] = {}
    for factor_map in factor_maps:
        for edge_id, factor in factor_map.items():
            merged[edge_id] = round(merged.get(edge_id, 1.0) * factor, 4)
    return merged


def summarize_profile_breakdown(
    route: list[dict[str, Any]],
    profile: RoutingProfileName,
    profile_factors: dict[int, float],
    profile_meta: dict[str, Any],
) -> dict[str, Any]:
    route_edge_ids = [
        int(edge["edge"]) for edge in route if edge.get("edge") is not None
    ]
    route_factors = [profile_factors.get(edge_id, 1.0) for edge_id in route_edge_ids]

    return {
        "profile": profile,
        "edge_count_with_profile_factor": sum(
            1 for factor in route_factors if factor != 1.0
        ),
        "avg_profile_factor": round(sum(route_factors) / len(route_factors), 4)
        if route_factors
        else 1.0,
        "max_profile_factor": round(max(route_factors), 4) if route_factors else 1.0,
        "min_profile_factor": round(min(route_factors), 4) if route_factors else 1.0,
        **profile_meta,
    }


def build_corridor_export_feature_collection(
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []

    centerline = result_payload.get("centerline") or {}
    for feature in centerline.get("features", []):
        features.append(
            {
                **feature,
                "properties": {
                    **(feature.get("properties") or {}),
                    "route_role": "centerline",
                },
            }
        )

    corridor = result_payload.get("corridor")
    if corridor and corridor.get("type") == "Feature":
        features.append(
            {
                **corridor,
                "properties": {
                    **(corridor.get("properties") or {}),
                    "route_role": "corridor",
                },
            }
        )

    for alternative in result_payload.get("alternatives", []):
        for feature in (alternative.get("geojson") or {}).get("features", []):
            features.append(
                {
                    **feature,
                    "properties": {
                        **(feature.get("properties") or {}),
                        "route_role": "alternative",
                        "alternative_rank": alternative.get("rank"),
                    },
                }
            )

    return {"type": "FeatureCollection", "features": features}


def get_network_stats(db: Session) -> dict[str, Any]:
    stats = {}
    stats["total_edges"] = db.execute(
        text("SELECT count(*) FROM canal_network;")
    ).scalar()
    stats["total_vertices"] = (
        db.execute(text("SELECT count(*) FROM canal_network_vertices_pgr;")).scalar()
        or 0
    )
    stats["total_length_km"] = (
        db.execute(
            text("""
            SELECT ROUND((SUM(ST_Length(ST_Transform(geom, 32720))) / 1000)::numeric, 2)
            FROM canal_network WHERE geom IS NOT NULL;
        """)
        ).scalar()
        or 0
    )
    stats["types"] = [
        {"tipo": r[0], "count": r[1]}
        for r in db.execute(
            text(
                "SELECT tipo, count(*) FROM canal_network GROUP BY tipo ORDER BY count DESC;"
            )
        ).fetchall()
    ]
    return stats


def betweenness_centrality(
    db: Session,
    limit: int = 100,
    timeout_seconds: int = 120,
) -> list[dict[str, Any]]:
    try:
        return _betweenness_via_pgrouting(db, limit, timeout_seconds)
    except Exception as exc:
        logger.warning(
            "pgr_betweennessCentrality not available (%s), falling back to NetworkX",
            exc,
        )
        return _betweenness_via_networkx(db, limit)


def _betweenness_via_pgrouting(
    db: Session,
    limit: int,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    db.execute(text(f"SET LOCAL statement_timeout = '{timeout_seconds}s';"))
    rows = db.execute(
        text("""
            SELECT
                bc.vid AS node_id,
                bc.centrality,
                ST_AsGeoJSON(v.the_geom)::json AS geometry
            FROM pgr_betweennessCentrality(
                'SELECT id, source, target, cost FROM canal_network',
                directed := false
            ) AS bc
            JOIN canal_network_vertices_pgr v ON v.id = bc.vid
            ORDER BY bc.centrality DESC
            LIMIT :lim;
        """),
        {"lim": limit},
    ).fetchall()
    return [
        {
            "node_id": r.node_id,
            "centrality": round(float(r.centrality), 6),
            "geometry": r.geometry,
        }
        for r in rows
    ]


def _betweenness_via_networkx(
    db: Session,
    limit: int,
) -> list[dict[str, Any]]:
    import networkx as nx

    edges = db.execute(
        text("""
            SELECT id, source, target, cost
            FROM canal_network
            WHERE source IS NOT NULL AND target IS NOT NULL;
        """)
    ).fetchall()

    if not edges:
        return []

    graph = nx.Graph()
    for edge in edges:
        graph.add_edge(edge.source, edge.target, weight=edge.cost, edge_id=edge.id)

    centrality = nx.betweenness_centrality(graph, weight="weight")
    sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:limit]
    node_ids = [node_id for node_id, _ in sorted_nodes]
    if not node_ids:
        return []

    vertices = db.execute(
        text("""
            SELECT id, ST_AsGeoJSON(the_geom)::json AS geometry
            FROM canal_network_vertices_pgr
            WHERE id = ANY(:ids);
        """),
        {"ids": node_ids},
    ).fetchall()
    geom_map = {vertex.id: vertex.geometry for vertex in vertices}

    return [
        {
            "node_id": node_id,
            "centrality": round(float(score), 6),
            "geometry": geom_map.get(node_id),
        }
        for node_id, score in sorted_nodes
    ]
