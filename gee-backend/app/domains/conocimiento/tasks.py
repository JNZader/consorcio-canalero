"""Celery maintenance tasks for the conocimiento (RAG) domain."""

from __future__ import annotations

from app.core.celery_app import celery_app


@celery_app.task(queue="celery", name="conocimiento.purgar_retencion")
def purgar_retencion_conocimiento_task() -> dict[str, int]:
    """Daily 90-day retention purge for rag_decision_ruta and rag_consulta."""
    from app.db.session import SessionLocal
    from app.domains.conocimiento.repository import (
        purgar_consultas,
        purgar_decisiones_ruta,
    )

    with SessionLocal() as db:
        decisiones = purgar_decisiones_ruta(db)
        consultas = purgar_consultas(db)
        db.commit()
        return {
            "decisiones_borradas": decisiones,
            "consultas_borradas": consultas,
        }
