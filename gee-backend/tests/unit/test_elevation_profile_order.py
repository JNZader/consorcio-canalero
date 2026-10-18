"""Part order for a unified road. The sampler walks this order.

Every part is entered at the end where the cursor arrives. Kilometer zero
is the more western extremity of that chain. A gap is not filled.
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


def test_a_branch_starts_at_the_western_extremity_of_the_chain() -> None:
    # The joint is a middle vertex, so the spur's tip is an extremity and
    # the principal's west end is not. The return to the west end is the
    # one jump a branch still forces.
    principal = LineString([(-62.5, -32.5), (-62.4, -32.5), (-62.3, -32.5)])
    ramal = LineString([(-62.4, -32.4), (-62.4, -32.5)])
    orden = geometria_ordenada(MultiLineString([ramal, principal]))

    assert orden.geom_type == "MultiLineString"
    assert _coords(orden) == [
        [(-62.4, -32.4), (-62.4, -32.5)],
        [(-62.5, -32.5), (-62.4, -32.5), (-62.3, -32.5)],
    ]
    assert mapping(geometria_ordenada(orden)) == mapping(orden)


def test_a_three_way_junction_starts_at_its_western_extremity() -> None:
    oeste = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    espuela = LineString([(-62.49, -32.50), (-62.49, -32.49)])
    este = LineString([(-62.49, -32.50), (-62.48, -32.50)])
    orden = geometria_ordenada(MultiLineString([oeste, espuela, este]))

    assert _coords(orden) == [
        [(-62.49, -32.49), (-62.49, -32.50)],
        list(oeste.coords),
        list(este.coords),
    ]
    assert mapping(geometria_ordenada(orden)) == mapping(orden)


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


def test_a_forty_metre_gap_is_entered_at_the_near_end() -> None:
    dy = 40.0 / _METROS_POR_GRADO
    principal = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    punta = (-62.49, -32.50 + dy)
    lejos = (-62.48, -32.50)
    orden = geometria_ordenada(MultiLineString([LineString([lejos, punta]), principal]))

    assert list(orden.geoms[0].coords) == list(principal.coords)
    assert list(orden.geoms[1].coords) == [punta, lejos]
    assert list(geometria_ordenada(orden).geoms[1].coords) == [punta, lejos]


def test_a_separated_piece_is_entered_at_the_near_end() -> None:
    principal = LineString([(-62.50, -32.50), (-62.40, -32.50)])
    # Drawn toward the south-west. That tip is the end where the chain arrives.
    pieza = LineString([(-62.30, -32.40), (-62.35, -32.45)])
    orden = geometria_ordenada(MultiLineString([pieza, principal]))

    assert list(orden.geoms[0].coords) == list(principal.coords)
    assert list(orden.geoms[1].coords) == [(-62.35, -32.45), (-62.30, -32.40)]
    assert mapping(geometria_ordenada(orden)) == mapping(orden)


def test_stationing_starts_at_the_south_tip_and_heads_north() -> None:
    # The inland end is the westernmost vertex. It is not an extremity:
    # the chain ends at the south tip, and every piece heads north.
    sur = LineString([(-62.50, -32.64), (-62.48, -32.70)])
    medio = LineString([(-62.47, -32.60), (-62.48, -32.62)])
    norte = LineString([(-62.47, -32.59), (-62.35, -32.41)])
    orden = geometria_ordenada(MultiLineString([norte, medio, sur]))

    assert [list(parte.coords) for parte in orden.geoms] == [
        [(-62.48, -32.70), (-62.50, -32.64)],
        [(-62.48, -32.62), (-62.47, -32.60)],
        [(-62.47, -32.59), (-62.35, -32.41)],
    ]
    assert mapping(geometria_ordenada(orden)) == mapping(orden)


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


@pytest.mark.parametrize("metros", [8.0, 9.0, 40.0])
def test_a_gap_turns_the_piece_to_the_arrival_end(metros: float) -> None:
    dy = metros / _METROS_POR_GRADO
    principal = LineString([(-62.50, -32.50), (-62.49, -32.50)])
    punta = (-62.49, -32.50 + dy)
    lejos = (-62.48, -32.50)
    orden = geometria_ordenada(MultiLineString([LineString([lejos, punta]), principal]))

    assert orden.geoms[0].coords[0] == (-62.50, -32.50)
    assert orden.geoms[1].coords[0] == punta
