"""Part order for a unified road. The sampler walks this order, so a wrong
seed puts the elevation cursor in the middle of the route.

A reverse is an entrance: it happens only when the chosen end is within
8 m of the cursor. A separated piece keeps the direction it was drawn.
"""

from __future__ import annotations

from math import cos, radians

import pytest
from shapely.geometry import LineString, MultiLineString, mapping

from app.domains.geo.elevation_profile import geometria_ordenada

_METROS_POR_GRADO = 111_320.0


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
    # The joint is the nearer end, and it sits ~9 km from the cursor.
    # 0032 keeps the drawn direction. A meeting within 8 m still turns.
    assert list(orden.geoms[1].coords) == [(-62.4, -32.4), (-62.4, -32.5)]


def test_a_spur_stored_leaving_the_joint_stays_that_way() -> None:
    oeste = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    espuela = LineString([(-62.49, -32.50), (-62.49, -32.49)])
    este = LineString([(-62.49, -32.50), (-62.48, -32.50)])
    orden = geometria_ordenada(MultiLineString([oeste, espuela, este]))

    assert _coords(orden) == [
        list(oeste.coords),
        list(espuela.coords),
        list(este.coords),
    ]


def test_a_piece_that_meets_the_cursor_still_turns_around() -> None:
    principal = LineString([(-62.5, -32.5), (-62.4, -32.5)])
    ramal = LineString([(-62.4, -32.4), (-62.4, -32.5)])
    orden = geometria_ordenada(MultiLineString([ramal, principal]))

    assert list(orden.geoms[0].coords) == [(-62.5, -32.5), (-62.4, -32.5)]
    assert list(orden.geoms[1].coords) == [(-62.4, -32.5), (-62.4, -32.4)]


def test_a_three_metre_entrance_still_turns_the_piece_around() -> None:
    dy = 3.0 / _METROS_POR_GRADO
    principal = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    punta = (-62.49, -32.50 + dy)
    lejos = (-62.48, -32.50)
    orden = geometria_ordenada(MultiLineString([LineString([lejos, punta]), principal]))

    assert list(orden.geoms[0].coords) == [(-62.50, -32.50), (-62.49, -32.50)]
    assert list(orden.geoms[1].coords) == [punta, lejos]


def test_a_forty_metre_gap_keeps_the_drawn_direction() -> None:
    dy = 40.0 / _METROS_POR_GRADO
    principal = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    punta = (-62.49, -32.50 + dy)
    lejos = (-62.48, -32.50)
    orden = geometria_ordenada(MultiLineString([LineString([lejos, punta]), principal]))

    assert list(orden.geoms[1].coords) == [lejos, punta]
    assert list(geometria_ordenada(orden).geoms[1].coords) == [lejos, punta]


def test_a_separated_piece_keeps_the_direction_it_was_drawn() -> None:
    principal = LineString([(-62.50, -32.50), (-62.40, -32.50)])
    # Drawn toward the south. The south tip is closer to the cursor, and
    # the gap is kilometres, so the walk must not turn the piece around.
    pieza = LineString([(-62.30, -32.40), (-62.35, -32.45)])
    orden = geometria_ordenada(MultiLineString([pieza, principal]))

    assert list(orden.geoms[0].coords) == [(-62.50, -32.50), (-62.40, -32.50)]
    assert list(orden.geoms[1].coords) == list(pieza.coords)


def _grados_este(metros: float) -> float:
    return metros / (_METROS_POR_GRADO * cos(radians(-32.5)))


def test_a_seven_metre_east_gap_still_turns_the_piece_around() -> None:
    # 7.5 m of longitude. ``8/111320`` degrees is ~6.7 m east-west, so a
    # degree-length gate would call this more than 8 m and refuse the turn.
    principal = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    cerca = (-62.49 + _grados_este(7.5), -32.50)
    lejos = (-62.49 + _grados_este(80.0), -32.50)
    orden = geometria_ordenada(MultiLineString([LineString([lejos, cerca]), principal]))

    assert list(orden.geoms[1].coords) == [cerca, lejos]


@pytest.mark.parametrize(("metros", "voltea"), [(8.0, True), (9.0, False)])
def test_the_entrance_gate_closes_above_eight_metres(metros: float, voltea: bool) -> None:
    dy = metros / _METROS_POR_GRADO
    principal = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    punta = (-62.49, -32.50 + dy)
    lejos = (-62.48, -32.50)
    orden = geometria_ordenada(MultiLineString([LineString([lejos, punta]), principal]))

    assert orden.geoms[1].coords[0] == (punta if voltea else lejos)
