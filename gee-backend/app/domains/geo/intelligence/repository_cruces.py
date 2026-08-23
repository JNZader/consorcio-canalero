"""Data access for ``cruce_camino`` — the road-crossing rows and their provenance.

Deliberately small. The write path is a delete-then-insert **scoped to
``area_id``** in ONE transaction, which is expressible only because
``cruce_camino`` has an area column; it was not expressible on
``puntos_conflicto`` (design D1), and that is one of the five reasons the reuse
was withdrawn.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.cruces_camino_support import (
    DEM_JOB_TIPOS,
    dem_resultados_por_area,
)

#: Scoped to the area, so a re-run for area A leaves area B's rows untouched.
SQL_DELETE_AREA = text("DELETE FROM cruce_camino WHERE area_id = :area_id")

SQL_ADVISORY_LOCK_AREA = text(
    "SELECT pg_advisory_xact_lock(hashtextextended('cruce_camino:' || :area_id, 0))"
)

SQL_INSERT_CRUCE = text(
    """
    INSERT INTO cruce_camino (
        id, area_id, tramo_ref, tipo, geometria,
        direccion_flujo_deg, rumbo_camino_deg, lado_cruce,
        area_aporte_ha, orden_ranking, confianza, nota, canal_ref,
        geo_job_id, calculada_en
    ) VALUES (
        :id, :area_id, :tramo_ref, :tipo,
        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
        :direccion_flujo_deg, :rumbo_camino_deg, :lado_cruce,
        :area_aporte_ha, :orden_ranking, :confianza, :nota, :canal_ref,
        :geo_job_id, :calculada_en
    )
    """
)

SQL_SELECT_AREA = text(
    """
    SELECT id, tramo_ref, tipo, ST_X(geometria) AS lon, ST_Y(geometria) AS lat,
           direccion_flujo_deg, rumbo_camino_deg, lado_cruce, area_aporte_ha,
           orden_ranking, confianza, nota, canal_ref, geo_job_id, calculada_en
      FROM cruce_camino
     WHERE area_id = :area_id
     ORDER BY tipo, orden_ranking NULLS LAST, tramo_ref
    """
)

SQL_MAX_CALCULADA_EN = text("SELECT max(calculada_en) FROM cruce_camino WHERE area_id = :area_id")

SQL_ULTIMO_JOB = text(
    """
    SELECT resultado FROM geo_jobs
     WHERE id = (
        SELECT geo_job_id FROM cruce_camino WHERE area_id = :area_id
         ORDER BY calculada_en DESC LIMIT 1
     )
    """
)

#: The spatial pre-filter: only ACTIVE segments whose geometry intersects the
#: area raster's bounding box. Segments entirely outside it are **out of scope**
#: for the run — not iterated, not sampled, and NOT written to ``excluidos``: an
#: exclusion record means "this candidate was considered and rejected", and a
#: road in another province was never a candidate.
SQL_RED_VIAL_EN_BBOX = text(
    """
    SELECT id, ST_AsText(geom) AS wkt
      FROM red_vial
     WHERE activo
       AND ST_Intersects(geom, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
     ORDER BY id
    """
)

SQL_CANALES_EN_BBOX = text(
    """
    SELECT id, ST_AsText(geom) AS wkt
      FROM canal_consorcio
     WHERE ST_Intersects(geom, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
     ORDER BY id
    """
)


class IntelligenceRepositoryCrucesMixin:
    """``cruce_camino`` reads and writes, plus the two lookups the run needs."""

    def get_dem_resultados(self, db: Session, area_id: str) -> list[dict[str, Any]]:
        """Newest first. Used to verify the no-burn condition before substituting."""
        return dem_resultados_por_area(db, area_id)

    def replace_cruces_for_area(
        self,
        db: Session,
        *,
        area_id: str,
        rows: list[dict[str, Any]],
        geo_job_id: uuid.UUID,
        calculada_en: datetime,
    ) -> int:
        """Delete-then-insert, scoped to ``area_id``, in ONE transaction.

        The caller owns the transaction boundary. Recomputation IS invalidation:
        there is never a mixture of two generations, so ``orden_ranking`` is
        always a rank within one coherent run and no operator ever sees a
        half-replaced list.
        """
        # Serialize whole-area replaces: two concurrent runs for the SAME area
        # would otherwise interleave their delete-then-insert into a mixed set
        # and orden_ranking would stop being a rank within one coherent run.
        # The lock is transaction-scoped, so the caller's commit/rollback
        # releases it; runs for different areas do not contend.
        db.execute(SQL_ADVISORY_LOCK_AREA, {"area_id": area_id})
        db.execute(SQL_DELETE_AREA, {"area_id": area_id})
        for row in rows:
            db.execute(
                SQL_INSERT_CRUCE,
                {
                    "id": str(uuid.uuid4()),
                    "area_id": area_id,
                    "geo_job_id": str(geo_job_id),
                    "calculada_en": calculada_en,
                    **row,
                },
            )
        return len(rows)

    def get_cruces_for_area(self, db: Session, area_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in db.execute(SQL_SELECT_AREA, {"area_id": area_id}).mappings()]

    def get_calculada_en(self, db: Session, area_id: str) -> Optional[datetime]:
        return db.execute(SQL_MAX_CALCULADA_EN, {"area_id": area_id}).scalar()

    def get_ultimo_resultado_cruces(self, db: Session, area_id: str) -> Optional[dict]:
        """The producing run's own account: ``excluidos``, parameters, variant."""
        resultado = db.execute(SQL_ULTIMO_JOB, {"area_id": area_id}).scalar()
        return resultado if isinstance(resultado, dict) else None

    def get_red_vial_en_bbox(
        self, db: Session, *, minx: float, miny: float, maxx: float, maxy: float
    ) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in db.execute(
                SQL_RED_VIAL_EN_BBOX,
                {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
            ).mappings()
        ]

    def get_canales_en_bbox(
        self, db: Session, *, minx: float, miny: float, maxx: float, maxy: float
    ) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in db.execute(
                SQL_CANALES_EN_BBOX,
                {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
            ).mappings()
        ]


__all__ = ["IntelligenceRepositoryCrucesMixin", "DEM_JOB_TIPOS"]
