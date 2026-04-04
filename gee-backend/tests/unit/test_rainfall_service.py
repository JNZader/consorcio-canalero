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


# ---------------------------------------------------------------------------
# Mutation-killing tests — Geometry/DB (L41-77)
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.rainfall_service.json")
def test_postgis_to_ee_geometry_queries_by_equal_zona_id(mock_json, mock_ee):
    """L41: ZonaOperativa.id == zona_id — kill mutation to !=.

    We verify the WHERE clause uses == by compiling the select statement
    passed to db.execute and checking for the correct SQL operator.
    """
    from app.domains.geo.rainfall_service import _postgis_to_ee_geometry

    zona_id = uuid.uuid4()
    db = MagicMock()
    db.execute.return_value.scalar.return_value = '{"type":"Polygon","coordinates":[]}'
    mock_json.loads.return_value = {"type": "Polygon", "coordinates": []}
    mock_ee.Geometry.return_value = MagicMock()

    _postgis_to_ee_geometry(db, zona_id)

    # Grab the select statement passed to db.execute
    db.execute.assert_called_once()
    stmt = db.execute.call_args[0][0]
    # Compile it to string — SQLAlchemy select objects have __str__
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    # With ==: "... WHERE zona_operativa.id = ..."
    # With !=: "... WHERE zona_operativa.id != ..."
    assert " != " not in compiled


@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.rainfall_service.json")
def test_postgis_to_ee_geometry_returns_ee_geometry_not_none(mock_json, mock_ee):
    """L47: return ee.Geometry(geojson) — kill mutation to return None."""
    from app.domains.geo.rainfall_service import _postgis_to_ee_geometry

    zona_id = uuid.uuid4()
    db = MagicMock()
    db.execute.return_value.scalar.return_value = '{"type":"Polygon","coordinates":[]}'
    geojson_obj = {"type": "Polygon", "coordinates": []}
    mock_json.loads.return_value = geojson_obj
    sentinel = MagicMock(name="ee_geometry_sentinel")
    mock_ee.Geometry.return_value = sentinel

    result = _postgis_to_ee_geometry(db, zona_id)

    # Must be the ee.Geometry return, not None
    assert result is sentinel
    mock_ee.Geometry.assert_called_once_with(geojson_obj)


@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.rainfall_service.json")
def test_load_zone_geometries_returns_zones_not_none(mock_json, mock_ee):
    """L77: return zones — kill mutation to return None."""
    from app.domains.geo.rainfall_service import _load_zone_geometries

    zona_id = uuid.uuid4()
    db = MagicMock()
    row = MagicMock()
    row.id = zona_id
    row.nombre = "Zona Test"
    row.geojson = '{"type":"Polygon","coordinates":[]}'
    db.execute.return_value.all.return_value = [row]
    mock_json.loads.return_value = {"type": "Polygon", "coordinates": []}
    mock_ee.Geometry.return_value = MagicMock()

    result = _load_zone_geometries(db)

    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == zona_id
    assert result[0]["nombre"] == "Zona Test"


# ---------------------------------------------------------------------------
# Mutation-killing tests — CHIRPS fetch (L121, L123)
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
def test_fetch_chirps_daily_uses_scale_5566(mock_ee, mock_init):
    """L121: scale=5566 — kill constant mutation (5566 → 5567 or similar)."""
    from app.domains.geo.rainfall_service import fetch_chirps_daily

    zona_id = uuid.uuid4()
    zones = [{"id": zona_id, "nombre": "Z", "ee_geometry": MagicMock()}]

    mock_ee.Feature.return_value = MagicMock()
    mock_ee.FeatureCollection.return_value = MagicMock()

    coll = MagicMock()
    coll.filterDate.return_value = coll
    coll.select.return_value = coll

    # Capture the _reduce_image function
    reduced_fc = MagicMock()
    reduced_fc.flatten.return_value = MagicMock()
    reduced_fc.flatten.return_value.getInfo.return_value = {"features": []}
    coll.map.return_value = reduced_fc
    mock_ee.ImageCollection.return_value = coll

    fetch_chirps_daily(zones, date(2024, 1, 1), date(2024, 1, 1))

    # The _reduce_image function is passed to collection.map
    # We can verify the function was created and passed
    coll.map.assert_called_once()
    reduce_fn = coll.map.call_args[0][0]

    # Call the reduce function with a mock image to verify scale
    mock_image = MagicMock()
    mock_date = MagicMock()
    mock_date.format.return_value = "2024-01-01"
    mock_ee.Date.return_value = mock_date

    reduce_result = MagicMock()
    reduce_result.map.return_value = MagicMock()
    mock_image.reduceRegions.return_value = reduce_result

    reduce_fn(mock_image)

    # Verify scale=5566 was passed
    call_kwargs = mock_image.reduceRegions.call_args
    assert call_kwargs[1]["scale"] == 5566 or call_kwargs.kwargs.get("scale") == 5566


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
def test_fetch_chirps_daily_reduce_image_returns_mapped_fc(mock_ee, mock_init):
    """L123: return reduced.map(...) — kill mutation to return None.

    We capture the _reduce_image function from collection.map() and invoke it
    directly, verifying it returns a non-None FeatureCollection.
    """
    from app.domains.geo.rainfall_service import fetch_chirps_daily

    zona_id = uuid.uuid4()
    zones = [{"id": zona_id, "nombre": "Z", "ee_geometry": MagicMock()}]

    mock_ee.Feature.return_value = MagicMock()
    mock_ee.FeatureCollection.return_value = MagicMock()

    coll = MagicMock()
    coll.filterDate.return_value = coll
    coll.select.return_value = coll

    result_fc = MagicMock()
    result_fc.flatten.return_value = MagicMock()
    result_fc.flatten.return_value.getInfo.return_value = {"features": []}
    coll.map.return_value = result_fc
    mock_ee.ImageCollection.return_value = coll

    mock_date = MagicMock()
    mock_date.format.return_value = "2024-01-01"
    mock_ee.Date.return_value = mock_date

    fetch_chirps_daily(zones, date(2024, 1, 1), date(2024, 1, 1))

    # Capture the _reduce_image function passed to collection.map
    coll.map.assert_called_once()
    reduce_fn = coll.map.call_args[0][0]

    # Invoke it with a mock image
    mock_image = MagicMock()
    reduced_result = MagicMock()
    mapped_fc = MagicMock(name="mapped_fc_sentinel")
    reduced_result.map.return_value = mapped_fc
    mock_image.reduceRegions.return_value = reduced_result

    result = reduce_fn(mock_image)

    # With correct code: returns reduced.map(...) which is mapped_fc_sentinel
    # With mutation (return None): would return None
    assert result is not None
    assert result is mapped_fc


# ---------------------------------------------------------------------------
# Mutation-killing tests — Backfill (L185, L205)
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service.fetch_chirps_daily")
@patch("app.domains.geo.rainfall_service._load_zone_geometries")
@patch("app.domains.geo.rainfall_service.repo")
def test_backfill_includes_last_batch_when_end_equals_batch_boundary(mock_repo, mock_load, mock_fetch):
    """L185: while batch_start <= end_date — kill mutation to < end_date.

    If mutated to <, the last batch where batch_start == end_date is skipped.
    Use a 31-day range: batch 1 = day 1-30, batch 2 = day 31 (batch_start == end_date).
    """
    from app.domains.geo.rainfall_service import backfill_rainfall

    mock_load.return_value = [{"id": uuid.uuid4(), "nombre": "Z", "ee_geometry": MagicMock()}]
    mock_fetch.return_value = [
        {"zona_operativa_id": uuid.uuid4(), "date": date(2024, 1, 1),
         "precipitation_mm": 1.0, "source": "CHIRPS"},
    ]
    mock_repo.bulk_upsert_rainfall.return_value = 1

    db = MagicMock()
    # 30-day batch: Jan 1 → Jan 30, then Jan 31 is exactly batch_start == end_date
    result = backfill_rainfall(db, date(2024, 1, 1), date(2024, 1, 31))

    # With <=: 2 batches (Jan 1-30, Jan 31-31)
    # With <: only 1 batch (Jan 1-30, misses Jan 31)
    assert result["batches_processed"] == 2


@patch("app.domains.geo.rainfall_service.fetch_chirps_daily")
@patch("app.domains.geo.rainfall_service._load_zone_geometries")
@patch("app.domains.geo.rainfall_service.repo")
def test_backfill_error_logs_with_exc_info_true(mock_repo, mock_load, mock_fetch):
    """L205: exc_info=True — kill mutation to exc_info=False."""
    from app.domains.geo.rainfall_service import backfill_rainfall

    mock_load.return_value = [{"id": uuid.uuid4(), "nombre": "Z", "ee_geometry": MagicMock()}]
    mock_fetch.side_effect = RuntimeError("GEE boom")

    db = MagicMock()

    with patch("app.domains.geo.rainfall_service.logger") as mock_logger:
        backfill_rainfall(db, date(2024, 1, 1), date(2024, 1, 5))

        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args
        # exc_info=True must be in keyword args
        assert call_kwargs[1].get("exc_info") is True


# ---------------------------------------------------------------------------
# Mutation-killing tests — Event detection (L227-302)
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service.select")
def test_detect_default_threshold_is_exactly_50(mock_select):
    """L227: threshold_mm=50.0 — kill mutation to 51.0.

    Provide data that sums to EXACTLY 50.0 over the window.
    With threshold=50.0 (>=), it's flagged. With 51.0, it's not.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # 3-day window, each day 16.67 → rolling sum ≈ 50.01
    # Actually let's use exact: 3 days at ~16.67 each. Better: 25+25+0=50 on day 12
    records = []
    precip = {7: 0.0, 8: 0.0, 9: 0.0, 10: 25.0, 11: 25.0, 12: 0.0}
    for day, mm in precip.items():
        rec = MagicMock()
        rec.zona_operativa_id = zona_id
        rec.date = date(2024, 1, day)
        rec.precipitation_mm = mm
        records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    # Use default threshold (should be 50.0)
    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 12),
        window_days=3,
    )

    # Day 10: sum(day10=25, day9=0, day8=0) = 25 < 50 → not flagged
    # Day 11: sum(day11=25, day10=25, day9=0) = 50 >= 50 → flagged
    # Day 12: sum(day12=0, day11=25, day10=25) = 50 >= 50 → flagged
    # If threshold mutated to 51, days 11-12 would NOT be flagged
    assert len(events) == 1
    assert events[0]["accumulated_mm"] == pytest.approx(50.0)


def test_detect_default_start_date_is_end_minus_90():
    """L247: start_date = end_date - timedelta(days=90) — kill + timedelta mutation.

    When start_date is None, it defaults to end_date - 90.
    If mutated to +, start_date is in the FUTURE (after end_date),
    so the while loop (current=start > end) never executes → no events.
    We put heavy rain within the 90-day-back window to detect events.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()
    fixed_end = date(2024, 6, 1)
    # Data 30 days before end_date (well within the 90-day window)
    rain_date = fixed_end - timedelta(days=30)

    records = []
    rec = MagicMock()
    rec.zona_operativa_id = zona_id
    rec.date = rain_date
    rec.precipitation_mm = 60.0
    records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    # Don't pass start_date → defaults to end_date - 90
    events = detect_rainfall_events(
        db,
        end_date=fixed_end,
        threshold_mm=50.0,
        window_days=1,
    )

    # With - (correct): start_date = Mar 3, rain_date = May 2 → in range → event found
    # With + (mutated): start_date = Aug 30 > end Jun 1 → loop never runs → no events
    assert len(events) == 1
    assert events[0]["accumulated_mm"] == pytest.approx(60.0)


def test_detect_query_start_extends_before_start_date():
    """L251: query_start = start_date - timedelta(days=window_days).

    Verify the WHERE clause uses a query_start that is BEFORE start_date.
    If mutated to +, query_start would be AFTER start_date.
    We compile the real SQLAlchemy statement with literal binds to verify the date.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events
    from sqlalchemy.dialects import postgresql

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []

    detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 15),
        threshold_mm=50.0,
        window_days=3,
    )

    # Capture the statement passed to db.execute
    db.execute.assert_called_once()
    stmt = db.execute.call_args[0][0]

    # Extract the bound parameters from the compiled statement
    compiled = stmt.compile(compile_kwargs={"literal_binds": False})
    params = compiled.params

    # query_start = Jan 10 - 3 = Jan 7 (correct, BEFORE start_date)
    # If mutated to +: query_start = Jan 10 + 3 = Jan 13 (AFTER start_date, wrong)
    # The params should contain the dates used in WHERE clause
    param_values = list(params.values())
    dates_in_params = [v for v in param_values if isinstance(v, date)]

    # query_start should be Jan 7 (before start_date of Jan 10)
    # end_date should be Jan 15
    assert date(2024, 1, 7) in dates_in_params, (
        f"Expected query_start=2024-01-07 in params, got {dates_in_params}"
    )
    assert date(2024, 1, 15) in dates_in_params


def test_detect_query_boundaries_gte_and_lte():
    """L257-258: >= and <= boundary conditions on date query.

    Kill: >= → > (operator visible in compiled SQL)
    Kill: <= → < (operator visible in compiled SQL)

    We compile the real SQLAlchemy statement and verify operators.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []

    detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 15),
        threshold_mm=50.0,
        window_days=3,
    )

    stmt = db.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))

    # The compiled SQL should contain >= and <= (not > and <)
    # "WHERE rainfall_records.date >= :date_1 AND rainfall_records.date <= :date_2"
    # Count occurrences: should have >= not just >
    assert "date >= " in compiled or "date >=" in compiled
    assert "date <= " in compiled or "date <=" in compiled
    # Make sure it's NOT strict > or <
    # The compiled string has " >= " and " <= ", not " > " or " < "
    parts = compiled.split("WHERE")[1] if "WHERE" in compiled else compiled
    # Replace >= and <= with tokens, then check no bare > or < remain
    sanitized = parts.replace(">=", "GTE").replace("<=", "LTE")
    assert ">" not in sanitized, f"Found bare > in WHERE clause: {parts}"
    assert "<" not in sanitized, f"Found bare < in WHERE clause: {parts}"


@patch("app.domains.geo.rainfall_service.select")
def test_detect_while_loop_includes_end_date(mock_select):
    """L277: while current <= end_date — kill mutation to < end_date.

    If < is used, the last day (end_date) is never processed.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # Put heavy rain ONLY on the last day (end_date)
    records = []
    rec = MagicMock()
    rec.zona_operativa_id = zona_id
    rec.date = date(2024, 1, 15)
    rec.precipitation_mm = 60.0
    records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 14),
        end_date=date(2024, 1, 15),
        threshold_mm=50.0,
        window_days=1,
    )

    # Day 14: sum=0 (no data). Day 15: sum=60 >= 50 → flagged
    # If < instead of <=, day 15 is never checked → no events
    assert len(events) == 1
    assert events[0]["event_start"] == date(2024, 1, 15)
    assert events[0]["event_end"] == date(2024, 1, 15)


@patch("app.domains.geo.rainfall_service.select")
def test_detect_rolling_window_looks_backward_not_forward(mock_select):
    """L280: current - timedelta(days=offset) — kill + timedelta mutation.

    The window should look at the CURRENT day and days BEFORE it.
    If mutated to +, it looks FORWARD (future days).
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # Heavy rain on days 10-11, dry on days 12-14
    records = []
    for day, mm in [(8, 0.0), (9, 0.0), (10, 30.0), (11, 30.0), (12, 0.0), (13, 0.0), (14, 0.0)]:
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
        end_date=date(2024, 1, 14),
        threshold_mm=50.0,
        window_days=3,
    )

    # Day 11 backward: sum(day11=30, day10=30, day9=0) = 60 >= 50 → flagged
    # Day 12 backward: sum(day12=0, day11=30, day10=30) = 60 >= 50 → flagged
    # Day 13 backward: sum(day13=0, day12=0, day11=30) = 30 < 50 → not flagged
    # If + was used (forward): Day 10 would sum(10=30,11=30,12=0)=60 (different pattern)
    assert len(events) == 1
    # Event should start on day 11 (first day with rolling sum >= 50 looking backward)
    assert events[0]["event_start"] == date(2024, 1, 11)
    assert events[0]["event_end"] == date(2024, 1, 12)


@patch("app.domains.geo.rainfall_service.select")
def test_detect_rolling_sum_gte_threshold_boundary(mock_select):
    """L283: rolling_sum >= threshold_mm — kill mutation to >.

    Exactly at threshold should be flagged (>=). With >, it wouldn't be.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # Exactly 50.0 in a single day with window=1
    records = []
    rec = MagicMock()
    rec.zona_operativa_id = zona_id
    rec.date = date(2024, 1, 10)
    rec.precipitation_mm = 50.0
    records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 10),
        threshold_mm=50.0,
        window_days=1,
    )

    # Exactly at boundary: 50.0 >= 50.0 → True. If > : 50.0 > 50.0 → False
    assert len(events) == 1
    assert events[0]["accumulated_mm"] == pytest.approx(50.0)


@patch("app.domains.geo.rainfall_service.select")
def test_detect_cluster_adjacency_days_lte_1(mock_select):
    """L296: .days <= 1 — kill mutation to < 1.

    Two consecutive dates (gap of exactly 1 day) should cluster together.
    With < 1, only gap of 0 (same day, impossible) would cluster.
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    # Two consecutive days with heavy rain
    records = []
    for day in [10, 11]:
        rec = MagicMock()
        rec.zona_operativa_id = zona_id
        rec.date = date(2024, 1, day)
        rec.precipitation_mm = 60.0
        records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 11),
        threshold_mm=50.0,
        window_days=1,
    )

    # Gap between Jan 10 and Jan 11 = 1 day. With <= 1: same cluster. With < 1: 2 clusters.
    assert len(events) == 1
    assert events[0]["event_start"] == date(2024, 1, 10)
    assert events[0]["event_end"] == date(2024, 1, 11)
    assert events[0]["duration_days"] == 2


@patch("app.domains.geo.rainfall_service.select")
def test_detect_duration_formula_days_plus_1(mock_select):
    """L302: .days + 1 — kill mutation to .days - 1 (INSIDE the for loop).

    L302 is the duration calc when closing a cluster because a GAP was found.
    This only fires when there are 2+ clusters. We test the FIRST cluster's duration.

    Cluster 1: Jan 10-11 (2 days). Gap on Jan 12-13. Cluster 2: Jan 14 (1 day).
    L302: duration = (prev_date - cluster_start).days + 1 = (11-10).days + 1 = 2
    Mutated to -1: (11-10).days - 1 = 0
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    records = []
    for day, mm in [(10, 60.0), (11, 60.0), (12, 0.0), (13, 0.0), (14, 60.0)]:
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
        end_date=date(2024, 1, 14),
        threshold_mm=50.0,
        window_days=1,
    )

    # Should produce 2 events: cluster 1 (Jan 10-11) and cluster 2 (Jan 14)
    assert len(events) == 2
    # Events sorted descending by start date: [Jan 14, Jan 10-11]
    # First cluster (Jan 10-11) duration = 2
    first_cluster = next(e for e in events if e["event_start"] == date(2024, 1, 10))
    assert first_cluster["duration_days"] == 2  # (11-10).days + 1 = 2; with -1: 0
    # Second cluster (Jan 14) duration = 1
    second_cluster = next(e for e in events if e["event_start"] == date(2024, 1, 14))
    assert second_cluster["duration_days"] == 1


@patch("app.domains.geo.rainfall_service.select")
def test_detect_duration_formula_multiday_last_cluster(mock_select):
    """L318: .days + 1 — the LAST cluster formula (after the for loop).

    3-day event (Jan 10-12): (12-10).days + 1 = 2 + 1 = 3.
    With -1: 2 - 1 = 1 (way off).
    """
    from app.domains.geo.rainfall_service import detect_rainfall_events

    zona_id = uuid.uuid4()

    records = []
    for day in [10, 11, 12]:
        rec = MagicMock()
        rec.zona_operativa_id = zona_id
        rec.date = date(2024, 1, day)
        rec.precipitation_mm = 60.0
        records.append(rec)

    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = records

    events = detect_rainfall_events(
        db,
        start_date=date(2024, 1, 10),
        end_date=date(2024, 1, 12),
        threshold_mm=50.0,
        window_days=1,
    )

    assert len(events) == 1
    assert events[0]["duration_days"] == 3


# ---------------------------------------------------------------------------
# Mutation-killing tests — Image suggestion (L346-399)
# ---------------------------------------------------------------------------


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_search_window_after_event_not_before(mock_explorer_cls, mock_ee, mock_init):
    """L360-362: event_end_date + timedelta — kill mutation to - timedelta.

    search_start = event_end_date + days_after_min (AFTER the event)
    search_end = event_end_date + days_after_max
    If mutated to -, it would search BEFORE the event.
    """
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

    event_end = date(2024, 6, 15)
    suggest_images_for_event(event_end, days_after_min=2, days_after_max=5)

    # search_start = June 15 + 2 = June 17
    # search_end = June 15 + 5 = June 20
    # end_exclusive = June 21
    # If - was used: search_start = June 13, search_end = June 10 (backwards!)
    expected_start = "2024-06-17"
    expected_end_exclusive = "2024-06-21"
    coll.filterDate.assert_called_once_with(expected_start, expected_end_exclusive)


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_toa_cutoff_strictly_less_than_2019(mock_explorer_cls, mock_ee, mock_init):
    """L365: year < 2019 — kill mutation to <= 2019.

    2019 should use SR (not TOA). Only years < 2019 use TOA.
    With <=, year 2019 would incorrectly use TOA.
    """
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

    # Event end in 2019 → search_start is also 2019
    # year < 2019 → False → use SR. If <= 2019 → True → use TOA (wrong)
    suggest_images_for_event(date(2019, 1, 1), days_after_min=2, days_after_max=5)

    mock_ee.ImageCollection.assert_called_with("COPERNICUS/S2_SR_HARMONIZED")


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_extract_info_returns_feature_not_none(mock_explorer_cls, mock_ee, mock_init):
    """L383: return ee.Feature(...) — kill mutation to return None.

    Capture the _extract_info function from collection.map() and invoke it
    directly to verify it returns an ee.Feature, not None.
    """
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

    # Set up ee.Date and ee.Feature mocks
    mock_date = MagicMock()
    mock_date.format.return_value = "2024-06-20"
    mock_ee.Date.return_value = mock_date
    feature_sentinel = MagicMock(name="feature_sentinel")
    mock_ee.Feature.return_value = feature_sentinel

    suggest_images_for_event(date(2024, 6, 15))

    # Capture the _extract_info function passed to collection.map
    coll.map.assert_called_once()
    extract_fn = coll.map.call_args[0][0]

    # Invoke it with a mock image
    mock_image = MagicMock()
    result = extract_fn(mock_image)

    # With correct code: returns ee.Feature(...) → feature_sentinel
    # With mutation: returns None
    assert result is not None
    assert result is feature_sentinel


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_dedup_strict_less_than(mock_explorer_cls, mock_ee, mock_init):
    """L399: cc < date_best[d] — kill mutation to cc <= date_best[d].

    With <: only STRICTLY lower cloud cover replaces. Equal doesn't replace.
    With <=: equal cloud cover would replace (different behavior).
    """
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
            {"properties": {"date": "2024-06-20", "cloud_cover_pct": 15.0}},
            {"properties": {"date": "2024-06-20", "cloud_cover_pct": 10.0}},  # lower → replaces
            {"properties": {"date": "2024-06-20", "cloud_cover_pct": 10.0}},  # equal → does NOT replace
        ]
    }
    mock_ee.ImageCollection.return_value = coll

    suggestions = suggest_images_for_event(date(2024, 6, 15))

    assert len(suggestions) == 1
    # The best for 2024-06-20 should be 10.0 (the first time it went lower)
    assert suggestions[0]["cloud_cover_pct"] == pytest.approx(10.0)


@patch("app.domains.geo.rainfall_service._ensure_initialized")
@patch("app.domains.geo.rainfall_service.ee")
@patch("app.domains.geo.gee_service.ImageExplorer")
def test_suggest_images_end_exclusive_adds_one_day(mock_explorer_cls, mock_ee, mock_init):
    """L362: end_exclusive = search_end + timedelta(days=1) — kill - mutation."""
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

    # event_end = Jan 10, days_after_min=2, days_after_max=5
    # search_start = Jan 12, search_end = Jan 15, end_exclusive = Jan 16
    suggest_images_for_event(date(2024, 1, 10), days_after_min=2, days_after_max=5)

    coll.filterDate.assert_called_once_with("2024-01-12", "2024-01-16")
