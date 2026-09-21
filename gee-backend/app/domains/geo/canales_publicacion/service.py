"""Publication catalog over ``canal_consorcio``."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.canales_publicacion.schemas import (
    CanalPublicacionList,
    CanalPublicacionPatch,
    CanalPublicacionRow,
)

_SEED_SQL = text(
    """
    INSERT INTO canal_publicacion (canal_id, publicado, nombre_publico)
    SELECT c.id, TRUE, c.nombre FROM canal_consorcio c
    ON CONFLICT (canal_id) DO NOTHING
    """
)

_LIST_SQL = text(
    """
    SELECT c.id, c.estado, c.nombre AS nombre_interno,
           COALESCE(p.nombre_publico, c.nombre) AS nombre_publico,
           COALESCE(p.publicado, TRUE) AS publicado,
           c.longitud_m
    FROM canal_consorcio c
    LEFT JOIN canal_publicacion p ON p.canal_id = c.id
    ORDER BY c.estado, c.nombre
    """
)

_PATCH_SQL = text(
    """
    INSERT INTO canal_publicacion (canal_id, publicado, nombre_publico, updated_at)
    SELECT c.id,
           COALESCE(:publicado, TRUE),
           COALESCE(:nombre_publico, c.nombre),
           now()
    FROM canal_consorcio c
    WHERE c.id = :canal_id
    ON CONFLICT (canal_id) DO UPDATE SET
        publicado = COALESCE(:publicado, canal_publicacion.publicado),
        nombre_publico = COALESCE(:nombre_publico, canal_publicacion.nombre_publico),
        updated_at = now()
    RETURNING canal_id
    """
)

_PUBLIC_SQL = text(
    """
    SELECT c.id, c.estado, COALESCE(p.nombre_publico, c.nombre) AS nombre,
           c.longitud_m,
           ST_AsGeoJSON(c.geom) AS geom_json
    FROM canal_consorcio c
    JOIN canal_publicacion p ON p.canal_id = c.id
    WHERE p.publicado = TRUE
    """
)

_PUBLIC_FALLBACK_SQL = text(
    """
    SELECT c.id, c.estado, c.nombre,
           c.longitud_m,
           ST_AsGeoJSON(c.geom) AS geom_json
    FROM canal_consorcio c
    """
)

_HAS_PUBLICACION_SQL = text("SELECT EXISTS (SELECT 1 FROM canal_publicacion)")


class CanalPublicacionService:
    def list_staff(self, db: Session) -> CanalPublicacionList:
        db.execute(_SEED_SQL)
        rows = db.execute(_LIST_SQL).mappings().all()
        return CanalPublicacionList(
            items=[
                CanalPublicacionRow(
                    id=row["id"],
                    estado=row["estado"],
                    nombre_interno=row["nombre_interno"],
                    nombre_publico=row["nombre_publico"],
                    publicado=bool(row["publicado"]),
                    longitud_m=row["longitud_m"],
                )
                for row in rows
            ]
        )

    def patch(
        self, db: Session, canal_id: str, payload: CanalPublicacionPatch
    ) -> CanalPublicacionRow:
        result = db.execute(
            _PATCH_SQL,
            {
                "canal_id": canal_id,
                "publicado": payload.publicado,
                "nombre_publico": payload.nombre_publico,
            },
        )
        if result.first() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Canal no encontrado",
            )
        db.flush()
        listing = self.list_staff(db)
        for item in listing.items:
            if item.id == canal_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal no encontrado")

    def public_collections(self, db: Session) -> dict[str, Any]:
        has_pub = db.execute(_HAS_PUBLICACION_SQL).scalar()
        rows = db.execute(_PUBLIC_SQL if has_pub else _PUBLIC_FALLBACK_SQL).mappings().all()
        relevados: list[dict[str, Any]] = []
        propuestas: list[dict[str, Any]] = []
        for row in rows:
            geom = json.loads(row["geom_json"])
            feature = {
                "type": "Feature",
                "id": row["id"],
                "geometry": geom,
                "properties": {
                    "id": row["id"],
                    "nombre": row["nombre"],
                    "estado": row["estado"],
                    "longitud_m": row["longitud_m"],
                },
            }
            if row["estado"] == "propuesto":
                propuestas.append(feature)
            else:
                relevados.append(feature)
        return {
            "relevados": {"type": "FeatureCollection", "features": relevados},
            "propuestas": {"type": "FeatureCollection", "features": propuestas},
        }
