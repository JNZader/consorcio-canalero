from datetime import date
from types import SimpleNamespace

from app.domains.geo.rainfall.water_delta import pair_delta_payload, resolve_pair_rows


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


def test_resolve_pair_rows_picks_ranked_ids_not_slot_defaults() -> None:
    ranked_pre = _row("sentinel2", "ranked")
    ranked_pre.scene_id = "S2-A"
    ranked_post = _row("landsat8", "ranked")
    ranked_post.scene_id = "L8-B"
    stored_sar = _row("sentinel1", "pre")
    stored_sar.scene_id = "S1-PRE"
    pre, post = resolve_pair_rows(
        [stored_sar, ranked_pre, ranked_post],
        "S2-A",
        "L8-B",
    )
    assert pre is ranked_pre
    assert post is ranked_post


def test_resolve_pair_rows_unknown_id_is_none() -> None:
    row = _row("sentinel2", "ranked")
    row.scene_id = "S2-A"
    pre, post = resolve_pair_rows([row], "S2-A", "missing")
    assert pre is row
    assert post is None
