"""Business-logic layer for tramites domain."""

import uuid
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.tramites.models import (
    Tramite,
    TramiteSeguimiento,
    EstadoTramite,
    VALID_TRANSITIONS,
)
from app.domains.tramites.repository import TramiteRepository
from app.domains.tramites.schemas import (
    TramiteCreate,
    TramiteUpdate,
    SeguimientoCreate,
)


class TramiteService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: TramiteRepository | None = None) -> None:
        self.repo = repository or TramiteRepository()

    # ── QUERIES ───────────────────────────────

    def get_by_id(self, db: Session, tramite_id: uuid.UUID) -> Tramite:
        tramite = self.repo.get_by_id(db, tramite_id)
        if tramite is None:
            raise HTTPException(status_code=404, detail="Tramite no encontrado")
        return tramite

    def list_tramites(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado: Optional[str] = None,
        tipo: Optional[str] = None,
        prioridad: Optional[str] = None,
    ) -> tuple[list[Tramite], int]:
        return self.repo.get_all(
            db,
            page=page,
            limit=limit,
            estado_filter=estado,
            tipo_filter=tipo,
            prioridad_filter=prioridad,
        )

    def get_stats(self, db: Session) -> dict:
        return self.repo.get_stats(db)

    # ── COMMANDS ──────────────────────────────

    def create(
        self,
        db: Session,
        data: TramiteCreate,
        usuario_id: uuid.UUID,
    ) -> Tramite:
        """Create a tramite and commit."""
        tramite = self.repo.create(db, data, usuario_id=usuario_id)
        db.commit()
        db.refresh(tramite)
        return tramite

    def update(
        self,
        db: Session,
        tramite_id: uuid.UUID,
        data: TramiteUpdate,
        operator_id: uuid.UUID,
    ) -> Tramite:
        """
        Update estado / resolucion / prioridad, validating state transitions
        and recording changes in seguimiento.
        """
        tramite = self.get_by_id(db, tramite_id)

        # State transition validation
        if data.estado is not None and data.estado != tramite.estado:
            allowed = VALID_TRANSITIONS.get(tramite.estado, set())
            if data.estado not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Transicion de estado invalida: "
                        f"{tramite.estado} -> {data.estado}"
                    ),
                )

            # Record in seguimiento
            self.repo.add_seguimiento(
                db,
                tramite_id=tramite_id,
                estado_anterior=tramite.estado,
                estado_nuevo=data.estado,
                comentario=data.comentario or "Cambio de estado",
                usuario_id=operator_id,
            )

            # Set fecha_resolucion on terminal-ish states
            if data.estado in (
                EstadoTramite.APROBADO,
                EstadoTramite.RECHAZADO,
            ):
                tramite.fecha_resolucion = date.today()

        updated = self.repo.update(db, tramite_id, data)
        db.commit()
        db.refresh(updated)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]

    def add_seguimiento(
        self,
        db: Session,
        tramite_id: uuid.UUID,
        data: SeguimientoCreate,
        operator_id: uuid.UUID,
    ) -> TramiteSeguimiento:
        """Add a follow-up comment without changing state."""
        tramite = self.get_by_id(db, tramite_id)

        entry = self.repo.add_seguimiento(
            db,
            tramite_id=tramite_id,
            estado_anterior=tramite.estado,
            estado_nuevo=tramite.estado,
            comentario=data.comentario,
            usuario_id=operator_id,
        )
        db.commit()
        db.refresh(entry)
        return entry
