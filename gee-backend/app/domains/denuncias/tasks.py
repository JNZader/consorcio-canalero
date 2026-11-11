"""Cola de aviso de estado. No abre SMTP si el flag o el host están vacíos.

Con el default de la app (``task_acks_late=False``) un raise queda acked y
jamás se re-entrega: la recuperación de una falla transitoria de SMTP vive
en el retry del task (issue #697). Agotados los reintentos no hay
dead-letter de OUTCOMES — el outbox transaccional sólo trackea la
publicación al broker — así que el fallo definitivo es un log estructurado
de nivel error.
"""

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

# Política de retry establecida en este repo (rainfall.ingest_source_scope:
# ``bind=True, max_retries=3`` + countdown fijo de 300s). Cuatro intentos a
# lo largo de ~15 minutos cubren una caída transitoria de SMTP.
RETRY_COUNTDOWN_SECONDS = 300


def deliver_status_email(denuncia_id: str, estado: str, respuesta: str | None) -> str:
    """Cuerpo del task, testeable sin broker.

    Levanta si el envío no se concreta (``raise_on_error``); la decisión de
    reintentar vive en el task, no acá.
    """
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
            raise_on_error=True,
        )
        return "queued_or_sent"
    finally:
        db.close()


@celery_app.task(queue="celery", name=TASK_NAME, bind=True, max_retries=3)
def notify_denuncia_status(
    self,
    denuncia_id: str,
    estado: str,
    respuesta: str | None = None,
) -> str:
    logger.info("denuncia.notify_status", denuncia_id=denuncia_id, estado=estado)
    try:
        return deliver_status_email(denuncia_id, estado, respuesta)
    except Exception as exc:
        # Broad a propósito: la jerarquía de errores de aiosmtplib no se puede
        # importar acá (app.shared.email protege el import para entornos sin
        # la lib) y una falla transitoria de DB del lookup merece el mismo
        # retry que una de SMTP.
        if self.request.retries >= self.max_retries:
            logger.error(
                "denuncia.notify_status.failed_permanently",
                denuncia_id=denuncia_id,
                estado=estado,
                attempts=self.max_retries + 1,
                error=f"{type(exc).__name__}: {exc}",
            )
            return "failed_after_retries"
        raise self.retry(exc=exc, countdown=RETRY_COUNTDOWN_SECONDS) from exc
