"""Hand-run shortlist of GEE scenes for extreme-rainfall events.

Not a Beat schedule. Same discipline as ``detector_cli``: labelled stops,
nothing on the request path.

    docker compose exec backend python -m app.domains.geo.rainfall.imagery_shortlist_cli

The lister is injected so tests never touch Earth Engine. Production wires
``list_gee_scenes``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.domains.geo.rainfall.imagery_shortlist import (
    POST_DAYS,
    PRE_LOOKBACK_DAYS,
    SCORER_REVISION,
    SLOT_POST,
    SLOT_PRE,
    SceneHit,
    pick_anchor_scene,
    rank_scenes,
    replace_candidates,
)

SENSORS = ("sentinel2", "sentinel1", "landsat9", "landsat8", "landsat7", "landsat5")

ListScenes = Callable[[str, date, date], list[SceneHit]]

EXIT_OK = 0
EXIT_STOPPED = 1


def _peak_date(event: Any) -> date:
    raw = getattr(event, "peak_date", None) or getattr(event, "date", None)
    if isinstance(event, dict):
        raw = event.get("peak_date") or event.get("date")
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


def _event_id(event: Any) -> str:
    if isinstance(event, dict):
        return str(event["id"])
    return str(event.id)


def _start_date(event: Any) -> date:
    raw = getattr(event, "start_date", None)
    if isinstance(event, dict):
        raw = event.get("start_date") or event.get("date")
    elif raw is None:
        raw = getattr(event, "date", None)
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


def shortlist_event(
    db: Session,
    event: Any,
    *,
    list_scenes: ListScenes,
) -> list:
    peak = _peak_date(event)
    start = _start_date(event)
    window_start = start - timedelta(days=PRE_LOOKBACK_DAYS)
    window_end = peak + timedelta(days=POST_DAYS)
    hits: list[SceneHit] = []
    for sensor in SENSORS:
        hits.extend(list_scenes(sensor, window_start, window_end))
    ranked = rank_scenes(peak, hits)
    pre = pick_anchor_scene(
        hits, toward=start, peak=peak, before=True, window_days=PRE_LOOKBACK_DAYS, slot=SLOT_PRE
    )
    post = pick_anchor_scene(
        hits, toward=peak, peak=peak, before=False, window_days=POST_DAYS, slot=SLOT_POST
    )
    replace_candidates(db, _event_id(event), ranked, pre=pre, post=post)
    return ranked


def run_events(db: Session, events: list[Any], *, list_scenes: ListScenes) -> int:
    written = 0
    for event in events:
        ranked = shortlist_event(db, event, list_scenes=list_scenes)
        if ranked:
            written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score GEE scenes for extreme rainfall events")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal
    from app.domains.geo.rainfall.catalog_view import build_catalog_response
    from app.domains.geo.rainfall.imagery_shortlist_gee import list_gee_scenes
    from app.domains.geo.rainfall.repository import read_events
    from app.domains.geo.router_gee_support import CATALOG_SCOPE

    db = SessionLocal()
    try:
        generation = read_events(db, **CATALOG_SCOPE)
        payload = build_catalog_response(generation, tier="extrema")
        events = payload.get("floods") or []
        if args.dry_run:
            print(f"events={len(events)} dry_run=true")
            return EXIT_OK

        count = run_events(db, events, list_scenes=list_gee_scenes)
        db.commit()
        print(f"events_shortlisted={count} scorer={SCORER_REVISION}")
        return EXIT_OK
    except Exception as exc:
        db.rollback()
        print(f"reason=unexpected error={exc}", file=sys.stderr)
        return EXIT_STOPPED
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
