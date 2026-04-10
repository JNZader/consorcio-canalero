from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.domains.geo.intelligence.models import CanalSuggestion, CompositeZonalStats, ZonaOperativa


class IntelligenceRepositoryCompositesMixin:
    def bulk_upsert_composite_stats(self, db: Session, stats: list[dict[str, Any]]) -> int:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not stats:
            return 0
        stmt = pg_insert(CompositeZonalStats).values(stats)
        stmt = stmt.on_conflict_do_update(
            index_elements=["zona_id", "tipo"],
            set_={
                "fecha_calculo": stmt.excluded.fecha_calculo,
                "mean_score": stmt.excluded.mean_score,
                "max_score": stmt.excluded.max_score,
                "p90_score": stmt.excluded.p90_score,
                "area_high_risk_ha": stmt.excluded.area_high_risk_ha,
                "weights_used": stmt.excluded.weights_used,
                "updated_at": func.now(),
            },
        )
        result = db.execute(stmt)
        db.flush()
        return result.rowcount

    def get_composite_stats_by_area(self, db: Session, area_id: str, tipo: Optional[str] = None) -> list[CompositeZonalStats]:
        stmt = select(CompositeZonalStats).join(ZonaOperativa, CompositeZonalStats.zona_id == ZonaOperativa.id).options(joinedload(CompositeZonalStats.zona)).where(ZonaOperativa.nombre.like(f"basin_{area_id}_%") | (ZonaOperativa.cuenca == area_id))
        if tipo:
            stmt = stmt.where(CompositeZonalStats.tipo == tipo)
        items = list(db.execute(stmt.order_by(CompositeZonalStats.mean_score.desc())).scalars().unique().all())
        if items or area_id != "zona_principal":
            return items
        fallback_stmt = select(CompositeZonalStats).join(ZonaOperativa, CompositeZonalStats.zona_id == ZonaOperativa.id).options(joinedload(CompositeZonalStats.zona))
        if tipo:
            fallback_stmt = fallback_stmt.where(CompositeZonalStats.tipo == tipo)
        return list(db.execute(fallback_stmt.order_by(CompositeZonalStats.mean_score.desc())).scalars().unique().all())

    def insert_suggestions_batch(self, db: Session, suggestions: list[dict[str, Any]]) -> int:
        if not suggestions:
            return 0
        objects = [CanalSuggestion(**s) for s in suggestions]
        db.add_all(objects)
        db.flush()
        return len(objects)

    def get_suggestions_by_tipo(self, db: Session, tipo: str, *, page: int = 1, limit: int = 50, batch_id: Optional[uuid.UUID] = None) -> tuple[list[CanalSuggestion], int]:
        base = select(CanalSuggestion).where(CanalSuggestion.tipo == tipo)
        if batch_id:
            base = base.where(CanalSuggestion.batch_id == batch_id)
        return self._paginated_results(db, base, page=page, limit=limit, order_by=CanalSuggestion.score.desc())

    def get_latest_batch(self, db: Session) -> Optional[uuid.UUID]:
        return db.execute(select(CanalSuggestion.batch_id).order_by(CanalSuggestion.created_at.desc()).limit(1)).scalar_one_or_none()

    def get_summary(self, db: Session, batch_id: Optional[uuid.UUID] = None) -> Optional[dict[str, Any]]:
        batch_id = batch_id or self.get_latest_batch(db)
        if batch_id is None:
            return None
        agg = db.execute(select(func.count().label("total"), func.avg(CanalSuggestion.score).label("avg_score"), func.min(CanalSuggestion.created_at).label("created_at")).where(CanalSuggestion.batch_id == batch_id)).one()
        if agg.total == 0:
            return None
        by_tipo = {row.tipo: row.cnt for row in db.execute(select(CanalSuggestion.tipo, func.count().label("cnt")).where(CanalSuggestion.batch_id == batch_id).group_by(CanalSuggestion.tipo)).all()}
        return {"batch_id": batch_id, "total_suggestions": agg.total, "by_tipo": by_tipo, "avg_score": round(float(agg.avg_score), 2), "created_at": agg.created_at}
