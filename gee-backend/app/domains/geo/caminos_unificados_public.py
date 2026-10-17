"""Public map projection: one geometry per route, padrón left intact.

``red_vial`` stays one physical segment per row (cruces and relevamientos
reference those rows). The map reads ``vt_caminos_unificados``, which is
``mv_caminos_unificados`` grouped by ``rtn``. A route that crosses more than
one consorcio is painted with the color of the consorcio that owns the longer
share. Legend kilometres are the geodesic sum of the active padrón rows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.gee_service_layers_support import CONSORCIO_COLORS

PUBLIC_CAMINOS_SQL = """
SELECT json_build_object(
  'routes', COALESCE((
    SELECT json_agg(row_to_json(q) ORDER BY q.ruta)
    FROM (
      SELECT
        u.id,
        u.ruta,
        u.nombre,
        u.tipo_generico,
        u.red,
        u.consorcios,
        u.longitud_geodesica_km,
        u.cantidad_tramos_fisicos,
        COALESCE(d.ccn, 'Sin consorcio') AS ccn,
        COALESCE(d.ccc, '') AS ccc,
        ST_AsGeoJSON(u.geom)::json AS geometry
      FROM vt_caminos_unificados u
      LEFT JOIN LATERAL (
        SELECT
          COALESCE(NULLIF(btrim(ccn), ''), 'Sin consorcio') AS ccn,
          COALESCE(NULLIF(btrim(ccc), ''), '') AS ccc
        FROM red_vial r
        WHERE r.activo IS TRUE
          AND r.rtn = u.ruta
        GROUP BY 1, 2
        ORDER BY sum(ST_Length(r.geom::geography)) DESC NULLS LAST, 1
        LIMIT 1
      ) d ON TRUE
      WHERE u.geom IS NOT NULL
    ) q
  ), '[]'::json),
  'legend', COALESCE((
    SELECT json_agg(row_to_json(legend_row) ORDER BY legend_row.ccn)
    FROM (
      SELECT
        COALESCE(NULLIF(btrim(ccn), ''), 'Sin consorcio') AS ccn,
        COALESCE(NULLIF(btrim(min(ccc)), ''), '') AS ccc,
        count(*)::int AS tramos,
        round((sum(ST_Length(geom::geography)) / 1000.0)::numeric, 2) AS km
      FROM red_vial
      WHERE activo IS TRUE
      GROUP BY COALESCE(NULLIF(btrim(ccn), ''), 'Sin consorcio')
    ) legend_row
  ), '[]'::json)
)
"""

_LINE_TYPES = frozenset({"LineString", "MultiLineString"})


def load_public_caminos_unificados(db: Session) -> dict[str, Any]:
    """One feature per ``rtn``. Rolls the session back when the view is missing."""
    try:
        payload = db.execute(text(PUBLIC_CAMINOS_SQL)).scalar_one()
    except Exception:
        db.rollback()
        raise
    return assemble_public_caminos(payload, CONSORCIO_COLORS)


def assemble_public_caminos(payload: Any, colors: list[str]) -> dict[str, Any]:
    """Turn the SQL payload into the colored-roads envelope the map already reads."""
    body = payload if isinstance(payload, dict) else {}
    routes = _mappings(body.get("routes"))
    legend_rows = _mappings(body.get("legend"))
    names = sorted({str(row.get("ccn") or "Sin consorcio") for row in (*routes, *legend_rows)})
    color_map = (
        {name: colors[index % len(colors)] for index, name in enumerate(names)} if colors else {}
    )

    features: list[dict[str, Any]] = []
    for row in routes:
        geometry = row.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in _LINE_TYPES:
            continue
        ccn = str(row.get("ccn") or "Sin consorcio")
        ruta = row.get("ruta")
        nombre = row.get("nombre")
        features.append(
            {
                "type": "Feature",
                "id": row.get("id"),
                "geometry": geometry,
                "properties": {
                    "id": row.get("id"),
                    "rtn": ruta,
                    "ruta": ruta,
                    "fna": nombre,
                    "nombre": nombre,
                    "gna": row.get("tipo_generico"),
                    "red": row.get("red"),
                    "ccn": ccn,
                    "ccc": str(row.get("ccc") or ""),
                    "consorcios": row.get("consorcios"),
                    "longitud_geodesica_km": _number(row.get("longitud_geodesica_km")),
                    "cantidad_tramos_fisicos": row.get("cantidad_tramos_fisicos"),
                    "color": color_map.get(ccn, "#888888"),
                },
            }
        )

    consorcios: list[dict[str, Any]] = []
    for row in legend_rows:
        ccn = str(row.get("ccn") or "Sin consorcio")
        ccc = str(row.get("ccc") or "")
        consorcios.append(
            {
                "nombre": ccn,
                "codigo": ccc or ccn,
                "color": color_map.get(ccn, "#888888"),
                "tramos": int(row.get("tramos") or 0),
                "longitud_km": _number(row.get("km")) or 0.0,
            }
        )
    consorcios.sort(key=lambda item: str(item["nombre"]))
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "total_tramos": len(features),
            "total_consorcios": len(consorcios),
            "total_km": round(sum(float(item["longitud_km"]) for item in consorcios), 2),
        },
        "consorcios": consorcios,
    }


def _mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number
