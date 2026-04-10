"""Hydromet Celery tasks for rainfall backfill and NDWI baselines."""

from __future__ import annotations

import uuid

import structlog

from app.core.celery_app import celery_app
from app.db.session import SessionLocal

logger = structlog.get_logger(__name__)


def _get_db():
    return SessionLocal()


# ---------------------------------------------------------------------------
# RAINFALL — CHIRPS backfill & daily sync
# ---------------------------------------------------------------------------


@celery_app.task(
    queue="geo",
    name="geo.rainfall_backfill",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def rainfall_backfill(
    self,
    start_date: str,
    end_date: str,
    zona_ids: list[str] | None = None,
    source: str = "CHIRPS",
) -> dict:
    """Backfill rainfall data in monthly batches.

    Args:
        start_date: ISO date string (inclusive).
        end_date: ISO date string (inclusive).
        zona_ids: Optional list of zona UUID strings. None = all zones.
        source: "CHIRPS" (default) or "IMERG".
    """
    from datetime import date as date_type

    from app.domains.geo.rainfall_service import backfill_rainfall

    db = _get_db()
    try:
        parsed_start = date_type.fromisoformat(start_date)
        parsed_end = date_type.fromisoformat(end_date)
        parsed_zona_ids = [uuid.UUID(z) for z in zona_ids] if zona_ids else None

        def _on_batch(current: int, total: int, records: int) -> None:
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": current,
                    "total": total,
                    "records": records,
                    "source": source,
                },
            )

        result = backfill_rainfall(
            db,
            start_date=parsed_start,
            end_date=parsed_end,
            zona_ids=parsed_zona_ids,
            source=source,
            on_batch_complete=_on_batch,
        )
        logger.info(
            "rainfall_backfill.done",
            total_records=result["total_records"],
            batches=result["batches_processed"],
        )
        return result
    except Exception as exc:
        logger.error("rainfall_backfill.failed", exc_info=True)
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


@celery_app.task(
    queue="geo",
    name="geo.compute_ndwi_baselines",
    bind=True,
    max_retries=2,
)
def compute_ndwi_baselines_task(
    self,
    zona_ids: list[str] | None = None,
    dry_season_months: list[int] | None = None,
    years_back: int = 3,
) -> dict:
    """Compute NDWI dry-season baselines per zona and persist to DB.

    Args:
        zona_ids: Optional list of zona UUID strings. None = all zones.
        dry_season_months: Month numbers for dry season. None = [6,7,8].
        years_back: Years of S2 history to use (default 3).
    """
    from app.domains.geo.gee_service import compute_ndwi_baselines_gee
    from app.domains.geo.rainfall_service import _load_zone_geometries
    from app.domains.geo.models import NdwiBaseline
    from datetime import datetime, timezone

    db = _get_db()
    try:
        parsed_zona_ids = [uuid.UUID(z) for z in zona_ids] if zona_ids else None
        zones = _load_zone_geometries(db, parsed_zona_ids)

        if not zones:
            return {"processed": 0, "failed": 0, "error": "No zones found"}

        self.update_state(
            state="PROGRESS",
            meta={"status": "computing", "total_zones": len(zones)},
        )

        results = compute_ndwi_baselines_gee(
            zones,
            dry_season_months=dry_season_months,
            years_back=years_back,
        )

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        processed = 0
        for r in results:
            now = datetime.now(timezone.utc)
            stmt = pg_insert(NdwiBaseline).values(
                zona_operativa_id=uuid.UUID(r["zona_id"]),
                ndwi_mean=r["ndwi_mean"],
                ndwi_std=r["ndwi_std"],
                sample_count=r["sample_count"],
                dry_season_months=dry_season_months or [6, 7, 8],
                years_back=years_back,
                computed_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["zona_operativa_id"],
                set_={
                    "ndwi_mean": stmt.excluded.ndwi_mean,
                    "ndwi_std": stmt.excluded.ndwi_std,
                    "sample_count": stmt.excluded.sample_count,
                    "dry_season_months": stmt.excluded.dry_season_months,
                    "years_back": stmt.excluded.years_back,
                    "computed_at": stmt.excluded.computed_at,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            db.execute(stmt)
            processed += 1

        db.commit()
        failed = len(zones) - len(results)

        logger.info(
            "compute_ndwi_baselines.done",
            processed=processed,
            failed=failed,
        )
        return {"processed": processed, "failed": failed}

    except Exception as exc:
        db.rollback()
        logger.error("compute_ndwi_baselines.failed", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1)) from exc
    finally:
        db.close()


@celery_app.task(queue="geo", name="geo.rainfall_daily_sync")
def rainfall_daily_sync() -> dict:
    """Daily cron task: sync yesterday's CHIRPS data for all active zones."""
    from datetime import date as date_type, timedelta as td

    from app.domains.geo.rainfall_service import backfill_rainfall

    db = _get_db()
    try:
        yesterday = date_type.today() - td(days=1)
        result = backfill_rainfall(db, start_date=yesterday, end_date=yesterday)
        logger.info(
            "rainfall_daily_sync.done",
            date=yesterday.isoformat(),
            records=result["total_records"],
        )
        return result
    finally:
        db.close()
