"""Celery entry point for the candidate classifier. Same ``geo`` queue family.

Three lines on purpose: the protocol lives in ``clasificador_service`` so every
property it exists for — the pre-check, the fence, the private copy, the
post-copy revalidation and the single write — is exercised against a plain
function, with no broker in the way.
"""

from __future__ import annotations

import structlog

from app.core.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(queue="geo", name="geo.relevamiento.classify_road_segments")
def classify_road_segments(area_id: str, job_id: str | None = None) -> dict:
    """Write this area's DEM candidates, one generation per run.

    Refusals are named and never silent: a DEM pipeline owning the area ends the
    job FAILED with ``dem_job_running_pre_check``, and a newest DEM run that
    offers only a burned or simulated surface ends it with
    ``dem_filled_no_disponible`` rather than classifying against a −10 m
    fictional trench. A private copy that fails corroboration ends it with
    ``copia_corrupta_post_check`` — the observation, never a guess at its cause.
    A lost fence returns ``skipped`` without writing an estado of its own — the
    row already belongs to whoever won it.

    Nothing this task writes is a measurement. Every row lands in
    ``tramo_clasificacion_candidata``, labelled a candidate, keyed by this run,
    and the previous run's candidates are left exactly where they are.
    """
    from app.db.session import SessionLocal
    from app.domains.geo.relevamiento.clasificador_service import run_classification_task

    return run_classification_task(
        area_id=area_id,
        job_id=job_id,
        session_factory=SessionLocal,
    )
