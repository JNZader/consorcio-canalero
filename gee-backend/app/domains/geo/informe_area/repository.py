"""Data access for ``informes_area``. No policy here — the service owns that.

State transitions use compare-and-set (``actualizar_estado_if_actual``), the
same discipline ``GeoRepository.update_job_status_if_current`` applies to
``geo_jobs``: a task that lost a race (or a retry against a row another
worker already finished) updates zero rows instead of resurrecting stale
work.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.domains.geo.models import EstadoGeoJob
from app.domains.geo.informe_area.models import InformeArea

# What "in progress" means for the per-user ceiling (S5): created but not yet
# finished, either way.
_EN_CURSO = (EstadoGeoJob.PENDING, EstadoGeoJob.RUNNING)

LISTA_LIMITE = 100


class InformeAreaRepository:
    """CRUD + the three purposeful queries the service needs."""

    def crear(
        self,
        db: Session,
        *,
        usuario_id: uuid.UUID,
        nombre: str,
        hash_seleccion: str,
        version_clave: str,
        parametros: dict,
        vence_at: datetime,
        celery_task_id: str,
    ) -> InformeArea:
        row = InformeArea(
            usuario_id=usuario_id,
            nombre=nombre,
            estado=EstadoGeoJob.PENDING,
            hash_seleccion=hash_seleccion,
            version_clave=version_clave,
            parametros=parametros,
            vence_at=vence_at,
            progreso=0,
            celery_task_id=celery_task_id,
        )
        db.add(row)
        db.flush()
        return row

    def obtener(self, db: Session, informe_id: uuid.UUID) -> InformeArea | None:
        return db.execute(
            select(InformeArea).where(InformeArea.id == informe_id)
        ).scalar_one_or_none()

    def contar_en_curso(self, db: Session, usuario_id: uuid.UUID) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(InformeArea)
                .where(
                    InformeArea.usuario_id == usuario_id,
                    InformeArea.estado.in_(_EN_CURSO),
                )
            )
            or 0
        )

    def buscar_completado(
        self, db: Session, *, usuario_id: uuid.UUID, version_clave: str
    ) -> InformeArea | None:
        """The S4 cache probe — scoped to the SAME user on purpose (S11).

        ``version_clave`` embeds ``hash_seleccion``, so clave equality implies
        selection equality; matching on the compound (usuario_id, version_clave)
        index is the whole lookup. Another user's completed informe is never a
        cache candidate: it is private data, and the reuse path hands back the
        row itself, not a recomputation.
        """
        return db.execute(
            select(InformeArea)
            .where(
                InformeArea.usuario_id == usuario_id,
                InformeArea.version_clave == version_clave,
                InformeArea.estado == EstadoGeoJob.COMPLETED,
            )
            .order_by(InformeArea.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def listar(
        self, db: Session, *, usuario_id: uuid.UUID | None = None
    ) -> tuple[list[InformeArea], int]:
        """Most recent first. ``usuario_id=None`` means the admin's full view."""
        base = select(InformeArea)
        total_base = select(func.count()).select_from(InformeArea)
        if usuario_id is not None:
            base = base.where(InformeArea.usuario_id == usuario_id)
            total_base = total_base.where(InformeArea.usuario_id == usuario_id)
        filas = list(
            db.execute(base.order_by(InformeArea.created_at.desc()).limit(LISTA_LIMITE)).scalars()
        )
        total = int(db.scalar(total_base) or 0)
        return filas, total

    def actualizar_estado_if_actual(
        self,
        db: Session,
        informe_id: uuid.UUID,
        *,
        expected_estado: EstadoGeoJob,
        estado: EstadoGeoJob | None = None,
        progreso: int | None = None,
        resultado: dict | None = None,
        error: str | None = None,
    ) -> bool:
        """Compare-and-set a transition; False means the row moved on."""
        valores: dict[str, object] = {"updated_at": func.now()}
        if estado is not None:
            valores["estado"] = estado
        if progreso is not None:
            valores["progreso"] = progreso
        if resultado is not None:
            valores["resultado"] = resultado
        if error is not None:
            valores["error"] = error
        result = db.execute(
            update(InformeArea)
            .where(InformeArea.id == informe_id, InformeArea.estado == expected_estado)
            .values(**valores)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    def borrar_vencidos(self, db: Session, *, ahora: datetime | None = None) -> int:
        """Delete every row past its retention deadline (S11)."""
        corte = ahora or datetime.now(timezone.utc)
        result = db.execute(delete(InformeArea).where(InformeArea.vence_at < corte))
        db.commit()
        return int(getattr(result, "rowcount", 0) or 0)
