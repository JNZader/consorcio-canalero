from shapely.geometry import LineString

from app.domains.geo.intelligence.zoning_suggestions import (
    build_zones_from_assignments,
    extract_basin_family,
    split_basins_for_display,
    suggest_grouped_zones,
)
from app.domains.geo.intelligence import zoning_suggestions


def _feature(fid: str, name: str, cuenca: str, area: float, coords: list[list[list[float]]]):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": coords},
        "properties": {
            "id": fid,
            "nombre": name,
            "cuenca": cuenca,
            "superficie_ha": area,
        },
    }


def test_extract_basin_family_from_sub_cuenca():
    assert extract_basin_family("sub_noroeste_14") == "noroeste"
    assert extract_basin_family("sub_ml_15") == "ml"


def test_suggest_grouped_zones_keeps_each_basin_once():
    basins = [
        _feature("a", "Sub-cuenca 1 (candil)", "sub_candil_1", 9000, [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]),
        _feature("b", "Sub-cuenca 2 (candil)", "sub_candil_2", 8000, [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]]),
        _feature("c", "Sub-cuenca 3 (candil)", "sub_candil_3", 7000, [[[2, 0], [3, 0], [3, 1], [2, 1], [2, 0]]]),
    ]

    result = suggest_grouped_zones(basins)
    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 1

    members = []
    for feature in result["features"]:
        members.extend(feature["properties"]["member_basin_ids"])

    assert sorted(members) == ["a", "b", "c"]


def test_suggest_grouped_zones_separates_families():
    basins = [
        _feature("a", "Sub-cuenca 1 (candil)", "sub_candil_1", 4000, [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]),
        _feature("b", "Sub-cuenca 1 (ml)", "sub_ml_1", 4000, [[[10, 0], [11, 0], [11, 1], [10, 1], [10, 0]]]),
        _feature("c", "Sub-cuenca 1 (noroeste)", "sub_noroeste_1", 4000, [[[20, 0], [21, 0], [21, 1], [20, 1], [20, 0]]]),
        _feature("d", "Sub-cuenca 1 (norte)", "sub_norte_1", 4000, [[[21, 0], [22, 0], [22, 1], [21, 1], [21, 0]]]),
    ]

    result = suggest_grouped_zones(basins)
    families = sorted(feature["properties"]["family"] for feature in result["features"])
    assert families == ["candil", "ml", "noroeste+norte"]


def test_suggest_grouped_zones_assigns_unassigned_to_monte_lena_or_candil():
    basins = [
        _feature("ml", "Sub-cuenca 1 (ml)", "sub_ml_1", 4000, [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]),
        _feature("candil", "Sub-cuenca 1 (candil)", "sub_candil_1", 4000, [[[10, 0], [11, 0], [11, 1], [10, 1], [10, 0]]]),
        _feature("norte", "Sub-cuenca 1 (norte)", "sub_norte_1", 4000, [[[0, 10], [1, 10], [1, 11], [0, 11], [0, 10]]]),
        _feature(
            "sur-este",
            "Sub-cuenca 99 (sin_asignar)",
            "sub_sin_asignar_99",
            1000,
            [[[9, -1], [10, -1], [10, 0], [9, 0], [9, -1]]],
        ),
    ]

    result = suggest_grouped_zones(basins)
    by_zone = {feature["properties"]["draft_zone_id"]: feature["properties"] for feature in result["features"]}

    candil_members = by_zone["draft-zone-candil"]["member_basin_ids"]
    norte_members = by_zone["draft-zone-norte"]["member_basin_ids"]

    assert "sur-este" in candil_members
    assert "sur-este" not in norte_members


def test_suggest_grouped_zones_assigns_unassigned_by_lindante_neighbor():
    basins = [
        _feature("n16", "Sub-cuenca 16 (norte)", "sub_norte_16", 4000, [[[0, 0], [1, 0], [1, 2], [0, 2], [0, 0]]]),
        _feature("n17", "Sub-cuenca 17 (norte)", "sub_norte_17", 4000, [[[1, 0], [2, 0], [2, 2], [1, 2], [1, 0]]]),
        _feature("candil", "Sub-cuenca 13 (candil)", "sub_candil_13", 4000, [[[3, 0], [4, 0], [4, 2], [3, 2], [3, 0]]]),
        _feature(
            "between",
            "Sub-cuenca 2 (sin_asignar)",
            "sub_sin_asignar_2",
            2000,
            [[[2, 0], [3, 0], [3, 2], [2, 2], [2, 0]]],
        ),
    ]

    result = suggest_grouped_zones(basins)
    by_zone = {feature["properties"]["draft_zone_id"]: feature["properties"] for feature in result["features"]}
    assert "between" in by_zone["draft-zone-norte"]["member_basin_ids"]


def test_build_zones_from_assignments_respects_manual_moves_and_names():
    basins = [
        _feature("a", "Sub-cuenca 1 (candil)", "sub_candil_1", 4000, [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]),
        _feature("b", "Sub-cuenca 1 (ml)", "sub_ml_1", 5000, [[[2, 0], [3, 0], [3, 1], [2, 1], [2, 0]]]),
        _feature("c", "Sub-cuenca 1 (norte)", "sub_norte_1", 6000, [[[4, 0], [5, 0], [5, 1], [4, 1], [4, 0]]]),
    ]

    result = build_zones_from_assignments(
        basins,
        basin_zone_assignments={"c": "draft-zone-candil"},
        zone_names={"draft-zone-candil": "Candil Ajustado"},
    )

    by_zone = {feature["properties"]["zone_id"]: feature["properties"] for feature in result["features"]}
    assert by_zone["draft-zone-candil"]["nombre"] == "Candil Ajustado"
    assert sorted(by_zone["draft-zone-candil"]["member_basin_ids"]) == ["a", "c"]


def test_suggest_grouped_zones_splits_subcuenca_9_between_ml_and_candil(monkeypatch):
    monkeypatch.setattr(
        zoning_suggestions,
        "_special_split_divider",
        lambda: LineString([(1.5, -1), (1.5, 3)]),
    )

    basins = [
        _feature("ml", "Sub-cuenca 1 (ml)", "sub_ml_1", 4000, [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]),
        _feature("candil", "Sub-cuenca 1 (candil)", "sub_candil_1", 4000, [[[3, 0], [4, 0], [4, 1], [3, 1], [3, 0]]]),
        _feature(
            "splitme",
            "Sub-cuenca 9 (sin_asignar)",
            "sub_sin_asignar_9",
            6000,
            [[[0, -0.5], [3, -0.5], [3, 2], [0, 2], [0, -0.5]]],
        ),
    ]

    result = suggest_grouped_zones(basins)
    by_zone = {feature["properties"]["draft_zone_id"]: feature["properties"] for feature in result["features"]}
    assert any(member.startswith("splitme::split-") for member in by_zone["draft-zone-monte-lena"]["member_basin_ids"])
    assert any(member.startswith("splitme::split-") for member in by_zone["draft-zone-candil"]["member_basin_ids"])


def test_split_basins_for_display_exposes_two_visual_parts(monkeypatch):
    monkeypatch.setattr(
        zoning_suggestions,
        "_special_split_divider",
        lambda: LineString([(1.5, -1), (1.5, 3)]),
    )

    basins = [
        _feature("ml", "Sub-cuenca 1 (ml)", "sub_ml_1", 4000, [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]),
        _feature("candil", "Sub-cuenca 1 (candil)", "sub_candil_1", 4000, [[[3, 0], [4, 0], [4, 1], [3, 1], [3, 0]]]),
        _feature(
            "splitme",
            "Sub-cuenca 9 (sin_asignar)",
            "sub_sin_asignar_9",
            6000,
            [[[0, -0.5], [3, -0.5], [3, 2], [0, 2], [0, -0.5]]],
        ),
    ]

    result = split_basins_for_display(basins)
    split_ids = sorted(feature["properties"]["id"] for feature in result if "::split-" in feature["properties"]["id"])
    assert split_ids == ["splitme::split-1", "splitme::split-2"]
