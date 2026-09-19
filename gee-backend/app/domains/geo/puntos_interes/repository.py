"""Data-access for ``punto_interes``."""

from __future__ import annotations

import json
import uuid
from typing import Optional

from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.geo.puntos_interes.models import PuntoInteres
from app.domains.geo.puntos_interes.schemas import (
    PuntoInteresCreate,
    PuntoInteresFeature,
    PuntoInteresFeatureCollection,
    PuntoInteresProperties,
)


def _feature_from_row(
    row_id: uuid.UUID,
    titulo: str,
    nota: Optional[str],
    tipo: str,
    geometry: dict,
) -> PuntoInteresFeature:
    ident = str(row_id)
    return PuntoInteresFeature(
        id=ident,
        geometry=geometry,
        properties=PuntoInteresProperties(id=ident, titulo=titulo, nota=nota, tipo=tipo),
    )


class PuntoInteresRepository:
    def list_all(self, db: Session) -> PuntoInteresFeatureCollection:
        stmt = select(
            PuntoInteres.id,
            PuntoInteres.titulo,
            PuntoInteres.nota,
            PuntoInteres.tipo,
            func.ST_AsGeoJSON(PuntoInteres.geometria).label("geom_json"),
        ).order_by(PuntoInteres.created_at.desc(), PuntoInteres.id.desc())
        rows = db.execute(stmt).all()
        features: list[PuntoInteresFeature] = []
        for row in rows:
            if row.geom_json is None:
                continue
            features.append(
                _feature_from_row(
                    row.id,
                    row.titulo,
                    row.nota,
                    row.tipo,
                    json.loads(row.geom_json),
                )
            )
        return PuntoInteresFeatureCollection(features=features)

    def create(
        self,
        db: Session,
        payload: PuntoInteresCreate,
        created_by: Optional[uuid.UUID],
    ) -> PuntoInteresFeature:
        row = PuntoInteres(
            titulo=payload.titulo,
            nota=payload.nota,
            tipo=payload.tipo,
            geometria=ST_SetSRID(ST_MakePoint(payload.lng, payload.lat), 4326),
            created_by=created_by,
        )
        db.add(row)
        db.flush()
        return _feature_from_row(
            row.id,
            row.titulo,
            row.nota,
            row.tipo,
            {"type": "Point", "coordinates": [payload.lng, payload.lat]},
        )

    def delete(self, db: Session, punto_id: uuid.UUID) -> bool:
        row = db.get(PuntoInteres, punto_id)
        if row is None:
            return False
        db.delete(row)
        db.flush()
        return True
