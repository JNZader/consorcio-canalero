"""Longitudinal elevation profile — GLO-30, never a burned surface.

The classifier already densifies traces every 15 m and samples ``dem_filled``.
This module exposes that series (distance vs elevation) without inventing
hydraulics. Nodata stays ``None`` so a gap is a gap, not sea level.
"""

from __future__ import annotations

import pytest
from shapely.geometry import LineString

from app.domains.geo.relevamiento.clasificador import (
    NOMBRE_DEM_FILLED,
    PASO_DENSIFICADO_M,
    DemFilledNoDisponible,
    densificar,
    resolver_dem_filled,
)


def test_densificar_keeps_half_cell_step_on_a_metric_line() -> None:
    from app.domains.geo.elevation_profile import distancias_sobre

    linea = LineString([(0.0, 0.0), (100.0, 0.0)])
    vertices = densificar(linea, PASO_DENSIFICADO_M)
    distancias = distancias_sobre(linea, vertices)
    assert vertices[0] == (0.0, 0.0)
    assert vertices[-1] == (100.0, 0.0)
    assert distancias[0] == 0.0
    assert distancias[-1] == pytest.approx(100.0, abs=1e-6)
    gaps = [distancias[i] - distancias[i - 1] for i in range(1, len(distancias))]
    assert max(gaps) <= PASO_DENSIFICADO_M + 1e-6


def test_paso_muestreo_keeps_15m_until_the_point_budget() -> None:
    from app.domains.geo.elevation_profile import MAX_POINTS, paso_muestreo

    assert paso_muestreo(10_000) == PASO_DENSIFICADO_M
    paso = paso_muestreo(40_000)
    assert paso > PASO_DENSIFICADO_M
    linea = LineString([(0.0, 0.0), (40_000.0, 0.0)])
    vertices = densificar(linea, paso)
    assert len(vertices) <= MAX_POINTS
    assert vertices[-1] == (40_000.0, 0.0)


def test_distancias_sobre_l_shape_is_true_chainage_not_index_uniform() -> None:
    from app.domains.geo.elevation_profile import distancias_sobre

    linea = LineString([(0.0, 0.0), (30.0, 0.0), (30.0, 40.0)])
    vertices = [(0.0, 0.0), (30.0, 0.0), (30.0, 40.0)]
    distancias = distancias_sobre(linea, vertices)
    assert distancias == pytest.approx([0.0, 30.0, 70.0])


def test_ensamblar_profile_keeps_nodata_holes_and_ignores_them_in_extrema() -> None:
    from app.domains.geo.elevation_profile import ensamblar_perfil

    payload = ensamblar_perfil(
        distancias_m=[0.0, 15.0, 30.0],
        cotas=[120.0, None, 110.0],
        dem_nombre=NOMBRE_DEM_FILLED,
    )
    assert payload["puntos"][1]["elevation_m"] is None
    assert "lon" not in payload["puntos"][0]
    assert payload["min_elevation_m"] == 110.0
    assert payload["max_elevation_m"] == 120.0
    assert payload["length_m"] == 30.0
    assert payload["source"] == NOMBRE_DEM_FILLED
    assert "30" in payload["disclaimer"]


def test_ensamblar_profile_attaches_lon_lat_for_the_map_cursor() -> None:
    from app.domains.geo.elevation_profile import ensamblar_perfil

    payload = ensamblar_perfil(
        distancias_m=[0.0, 15.0],
        cotas=[120.0, 118.0],
        dem_nombre=NOMBRE_DEM_FILLED,
        longitudes=[-62.7, -62.71],
        latitudes=[-32.6, -32.61],
    )
    assert payload["puntos"][0]["lon"] == pytest.approx(-62.7)
    assert payload["puntos"][1]["lat"] == pytest.approx(-32.61)


def test_ensamblar_profile_without_valid_samples_has_no_extrema() -> None:
    from app.domains.geo.elevation_profile import ensamblar_perfil

    payload = ensamblar_perfil(
        distancias_m=[0.0, 15.0],
        cotas=[None, None],
        dem_nombre=NOMBRE_DEM_FILLED,
    )
    assert payload["min_elevation_m"] is None
    assert payload["max_elevation_m"] is None


def test_resolver_dem_filled_still_refuses_a_burned_surface() -> None:
    with pytest.raises(DemFilledNoDisponible):
        resolver_dem_filled([{"filled_dem": "/tmp/dem_burned.tif"}])


def test_linea_vacia_no_es_un_perfil() -> None:
    from app.domains.geo.elevation_profile import perfil_desde_linea_metrica

    with pytest.raises(ValueError):
        perfil_desde_linea_metrica(LineString(), "/tmp/dem_filled.tif")


def test_elevation_profile_route_requires_operator() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.domains.geo.router import router as geo_router

    app = FastAPI()
    app.include_router(geo_router, prefix="/api/v2/geo")
    body = {
        "geometry": {
            "type": "LineString",
            "coordinates": [[-62.7, -32.6], [-62.71, -32.61]],
        }
    }
    with TestClient(app) as cliente:
        resp = cliente.post("/api/v2/geo/elevation-profile", json=body)
    assert resp.status_code == 401
