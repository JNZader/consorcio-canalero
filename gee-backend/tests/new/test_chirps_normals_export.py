"""CHIRPS monthly precipitation normals: the GEE-side export payload.

``export_chirps_monthly_normals_payload`` receives ``ee`` injected as
``ee_module``, so the whole thing runs against the recording ``FakeEE`` double
— no credentials, no network, no Earth Engine session. The tests assert the
*contract*: the CHIRPS source, the normals period, and the full 13-output set
(12 monthly + 1 annual), each with a resolved download URL.

Plus the fake-zero regression: the normals are exported over the zone's BUFFERED
BOUNDING BOX and never ``.clip``ped to its outline (the clip is what made Earth
Engine serialise masked pixels as ``0.0`` with no nodata tag), and every output
is ``unmask``ed to the sentinel so a real hole stays legible downstream.

AC: precip-normals-pipeline > "Full set generated".
"""

from __future__ import annotations

import pytest

from app.domains.geo.gee_service_analytics_support import (
    CHIRPS_COLLECTION_ID,
    CHIRPS_EXPORT_BUFFER_M,
    CHIRPS_EXPORT_NODATA,
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


def test_download_requests_geotiff_over_the_buffered_bounding_box() -> None:
    fake, _ = _run()

    params = fake.calls_to("getDownloadURL")[0].args[0]
    assert params["format"] == "GEO_TIFF"
    assert params["crs"] == "EPSG:4326"
    assert params["scale"] == 5566  # ~native CHIRPS (the 32720 warp is B1b)
    # The export window is the zone's BOUNDING BOX plus a skirt, not its outline:
    # ``bounds -> buffer -> bounds``. Asserted as the chain the code asked for,
    # which is the only thing a recording double can witness.
    assert params["region"]._path == ["Geometry", "bounds", "buffer", "bounds"]
    assert fake.one_call_to("Geometry.bounds.buffer").args == (CHIRPS_EXPORT_BUFFER_M,)


# ── the fake-zero regression: no clip, and holes carry a sentinel ────────────


def test_the_normals_are_never_clipped_to_the_zone_outline() -> None:
    """THE regression. ``.clip(geometry)`` is what manufactured the fake zeros.

    Earth Engine serialises a masked pixel into a GeoTIFF as a plain ``0.0``
    with no nodata tag, so clipping to the zone outline wrote a band of
    zero-rainfall months around the edge of the extent. CHIRPS is a global
    product — the clip never bought anything, the export window alone bounds the
    download. Any ``clip`` reaching Earth Engine here re-opens the defect.
    """
    fake, _ = _run()

    assert fake.calls_to("clip") == []


def test_every_output_is_unmasked_to_the_sentinel_before_the_download_url() -> None:
    """Defence in depth: "no data" must be a VALUE, not a mask the GeoTIFF drops.

    Dropping the clip stops manufacturing holes; ``unmask`` makes any hole that
    remains (EE masks CHIRPS off-product, e.g. over the ocean) legible to the ETL
    warp as an explicit ``src_nodata`` instead of another indistinguishable 0.0.
    """
    fake, _ = _run()

    unmasks = fake.calls_to("unmask")
    assert len(unmasks) == 13  # one per output, monthly and annual alike
    assert all(call.args == (CHIRPS_EXPORT_NODATA,) for call in unmasks)
    # …and it happens BEFORE the URL is resolved, or the bytes are the masked ones.
    assert all(_ends_with_unmask(call.path) for call in fake.calls_to("getDownloadURL"))


def _ends_with_unmask(path: str) -> bool:
    parts = path.split(".")
    return len(parts) >= 2 and parts[-2] == "unmask"
