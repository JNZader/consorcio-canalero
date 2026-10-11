from datetime import date
from types import SimpleNamespace

from app.domains.geo.rainfall.water_delta import pair_delta_payload


def _row(sensor: str, slot: str) -> SimpleNamespace:
    return SimpleNamespace(
        sensor=sensor,
        scene_id=f"{sensor}-scene",
        scene_date=date(2015, 3, 22),
        slot=slot,
    )


def test_missing_pair_is_not_comparable() -> None:
    payload = pair_delta_payload(None, _row("sentinel2", "post"), water_ha=lambda _row: 10.0)
    assert payload["comparable"] is False
    assert payload["reason"] == "missing_pair"


def test_sar_pair_is_not_comparable() -> None:
    payload = pair_delta_payload(
        _row("sentinel1", "pre"),
        _row("sentinel2", "post"),
        water_ha=lambda _row: 10.0,
    )
    assert payload["comparable"] is False
    assert payload["reason"] == "not_optical"


def test_optical_delta_is_post_minus_pre() -> None:
    pre = _row("sentinel2", "pre")
    post = _row("landsat8", "post")

    def water_ha(row: SimpleNamespace) -> float:
        return 100.0 if row.slot == "pre" else 340.5

    payload = pair_delta_payload(pre, post, water_ha=water_ha)
    assert payload["comparable"] is True
    assert payload["delta_ha"] == 240.5
    assert payload["pre"]["water_ha"] == 100.0
    assert payload["post"]["water_ha"] == 340.5
    assert "MNDWI" in payload["disclaimer"]


def test_missing_scene_ha_is_not_comparable() -> None:
    payload = pair_delta_payload(
        _row("sentinel2", "pre"),
        _row("sentinel2", "post"),
        water_ha=lambda row: None if row.slot == "post" else 12.0,
    )
    assert payload["comparable"] is False
    assert payload["reason"] == "scene_unavailable"
