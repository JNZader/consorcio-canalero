"""Annual Sentinel-2 window and JRC tile payloads, without a live Earth Engine session."""

from datetime import date

import pytest

from app.core.exceptions import AppException
from app.domains.geo.time_layers import (
    JRC_OCCURRENCE_ASSET,
    JRC_YEARLY_ASSET,
    TimeLayerError,
    annual_composite_request,
    annual_search_window,
    jrc_tile_payload,
)


def test_non_leap_annual_window_covers_the_calendar_year():
    target, buffer, cloud = annual_composite_request(2023, date(2026, 11, 2))
    start, end = annual_search_window(target, buffer)
    assert target == date(2023, 7, 2)
    assert buffer == 182
    assert cloud == 60
    assert start == date(2023, 1, 1)
    assert end == date(2024, 1, 1)


def test_leap_annual_window_starts_on_january_2():
    target, buffer, _cloud = annual_composite_request(2024, date(2026, 11, 2))
    start, end = annual_search_window(target, buffer)
    assert start == date(2024, 1, 2)
    assert end == date(2025, 1, 1)


def test_annual_year_must_be_inside_sentinel2_and_not_in_the_future():
    with pytest.raises(TimeLayerError):
        annual_composite_request(2016, date(2026, 11, 2))
    with pytest.raises(TimeLayerError):
        annual_composite_request(2027, date(2026, 11, 2))
    target, _, _ = annual_composite_request(2026, date(2026, 1, 1))
    assert target.year == 2026


class _Fetcher:
    url_format = "https://earthengine.googleapis.com/v1/projects/p/maps/m/tiles/{z}/{x}/{y}"


class _Rec:
    def __init__(self):
        self.images = []
        self.collections = []
        self.filters = []
        self.selects = []
        self.clips = []
        self.mosaics = 0
        self.vis = None


class _Image:
    def __init__(self, rec, asset):
        self.rec = rec
        self.asset = asset

    def select(self, band):
        self.rec.selects.append(band)
        return self

    def clip(self, geom):
        self.rec.clips.append(geom)
        return self

    def getMapId(self, vis):
        self.rec.vis = vis
        return {"tile_fetcher": _Fetcher()}


class _Collection:
    def __init__(self, rec, asset):
        self.rec = rec
        self.asset = asset

    def filterDate(self, start, end):
        self.rec.filters.append((start, end))
        return self

    def select(self, band):
        self.rec.selects.append(band)
        return self

    def mosaic(self):
        self.rec.mosaics += 1
        return _Image(self.rec, self.asset)


class _EE:
    def __init__(self, rec):
        self.rec = rec

    def Image(self, asset):
        self.rec.images.append(asset)
        return _Image(self.rec, asset)

    def ImageCollection(self, asset):
        self.rec.collections.append(asset)
        return _Collection(self.rec, asset)


def test_occurrence_clips_the_long_term_water_recurrence_band():
    rec = _Rec()
    payload = jrc_tile_payload(_EE(rec), "zona", kind="occurrence")
    assert rec.images == [JRC_OCCURRENCE_ASSET]
    assert rec.collections == []
    assert rec.selects == ["occurrence"]
    assert rec.clips == ["zona"]
    assert rec.vis["min"] == 0
    assert rec.vis["max"] == 100
    assert payload["sensor"] == "JRC"
    assert payload["mode"] == "composite"
    assert payload["tile_url"].startswith("https://earthengine.googleapis.com/")


def test_yearly_history_mosaics_one_calendar_year():
    rec = _Rec()
    payload = jrc_tile_payload(_EE(rec), "zona", kind="year", year=2015)
    assert rec.collections == [JRC_YEARLY_ASSET]
    assert rec.filters == [("2015-01-01", "2016-01-01")]
    assert rec.selects == ["waterClass"]
    assert rec.mosaics == 1
    assert rec.vis["max"] == 3
    assert payload["target_date"] == "2015-01-01"


def test_yearly_history_rejects_years_outside_the_published_range():
    rec = _Rec()
    ee = _EE(rec)
    with pytest.raises(TimeLayerError):
        jrc_tile_payload(ee, "zona", kind="year", year=1983)
    with pytest.raises(TimeLayerError):
        jrc_tile_payload(ee, "zona", kind="year", year=2022)


class _Cache:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl_seconds):
        self.store[key] = value
        return True


class _Explorer:
    def __init__(self):
        self.calls = []
        self.zona = "zona"

    def get_sentinel2_image(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "tile_url": _Fetcher.url_format,
            "target_date": kwargs["target_date"].isoformat(),
            "images_count": 12,
            "days_buffer": kwargs["days_buffer"],
            "max_cloud": kwargs["max_cloud"],
            "visualization": "rgb",
            "visualization_description": "Color real",
            "sensor": "Sentinel-2",
            "collection": "COPERNICUS/S2_SR_HARMONIZED",
        }


@pytest.mark.asyncio
async def test_annual_endpoint_asks_for_a_median_composite(monkeypatch):
    from app.domains.geo import router_gee_support as support

    cache = _Cache()
    explorer = _Explorer()
    monkeypatch.setattr(support, "get_cache", lambda: cache)

    def ensure():
        return {"get_image_explorer": lambda: explorer}

    payload = await support.get_sentinel2_annual_impl(year=2023, ensure_gee=ensure)
    assert explorer.calls[0]["use_median"] is True
    assert explorer.calls[0]["days_buffer"] == 182
    assert explorer.calls[0]["target_date"] == date(2023, 7, 2)
    assert payload["mode"] == "composite"
    again = await support.get_sentinel2_annual_impl(year=2023, ensure_gee=ensure)
    assert again == payload
    assert len(explorer.calls) == 1


@pytest.mark.asyncio
async def test_annual_endpoint_rejects_a_future_year(monkeypatch):
    from app.domains.geo import router_gee_support as support

    monkeypatch.setattr(support, "get_cache", lambda: _Cache())
    with pytest.raises(AppException) as caught:
        await support.get_sentinel2_annual_impl(year=2099, ensure_gee=lambda: None)
    assert caught.value.status_code == 422
