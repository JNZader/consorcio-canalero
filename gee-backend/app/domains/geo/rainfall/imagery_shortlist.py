"""Score and persist a shortlist of satellite scenes for one extreme event.

Cloud percentage is the **scene metadata** field (S2 ``CLOUDY_PIXEL_PERCENTAGE``,
Landsat ``CLOUD_COVER``). That is not cloud-over-the-zone. SAR has no cloud
field; its cloud term is 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domains.geo.rainfall.models import RainfallEventImageryCandidate

SCORER_REVISION = "imgcand-3"
CLOUD_BASIS = "scene_metadata"
TOP_N = 12
POST_DAYS = 10
PRE_DAYS = 2
PRE_LOOKBACK_DAYS = 30
CLOUD_REF = 80.0
SLOT_RANKED = "ranked"
SLOT_PRE = "pre"
SLOT_POST = "post"

SENSOR_WEIGHT: dict[str, float] = {
    "sentinel2": 1.0,
    "sentinel1": 0.9,
    "landsat8": 0.55,
    "landsat7": 0.35,
    "landsat5": 0.35,
}

_VISUALIZATION = {
    "sentinel1": "vv_flood",
}


@dataclass(frozen=True)
class SceneHit:
    sensor: str
    scene_id: str
    scene_date: date
    cloud_pct: float | None


@dataclass(frozen=True)
class RankedScene:
    sensor: str
    scene_id: str
    scene_date: date
    cloud_pct: float | None
    days_from_peak: int
    score: float
    rank: int
    slot: str = SLOT_RANKED
    scorer_revision: str = SCORER_REVISION
    cloud_basis: str = CLOUD_BASIS

    @property
    def visualization(self) -> str:
        return _VISUALIZATION.get(self.sensor, "rgb")


def _in_window(days_from_peak: int) -> bool:
    return -PRE_DAYS <= days_from_peak <= POST_DAYS


def _cloud_term(sensor: str, cloud_pct: float | None) -> float:
    if sensor == "sentinel1":
        return 1.0
    if cloud_pct is None:
        return 0.0
    return max(0.0, 1.0 - min(cloud_pct, CLOUD_REF) / CLOUD_REF)


def _time_term(days_from_peak: int) -> float:
    if days_from_peak >= 0:
        return max(0.0, 1.0 - days_from_peak / POST_DAYS)
    return 0.65 * max(0.0, 1.0 - abs(days_from_peak) / PRE_DAYS)


def score_hit(peak: date, hit: SceneHit) -> float:
    days = (hit.scene_date - peak).days
    weight = SENSOR_WEIGHT.get(hit.sensor, 0.2)
    return round(100.0 * weight * _time_term(days) * _cloud_term(hit.sensor, hit.cloud_pct), 4)


def rank_scenes(peak: date, hits: Sequence[SceneHit], *, top_n: int = TOP_N) -> list[RankedScene]:
    scored: list[tuple[float, SceneHit, int]] = []
    for hit in hits:
        days = (hit.scene_date - peak).days
        if not _in_window(days):
            continue
        scored.append((score_hit(peak, hit), hit, days))
    scored.sort(key=lambda item: (-item[0], -item[2], item[1].sensor, item[1].scene_id))
    ranked: list[RankedScene] = []
    seen: set[str] = set()
    for score, hit, days in scored:
        if hit.scene_id in seen:
            continue
        seen.add(hit.scene_id)
        ranked.append(
            RankedScene(
                sensor=hit.sensor,
                scene_id=hit.scene_id,
                scene_date=hit.scene_date,
                cloud_pct=hit.cloud_pct,
                days_from_peak=days,
                score=score,
                rank=len(ranked) + 1,
            )
        )
        if len(ranked) >= top_n:
            break
    return ranked


def pick_anchor_scene(
    hits: Sequence[SceneHit],
    *,
    toward: date,
    peak: date,
    before: bool,
    window_days: int,
    slot: str,
) -> RankedScene | None:
    """Best single scene before ``toward`` (pre) or on/after it (post)."""
    scored: list[tuple[float, SceneHit]] = []
    for hit in hits:
        delta = (hit.scene_date - toward).days
        if before:
            if not (-window_days <= delta < 0):
                continue
            recency = 1.0 - abs(delta) / window_days
        else:
            if not (0 <= delta <= window_days):
                continue
            recency = 1.0 - delta / window_days if window_days else 1.0
        weight = SENSOR_WEIGHT.get(hit.sensor, 0.2)
        score = round(100.0 * weight * recency * _cloud_term(hit.sensor, hit.cloud_pct), 4)
        scored.append((score, hit))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1].scene_id))
    score, hit = scored[0]
    return RankedScene(
        sensor=hit.sensor,
        scene_id=hit.scene_id,
        scene_date=hit.scene_date,
        cloud_pct=hit.cloud_pct,
        days_from_peak=(hit.scene_date - peak).days,
        score=score,
        rank=1,
        slot=slot,
    )


def _candidate_from_ranked(event_key: str, item: RankedScene) -> RainfallEventImageryCandidate:
    return RainfallEventImageryCandidate(
        event_key=event_key,
        scorer_revision=item.scorer_revision,
        sensor=item.sensor,
        scene_id=item.scene_id,
        scene_date=item.scene_date,
        days_from_peak=item.days_from_peak,
        cloud_pct=item.cloud_pct,
        cloud_basis=item.cloud_basis,
        score=item.score,
        rank=item.rank,
        visualization=item.visualization,
        slot=item.slot,
    )


def replace_candidates(
    db: Session,
    event_key: str,
    ranked: Sequence[RankedScene],
    *,
    pre: RankedScene | None = None,
    post: RankedScene | None = None,
) -> list[RainfallEventImageryCandidate]:
    db.execute(
        delete(RainfallEventImageryCandidate).where(
            RainfallEventImageryCandidate.event_key == event_key
        )
    )
    rows: list[RainfallEventImageryCandidate] = []
    for item in ranked:
        row = _candidate_from_ranked(event_key, item)
        db.add(row)
        rows.append(row)
    for extra in (pre, post):
        if extra is None:
            continue
        row = _candidate_from_ranked(event_key, extra)
        db.add(row)
        rows.append(row)
    return rows


def load_candidates(db: Session, event_key: str) -> list[RainfallEventImageryCandidate]:
    return list(
        db.scalars(
            select(RainfallEventImageryCandidate)
            .where(RainfallEventImageryCandidate.event_key == event_key)
            .where(RainfallEventImageryCandidate.slot == SLOT_RANKED)
            .order_by(RainfallEventImageryCandidate.rank)
        ).all()
    )


def load_all_shortlists(db: Session) -> dict[str, list[RainfallEventImageryCandidate]]:
    rows = db.scalars(
        select(RainfallEventImageryCandidate)
        .where(RainfallEventImageryCandidate.slot == SLOT_RANKED)
        .order_by(
            RainfallEventImageryCandidate.event_key,
            RainfallEventImageryCandidate.rank,
        )
    ).all()
    grouped: dict[str, list[RainfallEventImageryCandidate]] = {}
    for row in rows:
        grouped.setdefault(row.event_key, []).append(row)
    return grouped


def load_all_pairs(db: Session) -> dict[str, dict[str, RainfallEventImageryCandidate | None]]:
    rows = db.scalars(
        select(RainfallEventImageryCandidate).where(
            RainfallEventImageryCandidate.slot.in_((SLOT_PRE, SLOT_POST))
        )
    ).all()
    pairs: dict[str, dict[str, RainfallEventImageryCandidate | None]] = {}
    for row in rows:
        bucket = pairs.setdefault(row.event_key, {SLOT_PRE: None, SLOT_POST: None})
        bucket[row.slot] = row
    return pairs


def _row_public(row: RainfallEventImageryCandidate) -> dict:
    return {
        "rank": row.rank,
        "sensor": row.sensor,
        "scene_id": row.scene_id,
        "scene_date": row.scene_date.isoformat(),
        "days_from_peak": row.days_from_peak,
        "cloud_pct": row.cloud_pct,
        "score": row.score,
        "visualization": row.visualization,
        "slot": row.slot,
    }


def all_shortlists_payload(
    grouped: dict[str, list[RainfallEventImageryCandidate]],
    pairs: dict[str, dict[str, RainfallEventImageryCandidate | None]] | None = None,
) -> dict:
    pair_payload = {}
    for event_id, bucket in (pairs or {}).items():
        pair_payload[event_id] = {
            SLOT_PRE: _row_public(bucket[SLOT_PRE]) if bucket.get(SLOT_PRE) else None,
            SLOT_POST: _row_public(bucket[SLOT_POST]) if bucket.get(SLOT_POST) else None,
        }
    return {
        "scorer_revision": SCORER_REVISION,
        "cloud_basis": CLOUD_BASIS,
        "shortlists": {
            event_id: payload_from_rows(event_id, rows)["candidates"]
            for event_id, rows in grouped.items()
        },
        "pairs": pair_payload,
    }


def shortlist_payload(event_id: str, ranked: Sequence[RankedScene]) -> dict:
    return {
        "event_id": event_id,
        "scorer_revision": SCORER_REVISION,
        "cloud_basis": CLOUD_BASIS,
        "candidates": [
            {
                "rank": item.rank,
                "sensor": item.sensor,
                "scene_id": item.scene_id,
                "scene_date": item.scene_date.isoformat(),
                "days_from_peak": item.days_from_peak,
                "cloud_pct": item.cloud_pct,
                "score": item.score,
                "visualization": item.visualization,
            }
            for item in ranked
        ],
    }


def payload_from_rows(event_id: str, rows: Sequence[RainfallEventImageryCandidate]) -> dict:
    return {
        "event_id": event_id,
        "scorer_revision": rows[0].scorer_revision if rows else SCORER_REVISION,
        "cloud_basis": CLOUD_BASIS,
        "candidates": [
            {
                "rank": row.rank,
                "sensor": row.sensor,
                "scene_id": row.scene_id,
                "scene_date": row.scene_date.isoformat(),
                "days_from_peak": row.days_from_peak,
                "cloud_pct": row.cloud_pct,
                "score": row.score,
                "visualization": row.visualization,
            }
            for row in rows
        ],
    }
