"""CHIRPS monthly precipitation normals: the GEE-side export payload.

``export_chirps_monthly_normals_payload`` receives ``ee`` injected as
``ee_module``, so the whole thing runs against the recording ``FakeEE`` double
— no credentials, no network, no Earth Engine session. The tests assert the
*contract*: the CHIRPS source, the normals period, and the full 13-output set
(12 monthly + 1 annual), each with a resolved download URL.

AC: precip-normals-pipeline > "Full set generated".
"""

from __future__ import annotations

import pytest

from app.domains.geo.gee_service_analytics_support import (
    CHIRPS_COLLECTION_ID,
    export_chirps_monthly_normals_payload,
)

from tests.new.imagery_ee_double import FakeEE

REGION = {
    "type": "Polygon",
    "coordinates": [
        [[-58.5, -34.9], [-58.4, -34.9], [-58.4, -34.8], [-58.5, -34.8], [-58.5, -34.9]]
    ],
}

_DOWNLOAD_URL = "https://earthengine.example/chirps/download.tif"


def _fake() -> FakeEE:
    return FakeEE({"getDownloadURL": _DOWNLOAD_URL})


def _run(**kwargs):
    fake = _fake()
    descriptors = export_chirps_monthly_normals_payload(
        fake,
        _NullLogger(),
        region=REGION,
        **kwargs,
    )
    return fake, descriptors


class _NullLogger:
    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass


# ── Full set generated ─────────────────────────────────────────────────────


def test_produces_thirteen_outputs_twelve_monthly_plus_annual() -> None:
    _, descriptors = _run()

    assert len(descriptors) == 13
    meses = [d["mes"] for d in descriptors]
    assert meses == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, "anual"]


def test_every_output_carries_a_resolved_download_url() -> None:
    fake, descriptors = _run()

    assert all(d["download_url"] == _DOWNLOAD_URL for d in descriptors)
    # One getDownloadURL per output — nothing skipped, nothing doubled.
    assert len(fake.calls_to("getDownloadURL")) == 13


def test_source_is_chirps_daily() -> None:
    fake, _ = _run()

    image_collections = [
        call.args[0]
        for call in fake.calls_to("ImageCollection")
        if call.args and isinstance(call.args[0], str)
    ]
    assert CHIRPS_COLLECTION_ID in image_collections


def test_normals_period_bounds_the_filter_date_window() -> None:
    fake, _ = _run(start_year=1991, end_year=2020)

    window = fake.one_call_to("filterDate")
    # End-exclusive upper bound: the year after end_year captures all of 2020.
    assert window.args == ("1991-01-01", "2021-01-01")


def test_monthly_normals_average_per_year_sums_across_the_period() -> None:
    # 30 years x 12 months = 360 year-scoped month sums, each averaged.
    fake, _ = _run(start_year=1991, end_year=2020)

    year_filters = [
        call for call in fake.calls_to("calendarRange") if call.args and call.args[2] == "year"
    ]
    month_filters = [
        call for call in fake.calls_to("calendarRange") if call.args and call.args[2] == "month"
    ]
    assert len(year_filters) == 360
    assert len(month_filters) == 360


def test_reducer_topology_is_per_year_sum_then_cross_year_mean_then_annual_sum() -> None:
    # This pins the *math*, not just the filter fan-out. Each monthly normal
    # accumulates a year's daily precipitation with a per-year ``.sum()`` (one
    # per year), then averages those year-sums with a single cross-year
    # ``.mean()``; the annual output is a ``.sum()`` over the 12 monthly normals.
    # Swapping any of those reducers (sum<->mean) silently corrupts the normal
    # and MUST fail here.
    fake, _ = _run(start_year=1991, end_year=2020)

    # 30 years x 12 months = 360 per-year accumulations. They live at the tail of
    # the year/month filter chain, so ``filter.filter.sum`` uniquely identifies
    # them (the annual sum has no preceding filters).
    per_year_sums = fake.calls_to("filter.filter.sum")
    per_year_means = fake.calls_to("filter.filter.mean")
    assert len(per_year_sums) == 360, "each month-year must accumulate with .sum()"
    assert per_year_means == [], "per-year reducer must be .sum(), never .mean()"

    # 12 cross-year averages (one per month) + exactly 1 annual accumulation,
    # both built as ``ImageCollection([...]).<reducer>()``. Exactly-12 mean and
    # exactly-1 sum catches an inverted cross-year mean->sum or annual sum->mean.
    cross_year_means = fake.calls_to("ImageCollection.mean")
    annual_sums = fake.calls_to("ImageCollection.sum")
    assert len(cross_year_means) == 12, "each monthly normal must average with .mean()"
    assert len(annual_sums) == 1, "the annual normal must accumulate with .sum()"


def test_degenerate_year_range_fails_fast() -> None:
    fake = _fake()
    with pytest.raises(ValueError, match=r"start_year \(2020\) must be <= end_year \(1991\)"):
        export_chirps_monthly_normals_payload(
            fake,
            _NullLogger(),
            region=REGION,
            start_year=2020,
            end_year=1991,
        )


def test_download_requests_geotiff_clipped_to_the_region() -> None:
    fake, _ = _run()

    params = fake.calls_to("getDownloadURL")[0].args[0]
    assert params["format"] == "GEO_TIFF"
    assert params["crs"] == "EPSG:4326"
    # Region-clipped and rendered at ~native CHIRPS scale (the 32720 warp is B1b).
    assert "region" in params
    assert params["scale"] == 5566
