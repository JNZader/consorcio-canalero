"""Encola un aviso por cambio de estado sin duplicar la misma transición."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.denuncias.models import Denuncia
from app.domains.denuncias.tasks import TASK_NAME
from app.shared.celery_outbox import CeleryTaskKey, enqueue_celery_task

NOTIFY_NAMESPACE = uuid.UUID("6f0c1a2e-7b34-4d11-9a55-0c1e8a7b2d44")


def notification_task_id(denuncia_id: uuid.UUID, estado: str, respuesta: str | None) -> uuid.UUID:
    material = f"{denuncia_id}:{estado}:{(respuesta or '').strip()}"
    return uuid.uuid5(NOTIFY_NAMESPACE, material)


def maybe_enqueue_status_email(db: Session, denuncia: Denuncia, *, became_attended: bool) -> None:
    """Misma transacción que el update. Un reintento con el mismo estado no duplica la fila."""
    if not became_attended:
        return
    if not settings.denuncia_status_email_enabled:
        return
    if not (denuncia.contacto_email or "").strip():
        return
    task_id = notification_task_id(denuncia.id, denuncia.estado, denuncia.respuesta)
    try:
        with db.begin_nested():
            enqueue_celery_task(
                db,
                celery_task_id=task_id,
                task_key=CeleryTaskKey.NOTIFY_DENUNCIA_STATUS,
                task_kwargs={
                    "denuncia_id": str(denuncia.id),
                    "estado": denuncia.estado,
                    "respuesta": denuncia.respuesta,
                },
            )
    except IntegrityError:
        return


def payload_hash(ids: list[uuid.UUID], estado: str, comentario: str | None) -> str:
    raw = "|".join([estado, comentario or "", *sorted(str(item) for item in ids)])
    return hashlib.sha256(raw.encode()).hexdigest()


# El nombre del task tiene que coincidir con la clave del outbox.
assert TASK_NAME == CeleryTaskKey.NOTIFY_DENUNCIA_STATUS.value
