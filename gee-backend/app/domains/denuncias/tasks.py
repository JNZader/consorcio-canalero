"""Cola de aviso de estado. No abre SMTP si el flag o el host están vacíos."""

from __future__ import annotations

import uuid

import structlog

from app.config import settings
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.domains.denuncias.models import Denuncia
from app.shared.email import send_email_blocking

logger = structlog.get_logger(__name__)

TASK_NAME = "denuncias.notify_status"


def deliver_status_email(denuncia_id: str, estado: str, respuesta: str | None) -> str:
    """Cuerpo del task, testeable sin broker."""
    if not settings.denuncia_status_email_enabled:
        return "flag_off"
    db = SessionLocal()
    try:
        row = db.get(Denuncia, uuid.UUID(denuncia_id))
        if row is None or row.deleted_at is not None:
            return "missing"
        email = (row.contacto_email or "").strip()
        if not email:
            return "no_recipient"
        text = f"El consorcio actualizó tu reporte.\n\nEstado: {estado}\n"
        if respuesta:
            text += f"\nRespuesta:\n{respuesta}\n"
        text += "\nEl seguimiento también está en tu perfil, en Mis denuncias.\n"
        send_email_blocking(
            to_email=email,
            subject="Actualización de tu reporte",
            body_text=text,
        )
        return "queued_or_sent"
    finally:
        db.close()


@celery_app.task(queue="celery", name=TASK_NAME)
def notify_denuncia_status(denuncia_id: str, estado: str, respuesta: str | None = None) -> str:
    logger.info("denuncia.notify_status", denuncia_id=denuncia_id, estado=estado)
    return deliver_status_email(denuncia_id, estado, respuesta)
