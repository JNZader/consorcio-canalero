"""Business-logic layer for the monitoring domain."""

import uuid
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.monitoring.models import AnalisisGee, Sugerencia
from app.domains.monitoring.repository import MonitoringRepository
from app.domains.monitoring.schemas import SugerenciaCreate, SugerenciaUpdate


class MonitoringService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: MonitoringRepository | None = None) -> None:
        self.repo = repository or MonitoringRepository()

    # ── SUGERENCIAS ────────────────────────────

    def get_sugerencia(self, db: Session, sugerencia_id: uuid.UUID) -> Sugerencia:
        sugerencia = self.repo.get_sugerencia_by_id(db, sugerencia_id)
        if sugerencia is None:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
        return sugerencia

    def list_sugerencias(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado: Optional[str] = None,
        categoria: Optional[str] = None,
    ) -> tuple[list[Sugerencia], int]:
        return self.repo.get_all_sugerencias(
            db,
            page=page,
            limit=limit,
            estado_filter=estado,
            categoria_filter=categoria,
        )

    def create_sugerencia(
        self, db: Session, data: SugerenciaCreate
    ) -> Sugerencia:
        sugerencia = self.repo.create_sugerencia(db, data)
        db.commit()
        db.refresh(sugerencia)
        return sugerencia

    def update_sugerencia(
        self,
        db: Session,
        sugerencia_id: uuid.UUID,
        data: SugerenciaUpdate,
    ) -> Sugerencia:
        sugerencia = self.repo.update_sugerencia(db, sugerencia_id, data)
        if sugerencia is None:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
        db.commit()
        db.refresh(sugerencia)
        return sugerencia

    # ── ANALYSES ───────────────────────────────

    def get_analysis(self, db: Session, analysis_id: uuid.UUID) -> AnalisisGee:
        analysis = self.repo.get_analysis_by_id(db, analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analisis no encontrado")
        return analysis

    def list_analyses(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo: Optional[str] = None,
    ) -> tuple[list[AnalisisGee], int]:
        return self.repo.get_analysis_history(
            db, page=page, limit=limit, tipo_filter=tipo
        )

    def save_analysis(
        self, db: Session, data: dict[str, Any]
    ) -> AnalisisGee:
        analysis = self.repo.save_analysis(db, data)
        db.commit()
        db.refresh(analysis)
        return analysis

    # ── DASHBOARD ──────────────────────────────

    def get_dashboard_stats(self, db: Session) -> dict[str, Any]:
        return self.repo.get_dashboard_stats(db)
