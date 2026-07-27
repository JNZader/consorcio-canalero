"""El cableado del stream burning dentro del pipeline DEM.

Lo que se fija aca no es el quemado en si (eso vive en test_burn_support.py)
sino LA PROPIEDAD DE DISEÑO: el DEM quemado es ficcion deliberada y solo puede
alimentar los derivados hidrologicos. Si alguien "simplifica" el pipeline a un
solo fill, o cruza las ramas, pasan cosas concretas y malas:

- pendiente/aspecto sobre el DEM quemado -> zanjas de 10 m que no existen en
  el visor 3D y pendientes disparatadas junto a cada canal;
- flow_dir/flow_acc sobre el DEM sin quemar -> el agua del modelo ignora el
  sistema de canales, que es el estado que este feature vino a corregir.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
from app.domains.geo.tasks_dem_support import process_dem_pipeline_impl


def _correr_pipeline(tmp_path, *, canal_geojsons: list[str], burn_canals=None):
    """Corre el impl con fakes; run_step ejecuta de verdad la funcion."""
    processing = MagicMock()
    burn = burn_canals or MagicMock(return_value=str(tmp_path / "output" / "dem_burned.tif"))

    resultado = process_dem_pipeline_impl(
        area_id="area-1",
        dem_path=str(tmp_path / "dem.tif"),
        bbox=None,
        job_id=str(uuid.uuid4()),
        fetch_canal_geojsons=MagicMock(return_value=canal_geojsons),
        burn_canals=burn,
        burn_depth_m=10.0,
        create_geo_job=MagicMock(),
        update_job=MagicMock(return_value=True),
        run_step=lambda job_id, name, fn, args, kwargs=None: fn(*args, **(kwargs or {})),
        get_processing=MagicMock(return_value=processing),
        register_raster_layer=MagicMock(),
        register_layer=MagicMock(),
        tipo_geo_job=TipoGeoJob,
        tipo_geo_layer=MagicMock(),
        estado_geo_job=EstadoGeoJob,
        formato_geo_layer=MagicMock(),
    )
    return resultado, processing, burn


def _llamadas(mock: MagicMock) -> list[tuple]:
    return [llamada.args for llamada in mock.call_args_list]


def test_con_canales_cada_familia_usa_su_dem(tmp_path) -> None:
    resultado, processing, burn = _correr_pipeline(
        tmp_path, canal_geojsons=['{"type":"LineString","coordinates":[[0,0],[1,1]]}']
    )

    salida = str(tmp_path / "output")
    dem_original = str(tmp_path / "dem.tif")
    quemado = f"{salida}/dem_burned.tif"
    fill_terreno = f"{salida}/dem_filled.tif"
    fill_hidro = f"{salida}/dem_filled_hydro.tif"

    # El quemado parte del DEM original y con la profundidad pedida.
    kwargs = burn.call_args.kwargs
    assert kwargs["dem_path"] == dem_original
    assert kwargs["burn_depth_m"] == 10.0

    # DOS fills, uno por familia.
    assert _llamadas(processing.fill_sinks) == [
        (dem_original, fill_terreno),
        (quemado, fill_hidro),
    ]

    # Familia hidrologica -> DEM QUEMADO rellenado.
    assert _llamadas(processing.compute_flow_direction)[0][0] == fill_hidro
    assert _llamadas(processing.compute_flow_accumulation)[0][0] == fill_hidro

    # Familia de terreno -> DEM REAL rellenado.
    assert _llamadas(processing.compute_slope)[0][0] == fill_terreno
    assert _llamadas(processing.compute_aspect)[0][0] == fill_terreno

    assert resultado["outputs"]["burned_dem"] == quemado
    assert resultado["outputs"]["filled_hydro_dem"] == fill_hidro


def test_sin_canales_no_quema_y_todo_usa_el_mismo_fill(tmp_path) -> None:
    """Area sin red digitalizada: el pipeline tiene que quedar IGUAL que antes
    de este feature — un solo fill y ninguna llamada al quemado."""
    resultado, processing, burn = _correr_pipeline(tmp_path, canal_geojsons=[])

    burn.assert_not_called()
    assert len(_llamadas(processing.fill_sinks)) == 1

    fill_unico = _llamadas(processing.fill_sinks)[0][1]
    assert _llamadas(processing.compute_flow_direction)[0][0] == fill_unico
    assert _llamadas(processing.compute_slope)[0][0] == fill_unico
    assert "burned_dem" not in resultado["outputs"]
    assert "filled_hydro_dem" not in resultado["outputs"]


def test_la_profundidad_queda_registrada_en_el_job(tmp_path) -> None:
    """Sin el valor en los parametros del job, dos corridas con profundidades
    distintas serian indistinguibles a posteriori."""
    create_geo_job = MagicMock(return_value=str(uuid.uuid4()))
    processing = MagicMock()

    process_dem_pipeline_impl(
        area_id="area-1",
        dem_path=str(tmp_path / "dem.tif"),
        bbox=None,
        job_id=None,  # fuerza la creacion del job
        fetch_canal_geojsons=MagicMock(return_value=[]),
        burn_canals=MagicMock(),
        burn_depth_m=7.5,
        create_geo_job=create_geo_job,
        update_job=MagicMock(return_value=True),
        run_step=lambda job_id, name, fn, args, kwargs=None: fn(*args, **(kwargs or {})),
        get_processing=MagicMock(return_value=processing),
        register_raster_layer=MagicMock(),
        register_layer=MagicMock(),
        tipo_geo_job=TipoGeoJob,
        tipo_geo_layer=MagicMock(),
        estado_geo_job=EstadoGeoJob,
        formato_geo_layer=MagicMock(),
    )

    assert create_geo_job.call_args.kwargs["parametros"]["burn_depth_m"] == 7.5
