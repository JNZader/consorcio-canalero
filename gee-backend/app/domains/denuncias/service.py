"""Business-logic layer for denuncias domain."""

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.denuncias.models import (
    Denuncia,
    DenunciaHistorial,
    EstadoDenuncia,
    VALID_TRANSITIONS,
)
from app.domains.denuncias.repository import DenunciaRepository
from app.domains.denuncias.schemas import DenunciaCreate, DenunciaUpdate


class DenunciaService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: DenunciaRepository | None = None) -> None:
        self.repo = repository or DenunciaRepository()

    # ── QUERIES ───────────────────────────────

    def get_by_id(self, db: Session, denuncia_id: uuid.UUID) -> Denuncia:
        denuncia = self.repo.get_by_id(db, denuncia_id)
        if denuncia is None:
            raise HTTPException(status_code=404, detail="Denuncia no encontrada")
        return denuncia

    def list_denuncias(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado: Optional[str] = None,
        cuenca: Optional[str] = None,
    ) -> tuple[list[Denuncia], int]:
        return self.repo.get_all(
            db,
            page=page,
            limit=limit,
            estado_filter=estado,
            cuenca_filter=cuenca,
        )

    def get_stats(self, db: Session) -> dict:
        return self.repo.get_stats(db)

    # ── COMMANDS ──────────────────────────────

    def create(
        self,
        db: Session,
        data: DenunciaCreate,
        user_id: Optional[uuid.UUID] = None,
    ) -> Denuncia:
        """Create a denuncia and commit."""
        denuncia = self.repo.create(db, data, user_id=user_id)
        db.commit()
        db.refresh(denuncia)
        return denuncia

    def update(
        self,
        db: Session,
        denuncia_id: uuid.UUID,
        data: DenunciaUpdate,
        operator_id: uuid.UUID,
    ) -> Denuncia:
        """
        Update estado / respuesta, validating state transitions
        and recording changes in historial.
        """
        denuncia = self.get_by_id(db, denuncia_id)

        # State transition validation
        if data.estado is not None and data.estado != denuncia.estado:
            allowed = VALID_TRANSITIONS.get(denuncia.estado, set())
            if data.estado not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Transicion de estado invalida: "
                        f"{denuncia.estado} -> {data.estado}"
                    ),
                )

            # Record in historial
            self.repo.add_historial(
                db,
                denuncia_id=denuncia_id,
                estado_anterior=denuncia.estado,
                estado_nuevo=data.estado,
                comentario=data.comentario,
                usuario_id=operator_id,
            )

        updated = self.repo.update(db, denuncia_id, data)
        db.commit()
        db.refresh(updated)  # type: ignore[arg-type]
        return updated  # type: ignore[return-value]
