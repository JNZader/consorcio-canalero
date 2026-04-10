from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.models import IndiceHidrico, ZonaOperativa


class IntelligenceRepositoryZonesMixin:
    def _paginated_results(self, db: Session, base_stmt, *, page: int, limit: int, order_by) -> tuple[list[Any], int]:
        total: int = db.execute(select(func.count()).select_from(base_stmt.subquery())).scalar_one()
        items = list(db.execute(base_stmt.order_by(order_by).offset((page - 1) * limit).limit(limit)).scalars().all())
        return items, total

    def _zona_geojson_stmt(self, *, simplified: bool, tolerance: float = 0.0):
        geometry_expr = func.ST_AsGeoJSON(func.ST_Simplify(ZonaOperativa.geometria, tolerance)) if simplified else func.ST_AsGeoJSON(ZonaOperativa.geometria)
        return select(ZonaOperativa.id, ZonaOperativa.nombre, ZonaOperativa.cuenca, ZonaOperativa.superficie_ha, geometry_expr.label("geojson"))

    def _serialize_zona_feature(self, row, *, include_type: bool = True, allow_null_geometry: bool = False) -> dict[str, Any] | None:
        geometry = json.loads(row.geojson) if row.geojson else None
        if geometry is None and not allow_null_geometry:
            return None
        feature = {"geometry": geometry, "properties": {"id": str(row.id), "nombre": row.nombre, "cuenca": row.cuenca, "superficie_ha": row.superficie_ha}}
        if include_type:
            feature["type"] = "Feature"
        return feature

    def get_zona_by_id(self, db: Session, zona_id: uuid.UUID) -> Optional[ZonaOperativa]:
        return db.execute(select(ZonaOperativa).where(ZonaOperativa.id == zona_id)).scalar_one_or_none()

    def get_zonas(self, db: Session, *, page: int = 1, limit: int = 50, cuenca_filter: Optional[str] = None) -> tuple[list[ZonaOperativa], int]:
        base = select(ZonaOperativa)
        if cuenca_filter:
            base = base.where(ZonaOperativa.cuenca == cuenca_filter)
        return self._paginated_results(db, base, page=page, limit=limit, order_by=ZonaOperativa.nombre)

    def create_zona(self, db: Session, *, nombre: str, geometria: str, cuenca: str, superficie_ha: float = 0.0) -> ZonaOperativa:
        zona = ZonaOperativa(nombre=nombre, geometria=geometria, cuenca=cuenca, superficie_ha=superficie_ha)
        db.add(zona)
        db.flush()
        return zona

    def delete_zonas_by_cuenca(self, db: Session, cuenca: str) -> int:
        from sqlalchemy import delete

        result = db.execute(delete(ZonaOperativa).where(ZonaOperativa.cuenca == cuenca))
        db.flush()
        return result.rowcount

    def get_zonas_as_geojson(self, db: Session, *, bbox: tuple[float, float, float, float] | None = None, tolerance: float = 0.001, limit: int = 500, cuenca_filter: str | None = None) -> dict:
        stmt = self._zona_geojson_stmt(simplified=True, tolerance=tolerance)
        if cuenca_filter:
            stmt = stmt.where(ZonaOperativa.cuenca == cuenca_filter)
        if bbox is not None:
            minx, miny, maxx, maxy = bbox
            stmt = stmt.where(func.ST_Intersects(ZonaOperativa.geometria, func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)))
        rows = db.execute(stmt.order_by(ZonaOperativa.nombre).limit(limit)).all()
        features = [feature for row in rows if (feature := self._serialize_zona_feature(row, allow_null_geometry=True)) is not None]
        return {"type": "FeatureCollection", "features": features, "metadata": {"total": len(features), "tolerance": tolerance, "bbox": list(bbox) if bbox else None}}

    def get_zonas_for_grouping(self, db: Session, *, cuenca_filter: str | None = None) -> list[dict[str, Any]]:
        stmt = self._zona_geojson_stmt(simplified=False).order_by(ZonaOperativa.nombre)
        if cuenca_filter:
            stmt = stmt.where(ZonaOperativa.cuenca == cuenca_filter)
        rows = db.execute(stmt).all()
        return [feature for row in rows if (feature := self._serialize_zona_feature(row)) is not None]

    def get_zonas_criticas(self, db: Session, nivel_riesgo_min: str = "alto") -> list[ZonaOperativa]:
        niveles = ["bajo", "medio", "alto", "critico"]
        target_niveles = niveles[niveles.index(nivel_riesgo_min) if nivel_riesgo_min in niveles else 2 :]
        latest_hci = select(IndiceHidrico.zona_id, func.max(IndiceHidrico.fecha_calculo).label("max_fecha")).group_by(IndiceHidrico.zona_id).subquery()
        stmt = select(ZonaOperativa).join(IndiceHidrico, IndiceHidrico.zona_id == ZonaOperativa.id).join(latest_hci, (IndiceHidrico.zona_id == latest_hci.c.zona_id) & (IndiceHidrico.fecha_calculo == latest_hci.c.max_fecha)).where(IndiceHidrico.nivel_riesgo.in_(target_niveles))
        return list(db.execute(stmt).scalars().all())
