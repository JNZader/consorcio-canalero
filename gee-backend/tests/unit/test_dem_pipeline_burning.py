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


def _correr_pipeline(
    tmp_path,
    *,
    canal_geojsons: list[str],
    burn_canals=None,
    escenario_propuestas=None,
    propuesta_geojsons=None,
    register_raster_layer=None,
):
    """Corre el impl con fakes; run_step ejecuta de verdad la funcion."""
    processing = MagicMock()
    burn = burn_canals or MagicMock(return_value=str(tmp_path / "output" / "dem_burned.tif"))
    registrar = register_raster_layer if register_raster_layer is not None else MagicMock()

    resultado = process_dem_pipeline_impl(
        area_id="area-1",
        dem_path=str(tmp_path / "dem.tif"),
        bbox=None,
        job_id=str(uuid.uuid4()),
        fetch_canal_geojsons=MagicMock(return_value=canal_geojsons),
        fetch_propuesta_geojsons=MagicMock(return_value=propuesta_geojsons or []),
        escenario_propuestas=escenario_propuestas,
        archive_previous_output=MagicMock(return_value=None),
        run_timestamp="20260727_000000",
        burn_canals=burn,
        burn_depth_m=10.0,
        create_geo_job=MagicMock(),
        update_job=MagicMock(return_value=True),
        run_step=lambda job_id, name, fn, args, kwargs=None: fn(*args, **(kwargs or {})),
        get_processing=MagicMock(return_value=processing),
        register_raster_layer=registrar,
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
        fetch_propuesta_geojsons=MagicMock(return_value=[]),
        escenario_propuestas=None,
        archive_previous_output=MagicMock(return_value=None),
        run_timestamp="20260727_000000",
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


def test_escenario_quema_relevados_MAS_propuestas(tmp_path) -> None:
    """El escenario simula 'como drenaria SI se construyen las obras': quema
    la red real completa Y las propuestas seleccionadas, no solo estas."""
    canal = '{"type":"LineString","coordinates":[[0,0],[1,1]]}'
    propuesta = '{"type":"LineString","coordinates":[[2,2],[3,3]]}'
    resultado, processing, burn = _correr_pipeline(
        tmp_path,
        canal_geojsons=[canal],
        escenario_propuestas=["n3-tramo"],
        propuesta_geojsons=[propuesta],
    )

    # Dos quemados: el operativo (solo red real) y el del escenario (ambas).
    assert burn.call_count == 2
    kwargs_escenario = burn.call_args_list[1].kwargs
    assert kwargs_escenario["canal_geojsons"] == [canal, propuesta]
    assert "escenario" in kwargs_escenario["output_path"]

    # La cadena del escenario existe completa en los outputs.
    for clave in (
        "burned_dem_escenario",
        "filled_dem_escenario",
        "flow_dir_escenario",
        "flow_acc_escenario",
    ):
        assert clave in resultado["outputs"], clave


def test_escenario_jamas_pisa_las_capas_operativas(tmp_path) -> None:
    """LA regla de segregacion. Si una capa de escenario se registrara con un
    nombre operativo, el mapa mostraria drenaje de canales que nadie
    construyo y un operador tomaria decisiones sobre obras inexistentes."""
    registros = MagicMock()
    _correr_pipeline(
        tmp_path,
        canal_geojsons=['{"type":"LineString","coordinates":[[0,0],[1,1]]}'],
        escenario_propuestas=["n3-tramo"],
        propuesta_geojsons=['{"type":"LineString","coordinates":[[2,2],[3,3]]}'],
        register_raster_layer=registros,
    )

    nombres = [c.kwargs["nombre"] for c in registros.call_args_list]
    de_escenario = [n for n in nombres if "escenario" in n]
    operativas = [n for n in nombres if "escenario" not in n]

    # Las capas del escenario llevan SIEMPRE el prefijo `escenario_`. Se listan
    # todas: si el pipeline agrega una variante de escenario nueva, tiene que
    # aparecer aca CON prefijo, nunca con nombre operativo.
    assert set(de_escenario) == {
        "escenario_flow_dir_area-1",
        "escenario_flow_acc_area-1",
        "escenario_hand_area-1",
        "escenario_twi_area-1",
    }
    # Y las operativas (relevado) conviven: mismas capas de siempre.
    assert "flow_dir_area-1" in operativas
    assert "flow_acc_area-1" in operativas
    assert "hand_area-1" in operativas
    assert "twi_area-1" in operativas
    # La variante NATURAL tambien esta, con su prefijo propio.
    assert "natural_flow_acc_area-1" in operativas  # "escenario" not in name
    assert "natural_hand_area-1" in operativas


def test_sin_escenario_no_hay_rastro_de_simulacion(tmp_path) -> None:
    registros = MagicMock()
    resultado, _, burn = _correr_pipeline(
        tmp_path,
        canal_geojsons=['{"type":"LineString","coordinates":[[0,0],[1,1]]}'],
        register_raster_layer=registros,
    )

    assert burn.call_count == 1  # solo el quemado operativo
    assert not [k for k in resultado["outputs"] if "escenario" in k]
    assert not [c for c in registros.call_args_list if "escenario" in c.kwargs["nombre"]]


def test_los_ids_del_escenario_quedan_en_el_job(tmp_path) -> None:
    """Sin los ids en los parametros, dos escenarios distintos serian
    indistinguibles a posteriori — y una comparacion sin trazabilidad no
    sirve como argumento tecnico para justificar una obra."""
    create_geo_job = MagicMock(return_value=str(uuid.uuid4()))

    process_dem_pipeline_impl(
        area_id="area-1",
        dem_path=str(tmp_path / "dem.tif"),
        bbox=None,
        job_id=None,
        fetch_canal_geojsons=MagicMock(return_value=[]),
        fetch_propuesta_geojsons=MagicMock(return_value=[]),
        escenario_propuestas=["n3-tramo", "n5-otro"],
        archive_previous_output=MagicMock(return_value=None),
        run_timestamp="20260727_000000",
        burn_canals=MagicMock(),
        burn_depth_m=10.0,
        create_geo_job=create_geo_job,
        update_job=MagicMock(return_value=True),
        run_step=lambda job_id, name, fn, args, kwargs=None: fn(*args, **(kwargs or {})),
        get_processing=MagicMock(),
        register_raster_layer=MagicMock(),
        register_layer=MagicMock(),
        tipo_geo_job=TipoGeoJob,
        tipo_geo_layer=MagicMock(),
        estado_geo_job=EstadoGeoJob,
        formato_geo_layer=MagicMock(),
    )

    parametros = create_geo_job.call_args.kwargs["parametros"]
    assert parametros["escenario_propuestas"] == ["n3-tramo", "n5-otro"]


def test_el_pipeline_completo_propaga_el_escenario(tmp_path) -> None:
    """El full pipeline (el que dispara el boton) tiene que pasarle el
    escenario al process_dem_pipeline interno.

    Era un hueco real: el escenario funcionaba por el pipeline corto pero el
    full lo ignoraba, asi que el boton nunca generaba las capas de escenario.
    """
    from app.domains.geo.tasks_dem_support import run_full_dem_pipeline_impl

    proceso = MagicMock(return_value={"outputs": {}})

    run_full_dem_pipeline_impl(
        area_id="zona_principal",
        min_basin_area_ha=50.0,
        escenario_propuestas=["s3-colector-p8", "s3-colector-p9"],
        job_id=str(uuid.uuid4()),
        create_geo_job=MagicMock(),
        update_job=MagicMock(return_value=True),
        cleanup_full_dem_state=MagicMock(),
        prepare_full_pipeline_dem=MagicMock(return_value=("/d/dem.tif", "/d/prep.tif")),
        process_dem_pipeline=proceso,
        generate_auto_basins=MagicMock(return_value=(0, None, None)),
        tipo_geo_job=TipoGeoJob,
        estado_geo_job=EstadoGeoJob,
    )

    # El escenario tiene que haber llegado tal cual al pipeline interno.
    assert proceso.call_args.kwargs["escenario_propuestas"] == [
        "s3-colector-p8",
        "s3-colector-p9",
    ]


def test_el_pipeline_completo_registra_el_escenario_en_el_job(tmp_path) -> None:
    from app.domains.geo.tasks_dem_support import run_full_dem_pipeline_impl

    create_geo_job = MagicMock(return_value=str(uuid.uuid4()))

    run_full_dem_pipeline_impl(
        area_id="zona_principal",
        min_basin_area_ha=50.0,
        escenario_propuestas=["s3-colector-p8"],
        job_id=None,  # fuerza la creacion
        create_geo_job=create_geo_job,
        update_job=MagicMock(return_value=True),
        cleanup_full_dem_state=MagicMock(),
        prepare_full_pipeline_dem=MagicMock(return_value=("/d/dem.tif", "/d/prep.tif")),
        process_dem_pipeline=MagicMock(return_value={"outputs": {}}),
        generate_auto_basins=MagicMock(return_value=(0, None, None)),
        tipo_geo_job=TipoGeoJob,
        estado_geo_job=EstadoGeoJob,
    )

    assert create_geo_job.call_args.kwargs["parametros"]["escenario_propuestas"] == [
        "s3-colector-p8"
    ]


def test_hand_twi_flow_acc_tienen_TRES_variantes(tmp_path) -> None:
    """El pedido del usuario: natural / relevado / escenario, conviviendo.

    Para HAND, TWI y flow_acc tienen que registrarse las tres capas con nombres
    distintos (prefijo natural_ / sin prefijo / escenario_). El upsert por
    nombre (otro fix) es lo que permite que no se pisen; aca se verifica que el
    pipeline las EMITE.
    """
    registros = MagicMock()
    _correr_pipeline(
        tmp_path,
        canal_geojsons=['{"type":"LineString","coordinates":[[0,0],[1,1]]}'],
        escenario_propuestas=["s3"],
        propuesta_geojsons=['{"type":"LineString","coordinates":[[2,2],[3,3]]}'],
        register_raster_layer=registros,
    )
    nombres = {c.kwargs["nombre"] for c in registros.call_args_list}

    for base in ("hand", "twi", "flow_acc"):
        assert f"natural_{base}_area-1" in nombres, f"falta natural de {base}"
        assert f"{base}_area-1" in nombres, f"falta relevado de {base}"
        assert f"escenario_{base}_area-1" in nombres, f"falta escenario de {base}"


def test_sin_canales_no_hay_variante_natural(tmp_path) -> None:
    """Area sin red: `filled` y `filled_hydro` son el mismo DEM, asi que el
    flujo natural coincide con el relevado. No se registran capas natural_
    duplicadas."""
    registros = MagicMock()
    _correr_pipeline(tmp_path, canal_geojsons=[], register_raster_layer=registros)
    nombres = {c.kwargs["nombre"] for c in registros.call_args_list}

    assert not any(n.startswith("natural_") for n in nombres)
    # pero las capas operativas siguen (un solo drenaje, sin quemado)
    assert "hand_area-1" in nombres
    assert "flow_acc_area-1" in nombres
