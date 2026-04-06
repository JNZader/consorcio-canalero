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

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def import_canals_from_geojson(db: Session, geojson_path: str, tipo: str = "canal") -> int:
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


def get_network_stats(db: Session) -> dict[str, Any]:
    """Get basic network statistics."""
    stats = {}

    stats["total_edges"] = db.execute(
        text("SELECT count(*) FROM canal_network;")
    ).scalar()

    stats["total_vertices"] = db.execute(
        text("SELECT count(*) FROM canal_network_vertices_pgr;")
    ).scalar() or 0

    stats["total_length_km"] = db.execute(
        text("""
            SELECT ROUND((SUM(ST_Length(ST_Transform(geom, 32720))) / 1000)::numeric, 2)
            FROM canal_network WHERE geom IS NOT NULL;
        """)
    ).scalar() or 0

    stats["types"] = [
        {"tipo": r[0], "count": r[1]}
        for r in db.execute(
            text("SELECT tipo, count(*) FROM canal_network GROUP BY tipo ORDER BY count DESC;")
        ).fetchall()
    ]

    return stats


def betweenness_centrality(
    db: Session,
    limit: int = 100,
    timeout_seconds: int = 120,
) -> list[dict[str, Any]]:
    """Compute betweenness centrality for the canal network graph.

    Tries pgr_betweennessCentrality first (requires pgRouting 3.4+).
    Falls back to NetworkX if pgRouting function is not available.

    Args:
        db: Database session.
        limit: Maximum number of top-ranked nodes to return.
        timeout_seconds: Statement timeout for the pgRouting query.

    Returns:
        List of dicts with node_id, centrality, and geometry,
        sorted descending by centrality.
    """
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
    """Betweenness centrality using pgRouting SQL extension."""
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
    """Betweenness centrality fallback using NetworkX in-memory graph."""
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

    G = nx.Graph()
    for e in edges:
        G.add_edge(e.source, e.target, weight=e.cost, edge_id=e.id)

    centrality = nx.betweenness_centrality(G, weight="weight")

    # Fetch vertex geometries for the top-N nodes
    sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:limit]
    node_ids = [n[0] for n in sorted_nodes]

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

    geom_map = {v.id: v.geometry for v in vertices}

    return [
        {
            "node_id": node_id,
            "centrality": round(float(score), 6),
            "geometry": geom_map.get(node_id),
        }
        for node_id, score in sorted_nodes
    ]


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
