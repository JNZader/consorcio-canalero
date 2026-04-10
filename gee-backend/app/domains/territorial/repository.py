"""Data-access layer for the territorial domain.

Reads from mv_suelos_por_zona and mv_canales_por_zona (pre-computed intersections).
Writes to suelos_catastro and canales_geo via TRUNCATE + bulk INSERT.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class TerritorialRepository:
    # ── Import ────────────────────────────────────────────────────────────────

    def import_suelos(self, db: Session, features: list[dict[str, Any]]) -> int:
        db.execute(text("TRUNCATE suelos_catastro"))
        count = 0
        for feat in features:
            props = feat.get("properties") or {}
            geom = feat.get("geometry")
            if not geom:
                continue
            db.execute(
                text("""
                    INSERT INTO suelos_catastro (simbolo, cap, ip, geometria)
                    VALUES (
                        :simbolo,
                        :cap,
                        :ip,
                        ST_Multi(ST_GeomFromGeoJSON(:geom_json))
                    )
                """),
                {
                    "simbolo": props.get("simbolo")
                    or props.get("SIMBOLO")
                    or "SIN_DATOS",
                    "cap": props.get("cap") or props.get("CAP"),
                    "ip": props.get("ip") or props.get("IP"),
                    "geom_json": json.dumps(geom),
                },
            )
            count += 1
        db.commit()
        return count

    def import_canales(self, db: Session, features: list[dict[str, Any]]) -> int:
        db.execute(text("TRUNCATE canales_geo"))
        count = 0
        for feat in features:
            props = feat.get("properties") or {}
            geom = feat.get("geometry")
            if not geom:
                continue
            db.execute(
                text("""
                    INSERT INTO canales_geo (nombre, tipo, geometria)
                    VALUES (
                        :nombre,
                        :tipo,
                        ST_Multi(ST_GeomFromGeoJSON(:geom_json))
                    )
                """),
                {
                    "nombre": props.get("name")
                    or props.get("nombre")
                    or props.get("NOMBRE"),
                    "tipo": props.get("tipo") or props.get("TIPO") or props.get("type"),
                    "geom_json": json.dumps(geom),
                },
            )
            count += 1
        db.commit()
        return count

    def import_caminos(self, db: Session, features: list[dict[str, Any]]) -> int:
        db.execute(text("TRUNCATE caminos_geo"))
        count = 0
        for feat in features:
            props = feat.get("properties") or {}
            geom = feat.get("geometry")
            if not geom:
                continue
            # GeoJSON may have consorcio fields (ccc/ccn from GEE) or just tipo
            db.execute(
                text("""
                    INSERT INTO caminos_geo (nombre, consorcio_codigo, consorcio_nombre, jerarquia, geometria)
                    VALUES (
                        :nombre,
                        :consorcio_codigo,
                        :consorcio_nombre,
                        :jerarquia,
                        ST_Multi(ST_GeomFromGeoJSON(:geom_json))
                    )
                """),
                {
                    "nombre": props.get("nombre")
                    or props.get("NOMBRE")
                    or props.get("name"),
                    "consorcio_codigo": props.get("ccc")
                    or props.get("consorcio_codigo"),
                    "consorcio_nombre": props.get("ccn")
                    or props.get("consorcio_nombre"),
                    "jerarquia": props.get("jerarquia")
                    or props.get("tipo")
                    or props.get("TIPO"),
                    "geom_json": json.dumps(geom),
                },
            )
            count += 1
        db.commit()
        return count

    def refresh_views(self, db: Session) -> None:
        """Re-compute materialized views after an import."""
        db.execute(text("REFRESH MATERIALIZED VIEW mv_suelos_por_zona"))
        db.execute(text("REFRESH MATERIALIZED VIEW mv_canales_por_zona"))
        db.commit()

    def refresh_caminos_view(self, db: Session) -> None:
        """Re-compute the caminos materialized view after import."""
        db.execute(text("REFRESH MATERIALIZED VIEW mv_caminos_por_zona"))
        db.commit()

    # ── Report queries ────────────────────────────────────────────────────────

    def get_suelos_data(
        self,
        db: Session,
        scope: str,
        scope_value: str | None,
    ) -> list[dict[str, Any]]:
        """Return aggregated soil areas grouped by (simbolo, cap) for a scope."""
        if scope == "zona":
            where = "WHERE zona_id = CAST(:value AS UUID)"
            params: dict[str, Any] = {"value": scope_value}
        elif scope == "cuenca":
            where = "WHERE cuenca = :value"
            params = {"value": scope_value}
        else:
            where = ""
            params = {}

        rows = db.execute(
            text(f"""
                SELECT simbolo, cap, SUM(ha_suelo) AS ha
                FROM mv_suelos_por_zona
                {where}
                GROUP BY simbolo, cap
                ORDER BY ha DESC
            """),
            params,
        ).fetchall()

        return [{"simbolo": r.simbolo, "cap": r.cap, "ha": float(r.ha)} for r in rows]

    def get_km_canales(
        self,
        db: Session,
        scope: str,
        scope_value: str | None,
    ) -> float:
        """Return total km of canales for a scope."""
        if scope == "zona":
            where = "WHERE zona_id = CAST(:value AS UUID)"
            params: dict[str, Any] = {"value": scope_value}
        elif scope == "cuenca":
            where = "WHERE cuenca = :value"
            params = {"value": scope_value}
        else:
            where = ""
            params = {}

        result = db.execute(
            text(f"""
                SELECT COALESCE(SUM(km_canales), 0) AS km
                FROM mv_canales_por_zona
                {where}
            """),
            params,
        ).scalar()

        return float(result or 0)

    def get_km_caminos_por_consorcio(
        self,
        db: Session,
        scope: str,
        scope_value: str | None,
    ) -> list[dict[str, Any]]:
        """Return km of roads grouped by consorcio caminero for a scope."""
        if scope == "zona":
            where = "WHERE zona_id = CAST(:value AS UUID)"
            params: dict[str, Any] = {"value": scope_value}
        elif scope == "cuenca":
            where = "WHERE cuenca = :value"
            params = {"value": scope_value}
        else:
            where = ""
            params = {}

        try:
            rows = db.execute(
                text(f"""
                    SELECT consorcio_codigo, consorcio_nombre, SUM(km_caminos) AS km
                    FROM mv_caminos_por_zona
                    {where}
                    GROUP BY consorcio_codigo, consorcio_nombre
                    ORDER BY km DESC
                """),
                params,
            ).fetchall()
        except Exception:
            db.rollback()
            return []

        return [
            {
                "consorcio_codigo": r.consorcio_codigo or "",
                "consorcio_nombre": r.consorcio_nombre
                or r.consorcio_codigo
                or "Sin datos",
                "km": float(r.km),
            }
            for r in rows
        ]

    def has_caminos_data(self, db: Session) -> bool:
        try:
            count = db.execute(text("SELECT COUNT(*) FROM caminos_geo")).scalar()
            return int(count or 0) > 0
        except Exception:
            db.rollback()
            return False

    def get_zona_nombre(self, db: Session, zona_id: str) -> str | None:
        """Fetch the zona name from the materialized view (avoids extra join)."""
        row = db.execute(
            text(
                "SELECT zona_nombre FROM mv_suelos_por_zona WHERE zona_id = CAST(:id AS UUID) LIMIT 1"
            ),
            {"id": zona_id},
        ).fetchone()
        if row:
            return row.zona_nombre
        row = db.execute(
            text(
                "SELECT zona_nombre FROM mv_canales_por_zona WHERE zona_id = CAST(:id AS UUID) LIMIT 1"
            ),
            {"id": zona_id},
        ).fetchone()
        return row.zona_nombre if row else zona_id

    def get_cuencas(self, db: Session) -> list[str]:
        rows = db.execute(
            text("SELECT DISTINCT cuenca FROM mv_suelos_por_zona ORDER BY cuenca")
        ).fetchall()
        return [r.cuenca for r in rows]

    def has_suelos_data(self, db: Session) -> bool:
        count = db.execute(text("SELECT COUNT(*) FROM suelos_catastro")).scalar()
        return int(count or 0) > 0

    def has_canales_data(self, db: Session) -> bool:
        count = db.execute(text("SELECT COUNT(*) FROM canales_geo")).scalar()
        return int(count or 0) > 0
