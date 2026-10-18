"""Part order for a unified road. The sampler walks this order, so a wrong
seed puts the elevation cursor in the middle of the route.
"""

from __future__ import annotations

from shapely.geometry import LineString, MultiLineString, mapping

from app.domains.geo.elevation_profile import geometria_ordenada


def _coords(geom):
    if geom.geom_type == "LineString":
        return [list(geom.coords)]
    return [list(parte.coords) for parte in geom.geoms]


def test_a_single_linestring_keeps_its_direction() -> None:
    este_a_oeste = LineString([(-62.1, -32.5), (-62.9, -32.5)])
    assert list(geometria_ordenada(este_a_oeste).coords) == list(este_a_oeste.coords)


def test_a_scrambled_chain_walks_west_to_east_without_gaps() -> None:
    oeste = LineString([(-62.5, -32.5), (-62.4, -32.5)])
    medio = LineString([(-62.4, -32.5), (-62.3, -32.5)])
    este = LineString([(-62.3, -32.5), (-62.2, -32.5)])
    orden = geometria_ordenada(MultiLineString([este, oeste, medio]))

    assert _coords(orden) == [
        [(-62.5, -32.5), (-62.4, -32.5)],
        [(-62.4, -32.5), (-62.3, -32.5)],
        [(-62.3, -32.5), (-62.2, -32.5)],
    ]
    assert orden.geoms[0].coords[-1] == orden.geoms[1].coords[0]
    assert orden.geoms[1].coords[-1] == orden.geoms[2].coords[0]


def test_reversed_storage_orders_to_the_same_geometry() -> None:
    oeste = LineString([(-62.7, -32.6), (-62.702, -32.6)])
    este = LineString([(-62.703, -32.6), (-62.705, -32.6)])
    directo = geometria_ordenada(MultiLineString([oeste, este]))
    invertido = geometria_ordenada(MultiLineString([este, oeste]))
    assert mapping(directo) == mapping(invertido)
    assert mapping(geometria_ordenada(directo)) == mapping(directo)


def test_a_westward_kink_does_not_become_the_start() -> None:
    norte = LineString([(-62.0, -32.0), (-62.0, -32.1)])
    sur = LineString([(-62.0, -32.1), (-62.2, -32.15), (-62.0, -32.2)])
    orden = geometria_ordenada(MultiLineString([norte, sur]))

    assert orden.geoms[0].coords[0] == (-62.0, -32.2)
    assert (-62.2, -32.15) in list(orden.geoms[0].coords)
    assert orden.geoms[1].coords[0] == (-62.0, -32.1)
    assert orden.geoms[1].coords[-1] == (-62.0, -32.0)


def test_a_branch_is_kept_and_the_walk_starts_at_the_free_end() -> None:
    principal = LineString([(-62.5, -32.5), (-62.4, -32.5), (-62.3, -32.5)])
    ramal = LineString([(-62.4, -32.4), (-62.4, -32.5)])
    orden = geometria_ordenada(MultiLineString([ramal, principal]))

    assert orden.geom_type == "MultiLineString"
    assert len(orden.geoms) == 2
    assert list(orden.geoms[0].coords) == [
        (-62.5, -32.5),
        (-62.4, -32.5),
        (-62.3, -32.5),
    ]
    assert orden.geoms[1].coords[0] == (-62.4, -32.5)
    assert (-62.4, -32.4) in list(orden.geoms[1].coords)
