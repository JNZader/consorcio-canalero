"""Tests de burn_support: el quemado de canales en el DEM.

Rasters sinteticos chicos en disco, sin base de datos ni WhiteboxTools. Lo que
se fija aca es el CONTRATO del quemado: donde baja la cota, cuanto, y que el
resto del raster quede intacto — porque un quemado que toca celdas de mas crea
drenajes falsos y uno que toca de menos deja el canal invisible.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")

from rasterio.transform import from_origin  # noqa: E402

from app.domains.geo.burn_support import (  # noqa: E402
    DEFAULT_BURN_DEPTH_M,
    burn_canals_impl,
)

ANCHO = ALTO = 10
CELDA = 0.01  # grados por celda; el raster cubre [0, 0.1] x [0, 0.1]


def _dem_plano(path: Path, cota: float = 100.0, crs: str = "EPSG:4326") -> None:
    perfil = {
        "driver": "GTiff",
        "width": ANCHO,
        "height": ALTO,
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": from_origin(0.0, 0.1, CELDA, CELDA),
        "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **perfil) as dst:
        dst.write(np.full((ALTO, ANCHO), cota, dtype="float32"), 1)


def _linea_horizontal() -> str:
    """Traza que cruza el raster por el medio, de oeste a este."""
    return json.dumps({"type": "LineString", "coordinates": [[0.0, 0.055], [0.1, 0.055]]})


def _leer(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1)


def test_quema_la_traza_y_nada_mas(tmp_path: Path) -> None:
    dem = tmp_path / "dem.tif"
    salida = tmp_path / "quemado.tif"
    _dem_plano(dem)

    resultado = burn_canals_impl(
        dem_path=str(dem),
        canal_geojsons=[_linea_horizontal()],
        output_path=str(salida),
        burn_depth_m=10.0,
    )

    assert resultado == str(salida)
    quemado = _leer(salida)
    fila_del_canal = quemado[4]  # y=0.055 cae en la fila 4 (origen arriba)
    assert np.all(fila_del_canal == 90.0), fila_del_canal
    # El resto del raster queda EXACTAMENTE igual: celdas de mas quemadas son
    # drenajes falsos.
    resto = np.delete(quemado, 4, axis=0)
    assert np.all(resto == 100.0)


def test_la_zanja_es_continua_de_borde_a_borde(tmp_path: Path) -> None:
    """Una zanja cortada es peor que ninguna: el fill posterior la rellena y
    el canal desaparece del modelo sin dejar rastro."""
    dem = tmp_path / "dem.tif"
    salida = tmp_path / "quemado.tif"
    _dem_plano(dem)

    burn_canals_impl(
        dem_path=str(dem),
        canal_geojsons=[_linea_horizontal()],
        output_path=str(salida),
    )

    fila = _leer(salida)[4]
    assert np.all(fila < 100.0), f"zanja con huecos: {fila}"


def test_profundidad_por_defecto(tmp_path: Path) -> None:
    dem = tmp_path / "dem.tif"
    salida = tmp_path / "quemado.tif"
    _dem_plano(dem)

    burn_canals_impl(
        dem_path=str(dem),
        canal_geojsons=[_linea_horizontal()],
        output_path=str(salida),
    )

    assert np.min(_leer(salida)) == pytest.approx(100.0 - DEFAULT_BURN_DEPTH_M)


def test_sin_canales_devuelve_none_y_no_escribe(tmp_path: Path) -> None:
    """Area sin red digitalizada = caso normal. El pipeline sigue con el DEM
    original; escribir una copia identica solo confundiria (dos archivos
    iguales con nombres distintos)."""
    dem = tmp_path / "dem.tif"
    salida = tmp_path / "quemado.tif"
    _dem_plano(dem)

    assert burn_canals_impl(dem_path=str(dem), canal_geojsons=[], output_path=str(salida)) is None
    assert not salida.exists()


def test_profundidad_invalida_falla_ruidosamente(tmp_path: Path) -> None:
    dem = tmp_path / "dem.tif"
    _dem_plano(dem)

    for profundidad in (0.0, -5.0):
        with pytest.raises(ValueError):
            burn_canals_impl(
                dem_path=str(dem),
                canal_geojsons=[_linea_horizontal()],
                output_path=str(tmp_path / "x.tif"),
                burn_depth_m=profundidad,
            )


def test_reproyecta_cuando_el_dem_no_esta_en_4326(tmp_path: Path) -> None:
    """Las trazas viven en EPSG:4326 (canal_network); el DEM podria venir en
    otro CRS. Si la reproyeccion faltara, la traza caeria fuera del raster y
    el quemado seria un no-op SILENCIOSO — el peor modo de falla posible."""
    dem = tmp_path / "dem3857.tif"
    salida = tmp_path / "quemado.tif"
    perfil = {
        "driver": "GTiff",
        "width": ANCHO,
        "height": ALTO,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:3857",
        # Mismo footprint que el DEM 4326 de los otros tests, en metros.
        "transform": from_origin(0.0, 11132.0, 1113.2, 1113.2),
        "nodata": -9999.0,
    }
    with rasterio.open(dem, "w", **perfil) as dst:
        dst.write(np.full((ALTO, ANCHO), 100.0, dtype="float32"), 1)

    burn_canals_impl(
        dem_path=str(dem),
        canal_geojsons=[_linea_horizontal()],
        output_path=str(salida),
        burn_depth_m=10.0,
    )

    assert np.min(_leer(salida)) == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# load_propuesta_geojsons: la seleccion de propuestas para escenarios
# ---------------------------------------------------------------------------


def _archivo_propuestas(tmp_path: Path) -> Path:
    ruta = tmp_path / "propuestas.geojson"
    ruta.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": "n3-tramo", "nombre": "Tramo N3"},
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"id": "n5-otro"},
                        "geometry": {"type": "LineString", "coordinates": [[2, 2], [3, 3]]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"id": "punto-no-quemable"},
                        "geometry": {"type": "Point", "coordinates": [5, 5]},
                    },
                    {
                        "type": "Feature",
                        "properties": {},  # sin id: no seleccionable
                        "geometry": {"type": "LineString", "coordinates": [[6, 6], [7, 7]]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return ruta


def test_carga_las_propuestas_pedidas_en_orden(tmp_path: Path) -> None:
    from app.domains.geo.burn_support import load_propuesta_geojsons

    resultado = load_propuesta_geojsons(
        propuestas_path=str(_archivo_propuestas(tmp_path)),
        propuesta_ids=["n5-otro", "n3-tramo"],
    )

    assert len(resultado) == 2
    assert json.loads(resultado[0])["coordinates"] == [[2, 2], [3, 3]]
    assert json.loads(resultado[1])["coordinates"] == [[0, 0], [1, 1]]


def test_id_inexistente_es_error_ruidoso_no_skip(tmp_path: Path) -> None:
    """Quemar un escenario con menos obras de las pedidas produce una
    comparacion silenciosamente equivocada — sobre la que se justifica (o no)
    una obra. Mejor reventar con la lista de lo disponible."""
    from app.domains.geo.burn_support import load_propuesta_geojsons

    with pytest.raises(ValueError, match="no-existe"):
        load_propuesta_geojsons(
            propuestas_path=str(_archivo_propuestas(tmp_path)),
            propuesta_ids=["n3-tramo", "no-existe"],
        )


def test_una_propuesta_puntual_no_es_seleccionable(tmp_path: Path) -> None:
    """Un punto no es una traza quemable: pedirlo tiene que fallar como
    inexistente, no colarse degradando el escenario."""
    from app.domains.geo.burn_support import load_propuesta_geojsons

    with pytest.raises(ValueError, match="punto-no-quemable"):
        load_propuesta_geojsons(
            propuestas_path=str(_archivo_propuestas(tmp_path)),
            propuesta_ids=["punto-no-quemable"],
        )
