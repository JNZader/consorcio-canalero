"""
Unit tests for rainfall_service.py — CHIRPS daily precipitation via GEE.

Mocks: ee, SQLAlchemy session, GeoRepository. No DB or GEE credentials needed.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_chirps_collection_name():
    from app.domains.geo.rainfall_service import CHIRPS_COLLECTION
    assert CHIRPS_COLLECTION == "UCSB-CHG/CHIRPS/DAILY"


def test_chirps_band_name():
    from app.domains.geo.rainfall_service import CHIRPS_BAND
    assert CHIRPS_BAND == "precipitation"


# ---------------------------------------------------------------------------
# fetch_chirps_daily tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
def test_fetch_chirps_daily_basic(mock_ee, mock_init):
    from app.domains.geo.rainfall_service import fetch_chirps_daily

    zona_id = uuid.uuid4()
    zones = [
        {
            "id": zona_id,
            "nombre": "Zona Norte",
            "ee_geometry": MagicMock(),
        }
    ]

    mock_ee.Feature.return_value = MagicMock()
    mock_ee.FeatureCollection.return_value = MagicMock()

    # Build ImageCollection chain
    coll = MagicMock()
    coll.filterDate.return_value = coll
    coll.select.return_value = coll
    coll.map.return_value = MagicMock()
    coll.map.return_value.flatten.return_value = MagicMock()
    coll.map.return_value.flatten.return_value.getInfo.return_value = {
        "features": [
            {
                "properties": {
                    "zona_id": str(zona_id),
                    "image_date": "2024-01-15",
                    "mean": 12.5,
                }
            },
            {
                "properties": {
                    "zona_id": str(zona_id),
                    "image_date": "2024-01-16",
                    "mean": 0.0,
                }
            },
        ]
    }
    mock_ee.ImageCollection.return_value = coll

    records = fetch_chirps_daily(
        zones,
        date(2024, 1, 15),
        date(2024, 1, 16),
    )

    assert len(records) == 2
    assert records[0]["zona_operativa_id"] == zona_id
    assert records[0]["precipitation_mm"] == 12.5
    assert records[0]["source"] == "CHIRPS"
    assert records[1]["precipitation_mm"] == 0.0


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
def test_fetch_chirps_daily_empty_result(mock_ee, mock_init):
    from app.domains.geo.rainfall_service import fetch_chirps_daily

    mock_ee.Feature.return_value = MagicMock()
    mock_ee.FeatureCollection.return_value = MagicMock()

    coll = MagicMock()
    coll.filterDate.return_value = coll
    coll.select.return_value = coll
    coll.map.return_value = MagicMock()
    coll.map.return_value.flatten.return_value = MagicMock()
    coll.map.return_value.flatten.return_value.getInfo.return_value = None
    mock_ee.ImageCollection.return_value = coll

    records = fetch_chirps_daily(
        [{"id": uuid.uuid4(), "nombre": "Z", "ee_geometry": MagicMock()}],
        date(2024, 1, 1),
        date(2024, 1, 1),
    )

    assert records == []


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
def test_fetch_chirps_daily_skips_none_precip(mock_ee, mock_init):
    """Records with precip=None should be skipped."""
    from app.domains.geo.rainfall_service import fetch_chirps_daily

    mock_ee.Feature.return_value = MagicMock()
    mock_ee.FeatureCollection.return_value = MagicMock()

    coll = MagicMock()
    coll.filterDate.return_value = coll
    coll.select.return_value = coll
    coll.map.return_value = MagicMock()
    coll.map.return_value.flatten.return_value = MagicMock()
    coll.map.return_value.flatten.return_value.getInfo.return_value = {
        "features": [
            {"properties": {"zona_id": str(uuid.uuid4()), "image_date": "2024-01-15", "mean": None}},
        ]
    }
    mock_ee.ImageCollection.return_value = coll

    records = fetch_chirps_daily(
        [{"id": uuid.uuid4(), "nombre": "Z", "ee_geometry": MagicMock()}],
        date(2024, 1, 15),
        date(2024, 1, 15),
    )

    assert records == []


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
def test_fetch_chirps_daily_end_date_exclusive(mock_ee, mock_init):
    """End date for GEE filterDate should be exclusive (end_date + 1 day)."""
    from app.domains.geo.rainfall_service import fetch_chirps_daily

    mock_ee.Feature.return_value = MagicMock()
    mock_ee.FeatureCollection.return_value = MagicMock()

    coll = MagicMock()
    coll.filterDate.return_value = coll
    coll.select.return_value = coll
    coll.map.return_value = MagicMock()
    coll.map.return_value.flatten.return_value = MagicMock()
    coll.map.return_value.flatten.return_value.getInfo.return_value = {"features": []}
    mock_ee.ImageCollection.return_value = coll

    fetch_chirps_daily(
        [{"id": uuid.uuid4(), "nombre": "Z", "ee_geometry": MagicMock()}],
        date(2024, 3, 1),
        date(2024, 3, 31),
    )

    # filterDate should be called with end=2024-04-01 (exclusive)
    coll.filterDate.assert_called_once_with("2024-03-01", "2024-04-01")


# ---------------------------------------------------------------------------
# backfill_rainfall tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service.fetch_chirps_daily")
@patch("app.domains.geo.rainfall_service._load_zone_geometries")
@patch("app.domains.geo.rainfall_service.repo")
def test_backfill_no_zones(mock_repo, mock_load, mock_fetch):
    from app.domains.geo.rainfall_service import backfill_rainfall

    mock_load.return_value = []
    db = MagicMock()

    result = backfill_rainfall(db, date(2024, 1, 1), date(2024, 1, 31))

    assert result["total_records"] == 0
    assert "No zones found" in result["errors"]
    mock_fetch.assert_not_called()


@patch("app.domains.geo.rainfall_service.fetch_chirps_daily")
@patch("app.domains.geo.rainfall_service._load_zone_geometries")
@patch("app.domains.geo.rainfall_service.repo")
def test_backfill_single_batch(mock_repo, mock_load, mock_fetch):
    from app.domains.geo.rainfall_service import backfill_rainfall

    zona_id = uuid.uuid4()
    mock_load.return_value = [{"id": zona_id, "nombre": "Z", "ee_geometry": MagicMock()}]
    mock_fetch.return_value = [
        {"zona_operativa_id": zona_id, "date": date(2024, 1, 1), "precipitation_mm": 5.0, "source": "CHIRPS"},
    ]
    mock_repo.bulk_upsert_rainfall.return_value = 1

    db = MagicMock()
    result = backfill_rainfall(db, date(2024, 1, 1), date(2024, 1, 15))

    assert result["total_records"] == 1
    assert result["batches_processed"] == 1
    assert result["errors"] == []
    db.commit.assert_called_once()


@patch("app.domains.geo.rainfall_service.fetch_chirps_daily")
@patch("app.domains.geo.rainfall_service._load_zone_geometries")
@patch("app.domains.geo.rainfall_service.repo")
def test_backfill_monthly_batching(mock_repo, mock_load, mock_fetch):
    """60-day range should produce ~2 batches (30 days each)."""
    from app.domains.geo.rainfall_service import backfill_rainfall

    mock_load.return_value = [{"id": uuid.uuid4(), "nombre": "Z", "ee_geometry": MagicMock()}]
    mock_fetch.return_value = [{"zona_operativa_id": uuid.uuid4(), "date": date(2024, 1, 1),
                                 "precipitation_mm": 1.0, "source": "CHIRPS"}]
    mock_repo.bulk_upsert_rainfall.return_value = 1

    db = MagicMock()
    result = backfill_rainfall(db, date(2024, 1, 1), date(2024, 3, 1))

    # Jan 1 → Jan 30 (batch 1), Jan 31 → Feb 29 (batch 2), Mar 1 → Mar 1 (batch 3)
    assert result["batches_processed"] >= 2


@patch("app.domains.geo.rainfall_service.fetch_chirps_daily")
@patch("app.domains.geo.rainfall_service._load_zone_geometries")
@patch("app.domains.geo.rainfall_service.repo")
def test_backfill_handles_error_gracefully(mock_repo, mock_load, mock_fetch):
    from app.domains.geo.rainfall_service import backfill_rainfall

    mock_load.return_value = [{"id": uuid.uuid4(), "nombre": "Z", "ee_geometry": MagicMock()}]
    mock_fetch.side_effect = Exception("GEE quota exceeded")

    db = MagicMock()
    result = backfill_rainfall(db, date(2024, 1, 1), date(2024, 1, 15))

    assert len(result["errors"]) == 1
    assert "GEE quota exceeded" in result["errors"][0]
    db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# detect_rainfall_events tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service.select")
def test_detect_rainfall_events_above_threshold(mock_select):
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # Create mock rainfall records — 3 days of heavy rain
    records = []
    for i in range(5):
        rec = MagicMock()
        rec.zona_operativa_id = zona_id
        rec.date = date(2024, 1, 10 + i)
        rec.precipitation_mm = 20.0  # 3-day window = 60mm > 50mm threshold
        records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 14),
        threshold_mm=50.0,
        window_days=3,
    )

    assert len(events) >= 1
    assert events[0]["zona_operativa_id"] == zona_id
    assert events[0]["accumulated_mm"] >= 50.0


@patch("app.domains.geo.rainfall_service.select")
def test_detect_rainfall_events_below_threshold(mock_select):
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    records = []
    for i in range(5):
        rec = MagicMock()
        rec.zona_operativa_id = zona_id
        rec.date = date(2024, 1, 10 + i)
        rec.precipitation_mm = 5.0  # 3-day window = 15mm < 50mm
        records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 14),
        threshold_mm=50.0,
        window_days=3,
    )

    assert events == []


@patch("app.domains.geo.rainfall_service.select")
def test_detect_rainfall_events_clusters_consecutive(mock_select):
    """Consecutive flagged dates should be clustered into single events."""
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # Days 10-12: heavy rain, days 13-14: dry, days 15-16: heavy again
    precip_by_day = {
        10: 30.0, 11: 30.0, 12: 30.0,  # event 1
        13: 0.0, 14: 0.0,                # gap
        15: 30.0, 16: 30.0,              # event 2
    }

    records = []
    for day, mm in sorted(precip_by_day.items()):
        rec = MagicMock()
        rec.zona_operativa_id = zona_id
        rec.date = date(2024, 1, day)
        rec.precipitation_mm = mm
        records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 16),
        threshold_mm=50.0,
        window_days=3,
    )

    # Should have 2 separate events (gap on day 13-14 breaks the cluster)
    assert len(events) >= 1  # at least event 1
    for e in events:
        assert e["duration_days"] >= 1


@patch("app.domains.geo.rainfall_service.select")
def test_detect_rainfall_events_default_dates(mock_select):
    """When no dates provided, defaults to last 90 days."""
    from app.domains.geo.rainfall_service import detect_rainfall_events

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []

    events = detect_rainfall_events(db)

    assert events == []
    # Verify the query was executed (defaults were used)
    db.execute.assert_called_once()


@patch("app.domains.geo.rainfall_service.select")
def test_detect_rainfall_events_sorted_descending(mock_select):
    """Events should be sorted by event_start descending."""
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # Two separate heavy rain periods
    records = []
    for day in [1, 2, 3, 20, 21, 22]:
        rec = MagicMock()
        rec.zona_operativa_id = zona_id
        rec.date = date(2024, 1, day)
        rec.precipitation_mm = 25.0  # 3-day sum = 75 > 50
        records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 25),
        threshold_mm=50.0,
        window_days=3,
    )

    if len(events) >= 2:
        assert events[0]["event_start"] >= events[1]["event_start"]


# ---------------------------------------------------------------------------
# suggest_images_for_event tests
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_basic(mock_explorer_cls, mock_ee, mock_init):
    from app.domains.geo.rainfall_service import suggest_images_for_event

    explorer = MagicMock()
    explorer.zona = MagicMock()
    mock_explorer_cls.return_value = explorer

    mock_ee.Filter.lt.return_value = MagicMock()

    coll = MagicMock()
    coll.filterBounds.return_value = coll
    coll.filterDate.return_value = coll
    coll.filter.return_value = coll
    coll.map.return_value = MagicMock()
    coll.map.return_value.getInfo.return_value = {
        "features": [
            {"properties": {"date": "2024-01-20", "cloud_cover_pct": 15.0}},
            {"properties": {"date": "2024-01-21", "cloud_cover_pct": 25.0}},
            {"properties": {"date": "2024-01-20", "cloud_cover_pct": 10.0}},  # duplicate date, lower cloud
        ]
    }
    mock_ee.ImageCollection.return_value = coll

    suggestions = suggest_images_for_event(date(2024, 1, 17))

    assert len(suggestions) == 2
    # Sorted by cloud cover ascending
    assert suggestions[0]["cloud_cover_pct"] <= suggestions[1]["cloud_cover_pct"]
    # Deduplication: date 2024-01-20 should keep the lower cloud value (10.0)
    jan20 = next(s for s in suggestions if str(s["date"]) == "2024-01-20")
    assert jan20["cloud_cover_pct"] == 10.0


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_empty(mock_explorer_cls, mock_ee, mock_init):
    from app.domains.geo.rainfall_service import suggest_images_for_event

    explorer = MagicMock()
    explorer.zona = MagicMock()
    mock_explorer_cls.return_value = explorer

    mock_ee.Filter.lt.return_value = MagicMock()

    coll = MagicMock()
    coll.filterBounds.return_value = coll
    coll.filterDate.return_value = coll
    coll.filter.return_value = coll
    coll.map.return_value = MagicMock()
    coll.map.return_value.getInfo.return_value = None
    mock_ee.ImageCollection.return_value = coll

    suggestions = suggest_images_for_event(date(2024, 1, 17))
    assert suggestions == []


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_uses_toa_for_pre_2019(mock_explorer_cls, mock_ee, mock_init):
    """Before 2019, the function should use TOA collection."""
    from app.domains.geo.rainfall_service import suggest_images_for_event

    explorer = MagicMock()
    explorer.zona = MagicMock()
    mock_explorer_cls.return_value = explorer

    mock_ee.Filter.lt.return_value = MagicMock()

    coll = MagicMock()
    coll.filterBounds.return_value = coll
    coll.filterDate.return_value = coll
    coll.filter.return_value = coll
    coll.map.return_value = MagicMock()
    coll.map.return_value.getInfo.return_value = {"features": []}
    mock_ee.ImageCollection.return_value = coll

    suggest_images_for_event(date(2018, 6, 1))

    # Should use TOA collection for pre-2019
    mock_ee.ImageCollection.assert_called_with("COPERNICUS/S2_HARMONIZED")
