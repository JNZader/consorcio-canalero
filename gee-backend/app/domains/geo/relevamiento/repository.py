"""Data access for Fase B. Append-only by construction, not by discipline.

There is no mutation statement in this module and no method that could grow into
one: every write is an INSERT, current state is read from
``relevamiento_tramo_vigente``, and history is read newest-first by ``version``.
``test_relevamiento_repository`` greps this file for a mutation path, so the
property is checked rather than promised.

``relevado_en`` never appears in an ORDER BY here. It is transaction-start time
and is carried for display only; ``version`` is the total order (design D4).
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: RETURNING the whole row, so the caller never has to re-read to learn the
#: ``version`` the sequence just assigned.
SQL_INSERT_RELEVAMIENTO = text(
    """
    INSERT INTO relevamiento_tramo (
        id, tramo_ref, nivel_relativo, tiene_cuneta, estado_cuneta,
        observaciones, relevado_por, nivel_desde_candidata
    ) VALUES (
        :id, :tramo_ref, :nivel_relativo, :tiene_cuneta, :estado_cuneta,
        :observaciones, :relevado_por, :nivel_desde_candidata
    )
    RETURNING id, tramo_ref, nivel_relativo, tiene_cuneta, estado_cuneta,
              observaciones, relevado_por, relevado_en, version,
              nivel_desde_candidata
    """
)

SQL_SELECT_VIGENTE = text(
    """
    SELECT id, tramo_ref, nivel_relativo, tiene_cuneta, estado_cuneta,
           observaciones, relevado_por, relevado_en, version, nivel_desde_candidata
      FROM relevamiento_tramo_vigente
     WHERE tramo_ref = :tramo_ref
    """
)

#: Newest first, by ``version``. A tie is impossible: the column is unique.
SQL_SELECT_HISTORIAL = text(
    """
    SELECT id, tramo_ref, nivel_relativo, tiene_cuneta, estado_cuneta,
           observaciones, relevado_por, relevado_en, version, nivel_desde_candidata
      FROM relevamiento_tramo
     WHERE tramo_ref = :tramo_ref
     ORDER BY version DESC
    """
)

#: The NEWEST candidate for this segment. Multiple runs legitimately coexist
#: (the key is the run, not the layer), so "the" candidate is not a thing —
#: ``geo_job_id`` breaks the tie deterministically if two runs share a stamp.
SQL_SELECT_CANDIDATA = text(
    """
    SELECT tramo_ref, geo_job_id, dem_layer_id, clasificacion_candidata,
           confianza_m, calculada_en
      FROM tramo_clasificacion_candidata
     WHERE tramo_ref = :tramo_ref
     ORDER BY calculada_en DESC, geo_job_id
     LIMIT 1
    """
)

#: One candidate row per segment per RUN. No upsert and no conflict clause: a new
#: run is a new generation, keyed by its own ``geo_job_id``, and the previous
#: generation is history rather than something to overwrite.
SQL_INSERT_CANDIDATA = text(
    """
    INSERT INTO tramo_clasificacion_candidata (
        tramo_ref, geo_job_id, dem_layer_id, clasificacion_candidata,
        confianza_m, calculada_en
    ) VALUES (
        :tramo_ref, :geo_job_id, :dem_layer_id, :clasificacion_candidata,
        :confianza_m, :calculada_en
    )
    """
)

#: The three counters plus the denominator, in ONE pass over the ACTIVE network,
#: so they cannot disagree with each other. A retired segment is out of all four:
#: counting it as ``sin_datos`` would permanently depress coverage against a road
#: that no longer exists, and counting it as ``relevados`` would inflate coverage
#: of the network that does.
SQL_COBERTURA = text(
    """
    SELECT
        count(*) FILTER (WHERE v.tramo_ref IS NOT NULL)                     AS relevados,
        count(*) FILTER (WHERE v.tramo_ref IS NULL AND c.tramo_ref IS NOT NULL)
                                                                            AS solo_candidato,
        count(*) FILTER (WHERE v.tramo_ref IS NULL AND c.tramo_ref IS NULL) AS sin_datos,
        count(*)                                                            AS total_activos
      FROM red_vial r
      LEFT JOIN relevamiento_tramo_vigente v ON v.tramo_ref = r.id
      LEFT JOIN LATERAL (
          SELECT 1 AS tramo_ref FROM tramo_clasificacion_candidata t
           WHERE t.tramo_ref = r.id LIMIT 1
      ) c ON true
     WHERE r.activo
       AND (
           :sin_filtro
           OR ST_Intersects(r.geom, ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, 4326))
       )
    """
)

#: The area footprint, from the layers that area's DEM runs registered. Same
#: spatial pre-filter the crossing run uses (``SQL_RED_VIAL_EN_BBOX``), read from
#: the recorded bboxes rather than by opening rasters: coverage is a counting
#: question and must not depend on a file still being on disk.
SQL_AREA_BBOX = text(
    """
    SELECT bbox FROM geo_layers
     WHERE area_id = :area_id AND bbox IS NOT NULL
    """
)


class RelevamientoRepository:
    """Reads and one INSERT. The caller owns the transaction boundary."""

    def insertar(
        self,
        db: Session,
        *,
        tramo_ref: str,
        nivel_relativo: str,
        tiene_cuneta: str,
        estado_cuneta: Optional[str],
        observaciones: Optional[str],
        relevado_por: uuid.UUID,
        nivel_desde_candidata: bool,
    ) -> dict[str, Any]:
        """Always an INSERT. A correction is a new row, never a rewrite.

        The id is generated here rather than left to the column default: the
        ``UUIDMixin`` default is a Python-side ORM default, so it does not exist
        for a plain SQL INSERT. Same shape as ``replace_cruces_for_area``.
        """
        row = (
            db.execute(
                SQL_INSERT_RELEVAMIENTO,
                {
                    "id": str(uuid.uuid4()),
                    "tramo_ref": tramo_ref,
                    "nivel_relativo": nivel_relativo,
                    "tiene_cuneta": tiene_cuneta,
                    "estado_cuneta": estado_cuneta,
                    "observaciones": observaciones,
                    "relevado_por": relevado_por,
                    "nivel_desde_candidata": nivel_desde_candidata,
                },
            )
            .mappings()
            .one()
        )
        return dict(row)

    def insertar_candidatas(
        self,
        db: Session,
        *,
        filas: list[dict[str, Any]],
        geo_job_id: uuid.UUID,
        calculada_en: Any,
    ) -> int:
        """Write one run's candidates. The caller owns the transaction boundary.

        Nothing older is touched: candidates from previous runs stay exactly
        where they are, which is what makes "two DEM runs produce two candidate
        rows" true rather than aspirational.
        """
        for fila in filas:
            db.execute(
                SQL_INSERT_CANDIDATA,
                {
                    "geo_job_id": str(geo_job_id),
                    "calculada_en": calculada_en,
                    "dem_layer_id": fila.get("dem_layer_id"),
                    "tramo_ref": fila["tramo_ref"],
                    "clasificacion_candidata": fila["clasificacion_candidata"],
                    "confianza_m": fila["confianza_m"],
                },
            )
        return len(filas)

    def get_vigente(self, db: Session, tramo_ref: str) -> Optional[dict[str, Any]]:
        row = db.execute(SQL_SELECT_VIGENTE, {"tramo_ref": tramo_ref}).mappings().first()
        return dict(row) if row is not None else None

    def get_historial(self, db: Session, tramo_ref: str) -> list[dict[str, Any]]:
        return [
            dict(r) for r in db.execute(SQL_SELECT_HISTORIAL, {"tramo_ref": tramo_ref}).mappings()
        ]

    def get_candidata(self, db: Session, tramo_ref: str) -> Optional[dict[str, Any]]:
        row = db.execute(SQL_SELECT_CANDIDATA, {"tramo_ref": tramo_ref}).mappings().first()
        return dict(row) if row is not None else None

    def get_area_bbox(
        self, db: Session, area_id: str
    ) -> Optional[tuple[float, float, float, float]]:
        """The union of the bboxes that area's layers recorded, or ``None``.

        ``None`` means "this area has no registered footprint" and is answered by
        the caller as a named refusal, never as "count the whole network".
        """
        cajas = [
            row[0]
            for row in db.execute(SQL_AREA_BBOX, {"area_id": area_id}).all()
            if isinstance(row[0], (list, tuple)) and len(row[0]) == 4
        ]
        if not cajas:
            return None
        return (
            min(float(c[0]) for c in cajas),
            min(float(c[1]) for c in cajas),
            max(float(c[2]) for c in cajas),
            max(float(c[3]) for c in cajas),
        )

    def contar_cobertura(
        self,
        db: Session,
        *,
        bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> dict[str, int]:
        """Three counters and their denominator, over ACTIVE segments only.

        They are returned separately and are never summed here: "surveyed" is one
        of them, not their total (RSS-R4).
        """
        minx, miny, maxx, maxy = bbox if bbox is not None else (0.0, 0.0, 0.0, 0.0)
        row = (
            db.execute(
                SQL_COBERTURA,
                {
                    "sin_filtro": bbox is None,
                    "minx": minx,
                    "miny": miny,
                    "maxx": maxx,
                    "maxy": maxy,
                },
            )
            .mappings()
            .one()
        )
        return {key: int(value) for key, value in row.items()}


__all__ = ["RelevamientoRepository"]
