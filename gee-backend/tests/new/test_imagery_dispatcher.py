"""``ImageExplorer.get_image`` routing and the historic-flood endpoint.

Regression this locks down: when ``mode='composite'`` stopped reaching
``get_sentinel2_image(use_median=True)``, historic floods silently went from a
temporal median (cloud-free) back to a plain mosaic, and the clouds showed up
on the user's screen.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict


import pytest

from app.core.exceptions import AppException, NotFoundError

TARGET = date(2015, 3, 15)
LANDSAT_SENSORS_IDS = ("landsat8", "landsat7", "landsat5")


class _Spy:
    """Records the kwargs a patched builder was called with."""

    def __init__(self, result: Dict[str, Any] | None = None):
        self.calls: list[dict] = []
        self.result = result if result is not None else {"tile_url": "https://tiles/{z}"}

    def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return dict(self.result)

    @property
    def kwargs(self) -> dict:
        assert len(self.calls) == 1, f"expected a single call, got {self.calls}"
        return self.calls[0]["kwargs"]


@pytest.fixture
def explorer():
    """A real ``ImageExplorer`` without touching Earth Engine.

    ``__init__`` would call ``ee.Initialize`` and build the zona asset, but the
    dispatcher under test only routes between methods, so bypassing the
    constructor keeps the REAL routing logic under test.
    """
    from app.domains.geo.gee_service import ImageExplorer

    instance = ImageExplorer.__new__(ImageExplorer)
    instance.zona = object()
    return instance


# ── sentinel2: composite → median, scene → mosaic ──────────────────────────


def test_sentinel2_composite_mode_requests_the_temporal_median(explorer, monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_sentinel2_payload", spy)

    explorer.get_image("sentinel2", TARGET, days_buffer=12, max_cloud=55, mode="composite")

    assert spy.kwargs["use_median"] is True
    assert spy.kwargs["target_date"] == TARGET
    assert spy.kwargs["days_buffer"] == 12
    assert spy.kwargs["max_cloud"] == 55


def test_sentinel2_scene_mode_requests_the_mosaic(explorer, monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_sentinel2_payload", spy)

    explorer.get_image("sentinel2", TARGET, mode="scene")

    assert spy.kwargs["use_median"] is False


def test_sentinel2_unknown_mode_is_not_treated_as_composite(explorer, monkeypatch) -> None:
    """A non-canonical mode must NOT silently enable the median.

    ``get_image`` compares ``mode == "composite"`` exactly, so anything else
    falls back to the mosaic. That fallback is only safe because the HTTP layer
    rejects unknown values up front (see the Literal on
    ``get_satellite_image_impl``) — this test pins the service-level half of
    that contract.
    """
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_sentinel2_payload", spy)

    explorer.get_image("sentinel2", TARGET, mode="COMPOSITE")

    assert spy.kwargs["use_median"] is False


def test_satellite_image_endpoint_rejects_an_unknown_mode() -> None:
    """The HTTP layer fails closed on a bad mode instead of degrading silently.

    FastAPI derives request validation from this annotation, so pinning it here
    is what stops a typo from reaching ``get_image`` and quietly falling back to
    a cloudy mosaic. ``get_type_hints`` resolves the string annotations that
    ``from __future__ import annotations`` leaves behind.
    """
    from typing import Literal, get_args, get_origin, get_type_hints

    from app.domains.geo.router_gee_support import get_satellite_image_impl

    annotation = get_type_hints(get_satellite_image_impl)["mode"]
    assert get_origin(annotation) is Literal
    assert set(get_args(annotation)) == {"scene", "composite"}


def test_sentinel2_visualization_is_forwarded(explorer, monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_sentinel2_payload", spy)

    explorer.get_image("sentinel2", TARGET, visualization="inundacion", mode="composite")

    assert spy.kwargs["visualization"] == "inundacion"


# ── sentinel1: SAR has no optical clouds, mode is irrelevant ───────────────


@pytest.mark.parametrize("mode", ["scene", "composite"])
def test_sentinel1_routes_to_the_sar_builder(explorer, monkeypatch, mode: str) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_sentinel1_payload", spy)

    explorer.get_image("sentinel1", TARGET, days_buffer=8, visualization="vv_flood", mode=mode)

    assert spy.kwargs["days_buffer"] == 8
    assert spy.kwargs["visualization"] == "vv_flood"
    # The SAR payload has no median/mosaic switch at all.
    assert "use_median" not in spy.kwargs


# ── landsat: composite mode must reach use_median=True ─────────────────────


@pytest.mark.parametrize("sensor", LANDSAT_SENSORS_IDS)
def test_landsat_composite_mode_requests_the_median(explorer, monkeypatch, sensor: str) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_landsat_payload", spy)

    explorer.get_image(sensor, TARGET, max_cloud=80, mode="composite")

    assert spy.kwargs["sensor"] == sensor
    assert spy.kwargs["use_median"] is True


@pytest.mark.parametrize("sensor", LANDSAT_SENSORS_IDS)
def test_landsat_scene_mode_requests_the_mosaic(explorer, monkeypatch, sensor: str) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_landsat_payload", spy)

    explorer.get_image(sensor, TARGET, mode="scene")

    assert spy.kwargs["use_median"] is False


def test_landsat_use_median_flag_wins_over_scene_mode(explorer, monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_landsat_payload", spy)

    explorer.get_landsat_image("landsat8", TARGET, use_median=True, mode="scene")

    assert spy.kwargs["use_median"] is True


def test_landsat_forwards_search_params(explorer, monkeypatch) -> None:
    spy = _Spy()
    monkeypatch.setattr("app.domains.geo.gee_service.build_landsat_payload", spy)

    explorer.get_image(
        "landsat8",
        TARGET,
        days_buffer=30,
        max_cloud=80,
        visualization="falso_color",
        mode="composite",
    )

    assert spy.kwargs["days_buffer"] == 30
    assert spy.kwargs["max_cloud"] == 80
    assert spy.kwargs["visualization"] == "falso_color"


def test_unsupported_sensor_returns_a_structured_error(explorer) -> None:
    result = explorer.get_image("modis", TARGET)

    assert result["error"] == "Sensor no soportado: modis"
    assert result["target_date"] == "2015-03-15"


@pytest.mark.parametrize("sensor", LANDSAT_SENSORS_IDS)
def test_get_image_scenes_routes_landsat(explorer, monkeypatch, sensor: str) -> None:
    spy = _Spy({"scenes": []})
    monkeypatch.setattr("app.domains.geo.gee_service.build_landsat_scenes_payload", spy)

    explorer.get_image_scenes(sensor, TARGET, days_buffer=1, visualization="rgb")

    assert spy.kwargs["sensor"] == sensor


def test_get_image_scenes_rejects_non_landsat(explorer) -> None:
    result = explorer.get_image_scenes("sentinel2", TARGET)

    assert "no soportado" in result["error"]


# ── historic floods: composite for optical, scene only for SAR ─────────────


class _FloodExplorer:
    def __init__(self, image_result: Dict[str, Any], sar_result: Dict[str, Any] | None = None):
        self.image_result = image_result
        self.sar_result = sar_result or {"sensor": "Sentinel-1", "tile_url": "sar"}
        self.image_calls: list[dict] = []
        self.sar_calls: list[dict] = []

    def get_image(self, **kwargs):
        self.image_calls.append(kwargs)
        return dict(self.image_result)

    def get_sentinel1_image(self, **kwargs):
        self.sar_calls.append(kwargs)
        return dict(self.sar_result)


def _ensure_gee(explorer_obj):
    return lambda: {"get_image_explorer": lambda: explorer_obj}


def _curated(db, *, event_key: str, day: date, payload: Dict[str, Any]):
    """Seed one curated anchor, exactly as migration `lluvia_ext_002` does.

    These used to be entries in the `HISTORIC_FLOODS` module literal; the
    literal died in B2b and the anchors are rows now, so the dispatcher tests
    that address them by id have to plant them. The helper is local and
    curated-only on purpose: what this file tests is the mode dispatch the
    bridge performs on a resolved record, not the served catalog contract
    (that lives in `geo/rainfall/test_rainfall_catalog_bridge.py`).
    """
    from app.domains.geo.rainfall.models import RainfallExtremeEvent
    from app.domains.geo.router_gee_support import CATALOG_SCOPE

    row = RainfallExtremeEvent(
        **CATALOG_SCOPE,
        detector_revision="curated",
        provenance="curated",
        event_key=event_key,
        tier=None,
        start_date=day,
        end_date=day,
        curated_payload=payload,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def anchors(db):
    """The three seeded anchors, verbatim from `lluvia_ext_002`."""
    _curated(
        db,
        event_key="mar_2015",
        day=date(2015, 3, 15),
        payload={
            "name": "Inundacion Marzo 2015",
            "description": "Evento historico para revisar con Landsat 8/Landsat 7 y Sentinel-1",
            "severity": "alta",
            "sensor": "landsat8",
            "max_cloud": 80,
            "days_buffer": 30,
        },
    )
    _curated(
        db,
        event_key="feb_2017",
        day=date(2017, 2, 20),
        payload={
            "name": "Inundacion Febrero 2017",
            "description": "Gran inundacion que afecto Bell Ville y zona rural",
            "severity": "alta",
            "sensor": "sentinel2",
        },
    )
    _curated(
        db,
        event_key="sep_2025",
        day=date(2025, 9, 5),
        payload={
            "name": "Inundacion Septiembre 2025",
            "description": "Evento de anegamiento por lluvias intensas",
            "severity": "media",
        },
    )
    return db


async def _historic(flood_id: str, explorer_obj, db, visualization: str = "rgb"):
    from app.domains.geo.router_gee_support import get_historic_flood_tiles_impl

    return await get_historic_flood_tiles_impl(
        flood_id=flood_id,
        visualization=visualization,
        ensure_gee=_ensure_gee(explorer_obj),
        db=db,
    )


async def test_historic_flood_optical_sensor_uses_composite_mode(anchors) -> None:
    explorer_obj = _FloodExplorer({"sensor": "Sentinel-2", "tile_url": "t"})

    result = await _historic("feb_2017", explorer_obj, anchors)

    call = explorer_obj.image_calls[0]
    assert call["sensor"] == "sentinel2"
    assert call["mode"] == "composite"
    assert result["composition_mode"] == "composite"


async def test_historic_flood_landsat_event_also_composites(anchors) -> None:
    explorer_obj = _FloodExplorer({"sensor": "Landsat 8", "tile_url": "t"})

    result = await _historic("mar_2015", explorer_obj, anchors)

    call = explorer_obj.image_calls[0]
    assert call["sensor"] == "landsat8"
    assert call["mode"] == "composite"
    assert call["max_cloud"] == 80
    assert call["days_buffer"] == 30
    assert result["composition_mode"] == "composite"


async def test_historic_flood_defaults_to_sentinel2_when_unspecified(anchors) -> None:
    explorer_obj = _FloodExplorer({"sensor": "Sentinel-2", "tile_url": "t"})

    await _historic("sep_2025", explorer_obj, anchors)

    call = explorer_obj.image_calls[0]
    assert call["sensor"] == "sentinel2"
    assert call["mode"] == "composite"
    assert call["max_cloud"] == 60
    # Post-2020 event → the shorter buffer.
    assert call["days_buffer"] == 15


async def test_historic_flood_sar_sensor_uses_scene_mode(db) -> None:
    """This one used to `monkeypatch.setattr(mod, "HISTORIC_FLOODS", ...)` to
    invent a SAR event; the symbol is gone, so the event is a catalog row now.
    The property is unchanged: SAR has no optical clouds, so it stays `scene`."""
    _curated(
        db,
        event_key="sar_evt",
        day=date(2024, 2, 20),
        payload={"name": "SAR", "severity": "alta", "sensor": "sentinel1"},
    )
    explorer_obj = _FloodExplorer({"sensor": "Sentinel-1", "tile_url": "t"})

    result = await _historic("sar_evt", explorer_obj, db)

    assert explorer_obj.image_calls[0]["mode"] == "scene"
    # SAR has no optical clouds — never mislabel it as a cloud-free composite.
    assert "composition_mode" not in result


async def test_historic_flood_sar_fallback_is_not_labelled_composite(anchors) -> None:
    """Optical came back empty → SAR fallback, whose result is a mosaic."""
    explorer_obj = _FloodExplorer(
        {"error": "No se encontraron imagenes"},
        {"sensor": "Sentinel-1", "tile_url": "sar"},
    )

    result = await _historic("feb_2017", explorer_obj, anchors)

    assert explorer_obj.sar_calls[0]["visualization"] == "vv_flood"
    assert result["sensor"] == "Sentinel-1"
    assert "composition_mode" not in result


async def test_historic_flood_keeps_the_composition_mode_the_builder_reported(anchors) -> None:
    explorer_obj = _FloodExplorer(
        {"sensor": "Landsat 7", "tile_url": "t", "composition_mode": "composite"}
    )

    result = await _historic("mar_2015", explorer_obj, anchors)

    assert result["composition_mode"] == "composite"


async def test_historic_flood_attaches_the_flood_metadata(anchors) -> None:
    explorer_obj = _FloodExplorer({"sensor": "Sentinel-2", "tile_url": "t"})

    result = await _historic("feb_2017", explorer_obj, anchors)

    assert result["flood_info"]["id"] == "feb_2017"
    assert result["flood_info"]["date"] == "2017-02-20"


async def test_historic_flood_unknown_id_raises_not_found(anchors) -> None:
    explorer_obj = _FloodExplorer({"sensor": "Sentinel-2"})

    with pytest.raises(NotFoundError) as excinfo:
        await _historic("no_existe", explorer_obj, anchors)

    assert excinfo.value.code == "FLOOD_NOT_FOUND"


async def test_historic_flood_wraps_unexpected_failures(anchors) -> None:
    class _Boom:
        def get_image(self, **kwargs):
            raise RuntimeError("GEE exploded")

    with pytest.raises(AppException) as excinfo:
        await _historic("feb_2017", _Boom(), anchors)

    assert excinfo.value.code == "HISTORIC_FLOOD_ERROR"
    assert excinfo.value.status_code == 500


async def test_historic_flood_forwards_the_requested_visualization(anchors) -> None:
    explorer_obj = _FloodExplorer({"sensor": "Sentinel-2", "tile_url": "t"})

    await _historic("feb_2017", explorer_obj, anchors, visualization="inundacion")

    assert explorer_obj.image_calls[0]["visualization"] == "inundacion"
