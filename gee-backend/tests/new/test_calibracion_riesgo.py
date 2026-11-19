"""Calibración de flood_risk: agua observada por clase (PR 5, S4-S7).

Real PostGIS + real raster grids, GEE/CHIRPS SEAMS faked — the network is
never touched except by the ONE opt-in live test at the bottom.

Covers the plan's S6 verbatim list plus the S9 threshold edge:

* synthetic mask covering ALL of Crítico → ``pct_con_agua`` 100 %;
* Σ ``ha_clase`` == the raster's valid area (the "zone area" invariant);
* the HCI per zone CHANGES when the real flood history replaces the 0.3
  constant (S10), and the fixed fallback is MARKED, not silent;
* threshold derivation (#738): 62 and 72 land in ``ha_alto`` (the legacy-70
  gap), 80 in ``ha_critico``, 54.9 in neither, and ``area_high_risk_ha``
  is the legend sum;
* the ETL is idempotent (re-run = same rows) and per-event isolated;
* the monotonicity verdict (S7) — the gate for S11's per-class phrases —
  reads True on a coherent world and False on an inverted one;
* the informe renders the validation table + the ``leyenda-55`` tag.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import date
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.calibracion_riesgo import (
    FilaClase,
    clasificar_agua_por_clase,
    leer_grilla_riesgo,
    lluvia_30d_gee,
    run_calibracion,
    veredicto_monotonia,
)
from app.db.migrations.versions import (
    zz_composite_ha_alto_critico as migracion_composite,
    zz_riesgo_validacion_evento as migracion_validacion,
)

pypdf = pytest.importorskip("pypdf")

# Dedicated world (same discipline as the informe tests: nothing else seeds
# near lon -61.9). 160 px wide: four 40-px column blocks, one per class.
LON0, LAT0 = -61.9, -32.0
PASO = 0.001  # ~94.5 m x 111.3 m per pixel at this latitude
ALTO_px, ANCHO_px = 40, 160
NODATA = -9999.0

# Column block → (score, class label). The values sit INSIDE each legend bin
# (10 Bajo, 40 Medio, 62 Alto, 90 Crítico) — 62 exercises exactly the
# legacy-70 gap the old threshold used to miss.
BLOQUES = [
    (10.0, "Bajo"),
    (40.0, "Medio"),
    (62.0, "Alto"),
    (90.0, "Crítico"),
]


def _px_ha() -> float:
    """Pixel hectares at the raster's CENTER latitude (the same math as
    ``composites._pixel_area`` — geographic rasters are approximated at the
    middle of their extent, not at a corner)."""
    import math

    centro = LAT0 + PASO * ALTO_px / 2.0
    m_lon = 111_320.0 * PASO * math.cos(math.radians(centro))
    m_lat = 111_320.0 * PASO
    return m_lon * m_lat / 10_000.0


def _raster_riesgo(path, valores_por_bloque: list[float]) -> str:
    """Four column blocks of constant score, one per legend class."""
    datos = np.zeros((ALTO_px, ANCHO_px), dtype="float32")
    for indice, valor in enumerate(valores_por_bloque):
        datos[:, indice * 40 : (indice + 1) * 40] = valor
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=ALTO_px,
        width=ANCHO_px,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON0, LAT0 + PASO * ALTO_px, PASO, PASO),
        nodata=NODATA,
    ) as dst:
        dst.write(datos, 1)
    return str(path)


def _tif_agua(fracciones: dict[str, float], grilla) -> bytes:
    """Water GeoTIFF ON the risk grid: fraction of each class block flooded.

    A fraction f marks the first ``round(f * ALTO_px)`` ROWS of the block —
    deterministic, and exactly 1.0 floods the whole class (S6's 100 % case).
    """
    con_agua = np.zeros((grilla.height, grilla.width), dtype="uint8")
    for indice, (_valor, clase) in enumerate(BLOQUES):
        filas = round(fracciones.get(clase, 0.0) * ALTO_px)
        con_agua[:filas, indice * 40 : (indice + 1) * 40] = 1
    buffer = io.BytesIO()
    a, b, c, d, e, f = grilla.transform
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=grilla.height,
        width=grilla.width,
        count=1,
        dtype="uint8",
        crs=grilla.crs,
        transform=rasterio.Affine(a, b, c, d, e, f),
    ) as dst:
        dst.write(con_agua, 1)
    return buffer.getvalue()


@pytest.fixture
def aplicar_migraciones(db):
    """The two PR-5 migrations, idempotent (persisted test DBs lack them)."""
    for statement in migracion_composite.UPGRADE_STATEMENTS:
        db.execute(text(statement))
    for statement in migracion_validacion.UPGRADE_STATEMENTS:
        db.execute(text(statement))
    db.flush()
    return db


def _sembrar_eventos(db: Session, claves: list[str]) -> None:
    """Anchor events + rank-1 candidates, uncommitted (rollback world)."""
    for clave in claves:
        db.execute(
            text(
                "INSERT INTO rainfall_extreme_event "
                "(id, source_id, scope_kind, scope_id, scope_version, detector_revision, "
                " provenance, event_key, start_date, end_date, curated_payload) "
                "VALUES (:id, 'chirps-v3-final', 'provider_asset', 'zona_cc_ampliada', "
                "        'v1', 'curated', 'curated', :k, CAST(:d AS date), CAST(:d AS date), "
                "        CAST(:p AS json))"
            ),
            {
                "id": uuid.uuid4(),
                "k": clave,
                "d": "2015-03-15",
                "p": json.dumps({"name": f"Evento {clave}"}),
            },
        )
        db.execute(
            text(
                "INSERT INTO rainfall_event_imagery_candidate "
                "(id, event_key, scorer_revision, sensor, scene_id, scene_date, "
                " days_from_peak, cloud_pct, cloud_basis, score, rank, visualization, slot) "
                "VALUES (:id, :k, 'caltest', 'landsat8', :sc, CAST(:sd AS date), "
                "        0, 10.0, 'scene', 99.0, 1, 'falso_color', 'ranked')"
            ),
            {
                "id": uuid.uuid4(),
                "k": clave,
                "sc": f"LANDSAT/LC08/C02/T1_TOA/LC08_{clave}",
                "sd": "2015-03-16",
            },
        )
    db.flush()


def _filas_validacion(db: Session, evento_key: str) -> list[Any]:
    return db.execute(
        text(
            "SELECT clase, ha_clase, ha_con_agua, pct_con_agua, lluvia_30d_mm, "
            "sensor, escena_id, version_flood_risk "
            "FROM riesgo_validacion_evento WHERE evento_key = :k ORDER BY clase"
        ),
        {"k": evento_key},
    ).all()


# ── S6: the synthetic-mask contract ──────────────────────────────────────────


def test_todo_el_critico_con_agua_da_cien(tmp_path, aplicar_migraciones):
    """S6 verbatim: todo el Crítico bajo agua → pct_con_agua 100 %."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    grilla = leer_grilla_riesgo(ruta)
    agua = _tif_agua({"Crítico": 1.0}, grilla)

    filas = clasificar_agua_por_clase(ruta, agua)
    por_clase = {fila.clase: fila for fila in filas}

    assert por_clase["Crítico"].pct_con_agua == 100.0
    assert por_clase["Crítico"].ha_con_agua == pytest.approx(
        por_clase["Crítico"].ha_clase, rel=1e-6
    )
    # The other classes stay dry in this world.
    assert por_clase["Bajo"].pct_con_agua == 0.0


def test_suma_ha_clase_es_el_area_de_la_zona(tmp_path, aplicar_migraciones):
    """S6 verbatim: Σ ha_clase == the raster's (the zone's) valid area."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    grilla = leer_grilla_riesgo(ruta)
    agua = _tif_agua({"Medio": 0.5}, grilla)

    filas = clasificar_agua_por_clase(ruta, agua)
    total = sum(fila.ha_clase for fila in filas)
    esperado = ALTO_px * ANCHO_px * _px_ha()

    assert total == pytest.approx(esperado, rel=1e-4)
    # Every class carries exactly its block: a quarter of the zone each.
    for fila in filas:
        assert fila.ha_clase == pytest.approx(esperado / 4.0, rel=1e-4)


def test_agua_parcial_por_clase_y_pct(tmp_path, aplicar_migraciones):
    """30 % del Medio y 60 % del Alto bajo agua → 30,0 / 60,0 exactos."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    grilla = leer_grilla_riesgo(ruta)
    agua = _tif_agua({"Medio": 0.30, "Alto": 0.60}, grilla)

    por_clase = {fila.clase: fila for fila in clasificar_agua_por_clase(ruta, agua)}
    assert por_clase["Medio"].pct_con_agua == 30.0
    assert por_clase["Alto"].pct_con_agua == 60.0
    assert por_clase["Medio"].ha_con_agua == pytest.approx(
        por_clase["Medio"].ha_clase * 0.30, rel=1e-6
    )


def test_grilla_de_agua_desalineada_es_error(tmp_path):
    """A water grid that does not match the risk raster is a hard error —
    silently resampling one side onto the other measures nothing."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    grilla = leer_grilla_riesgo(ruta)

    # Same world, but a HALF-WIDTH water grid: same intent, wrong geometry.
    con_agua = np.ones((grilla.height, grilla.width // 2), dtype="uint8")
    buffer = io.BytesIO()
    a, b, c, d, e, f = grilla.transform
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=grilla.height,
        width=grilla.width // 2,
        count=1,
        dtype="uint8",
        crs=grilla.crs,
        transform=rasterio.Affine(a, b, c, d, e, f),
    ) as dst:
        dst.write(con_agua, 1)

    with pytest.raises(ValueError, match="no coincide"):
        clasificar_agua_por_clase(ruta, buffer.getvalue())


# ── S9: the threshold derivation (#738) ──────────────────────────────────────


def _zona_cubrecartes() -> list[dict[str, Any]]:
    """One zone polygon covering the whole synthetic raster."""
    from shapely.geometry import mapping, shape

    ancho_deg = PASO * ANCHO_px
    alto_deg = PASO * ALTO_px
    poligono = shape(
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [LON0, LAT0],
                    [LON0 + ancho_deg, LAT0],
                    [LON0 + ancho_deg, LAT0 + alto_deg],
                    [LON0, LAT0 + alto_deg],
                    [LON0, LAT0],
                ]
            ],
        }
    )
    return [{"id": uuid.uuid4(), "geometry": mapping(poligono)}]


@pytest.mark.parametrize(
    ("valor", "esperado_alto", "esperado_critico"),
    [
        (54.9, 0.0, 0.0),  # below the Alto edge: neither (the legend's own cut)
        (62.0, 1.0, 0.0),  # the legacy-70 gap: 62 > 55 but < 70 AND < 75
        (72.0, 1.0, 0.0),  # above 70, still Alto — the split matters here
        (80.0, 0.0, 1.0),  # Crítico
    ],
)
def test_umbral_deriva_de_la_leyenda(tmp_path, valor, esperado_alto, esperado_critico):
    """62/72 count in ha_alto (not ha_critico); 80 in ha_critico; 54.9 in neither."""
    from app.domains.geo.composites import extract_composite_zonal_stats

    ruta = str(tmp_path / f"cte_{valor}.tif")
    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON0, LAT0 + 0.01, PASO, PASO),
        nodata=NODATA,
    ) as dst:
        dst.write(np.full((10, 10), valor, dtype="float32"), 1)

    resultado = extract_composite_zonal_stats(ruta, _zona_cubrecartes(), "flood_risk")
    assert len(resultado) == 1
    fila = resultado[0]

    area_total = 100 * _px_ha()
    assert fila["ha_alto"] == pytest.approx(esperado_alto * area_total, rel=1e-3)
    assert fila["ha_critico"] == pytest.approx(esperado_critico * area_total, rel=1e-3)
    # The compatibility column is the legend SUM, never the legacy >70 count.
    assert fila["area_high_risk_ha"] == pytest.approx(
        fila["ha_alto"] + fila["ha_critico"], rel=1e-9
    )
    if esperado_alto == 0.0 and esperado_critico == 0.0:
        assert fila["area_high_risk_ha"] == 0.0


def test_umbral_por_tipo_drenaje_usa_su_leyenda(tmp_path):
    """drainage_need derives from ITS OWN legend (Alto 50-70, Crítico ≥70):
    a constant 60 is Alto for drainage while it would be Alto for flood too —
    but a constant 45 is BELOW drainage's Alto and above flood's Bajo."""
    from app.domains.geo.composites import extract_composite_zonal_stats

    ruta = str(tmp_path / "cte_45.tif")
    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON0, LAT0 + 0.01, PASO, PASO),
        nodata=NODATA,
    ) as dst:
        dst.write(np.full((10, 10), 45.0, dtype="float32"), 1)

    fila = extract_composite_zonal_stats(ruta, _zona_cubrecartes(), "drainage_need")[0]
    assert fila["ha_alto"] == 0.0  # 45 < 50 (drainage's Alto edge)
    assert fila["ha_critico"] == 0.0


# ── S10: the real flood history ──────────────────────────────────────────────


def test_indice_hci_cambia_con_historial_real():
    """S6 verbatim: the per-zone index CHANGES when the real history changes."""
    from app.domains.geo.intelligence.calculations import (
        calcular_indice_criticidad_hidrica,
    )

    base = dict(pendiente=0.4, acumulacion=0.5, twi=0.6, dist_canal=0.5)
    fijo = calcular_indice_criticidad_hidrica(hist_inundacion=0.3, **base)
    real = calcular_indice_criticidad_hidrica(hist_inundacion=0.55, **base)
    assert fijo != real
    # Determinism: same inputs, same index.
    assert fijo == calcular_indice_criticidad_hidrica(hist_inundacion=0.3, **base)


def test_historial_desde_tabla_promedia_eventos(db, aplicar_migraciones):
    """Mean over the anchor events' zone water share; marked, not guessed."""
    from app.domains.geo.intelligence.tasks import (
        HISTORIAL_INUNDACION_POR_DEFECTO,
        historial_inundacion_desde_validacion,
    )

    def _evento(clave: str, ha_clase: float, ha_agua: float) -> None:
        db.execute(
            text(
                "INSERT INTO riesgo_validacion_evento "
                "(id, evento_key, fecha, clase, ha_clase, ha_con_agua, pct_con_agua, "
                " lluvia_30d_mm, sensor, escena_id, version_flood_risk) "
                "VALUES (:id, :k, CAST('2015-03-15' AS date), 'Alto', :hc, :ha, "
                "        :pct, 200.0, 'landsat8', 'LC08_x', 'vtest')"
            ),
            {
                "id": uuid.uuid4(),
                "k": clave,
                "hc": ha_clase,
                "ha": ha_agua,
                "pct": round(ha_agua / ha_clase * 100.0, 2),
            },
        )

    _evento("cal_e1", 1000.0, 200.0)  # 20 % under water
    _evento("cal_e2", 1000.0, 400.0)  # 40 % under water
    db.flush()

    historial, historial_fijo = historial_inundacion_desde_validacion(db)
    assert historial == pytest.approx(0.30, abs=1e-6)
    assert historial_fijo is False

    # No data at all → the fixed 0.3, MARKED (S10).
    db.execute(text("DELETE FROM riesgo_validacion_evento"))
    db.flush()
    historial, historial_fijo = historial_inundacion_desde_validacion(db)
    assert historial == HISTORIAL_INUNDACION_POR_DEFECTO
    assert historial_fijo is True

    # Table missing entirely (a deployment without the migration) → same
    # honest fallback. Transactional DDL: the DROP rolls back with the test.
    db.execute(text("DROP TABLE riesgo_validacion_evento"))
    historial, historial_fijo = historial_inundacion_desde_validacion(db)
    assert historial == HISTORIAL_INUNDACION_POR_DEFECTO
    assert historial_fijo is True


# ── S5/S4: the ETL, idempotent and per-event isolated ────────────────────────


def _correr_etl(db, ruta_riesgo, fracciones, claves=("cal_ev1",), lluvia=210.0):
    _sembrar_eventos(db, list(claves))
    return _correr_etl_sin_sembrar(db, ruta_riesgo, fracciones, claves, lluvia)


def _correr_etl_sin_sembrar(db, ruta_riesgo, fracciones, claves=("cal_ev1",), lluvia=210.0):
    grilla = leer_grilla_riesgo(ruta_riesgo)

    def fetch_agua(sensor: str, scene_id: str, g) -> bytes:
        assert sensor == "landsat8"
        assert scene_id.endswith(tuple(claves))
        return _tif_agua(fracciones, g)

    return run_calibracion(
        db,
        fetch_agua=fetch_agua,
        fetch_lluvia=lambda _fecha: lluvia,
        flood_path=ruta_riesgo,
        version_flood_risk="v-test",
    )


def test_etl_carga_filas_y_es_idempotente(db, aplicar_migraciones, tmp_path):
    """S4: one row per event×class, whole zone; re-run = the SAME rows."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    fracciones = {"Bajo": 0.0, "Medio": 0.3, "Alto": 0.6, "Crítico": 1.0}

    _sembrar_eventos(db, ["cal_ev1"])
    resultado = _correr_etl_sin_sembrar(db, ruta, fracciones)
    assert resultado["status"] == "completed"
    assert resultado["eventos_cargados"] == 1

    filas = _filas_validacion(db, "cal_ev1")
    assert [f.clase for f in filas] == ["Alto", "Bajo", "Crítico", "Medio"]
    por_clase = {f.clase: f for f in filas}
    assert por_clase["Crítico"].pct_con_agua == 100.0
    assert por_clase["Alto"].pct_con_agua == 60.0
    assert por_clase["Medio"].pct_con_agua == 30.0
    assert all(f.lluvia_30d_mm == 210.0 for f in filas)
    assert all(f.sensor == "landsat8" for f in filas)
    assert all(f.version_flood_risk == "v-test" for f in filas)

    primera = [(f.clase, f.ha_clase, f.ha_con_agua, f.pct_con_agua) for f in filas]

    # Re-run with the same scene + raster: DELETE-then-insert of the same
    # measurements — same rows, no duplicates, no drift.
    _correr_etl_sin_sembrar(db, ruta, fracciones)
    filas2 = _filas_validacion(db, "cal_ev1")
    assert len(filas2) == len(filas)
    segunda = [(f.clase, f.ha_clase, f.ha_con_agua, f.pct_con_agua) for f in filas2]
    assert segunda == primera


def test_etl_evento_sin_candidata_se_reporta_y_no_falla(db, aplicar_migraciones, tmp_path):
    """S8 per-event isolation: an event without a candidate is skipped with
    a motivo; the others still load."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    _sembrar_eventos(db, ["cal_con", "cal_sin"])
    db.execute(text("DELETE FROM rainfall_event_imagery_candidate WHERE event_key = 'cal_sin'"))
    db.flush()
    grilla = leer_grilla_riesgo(ruta)

    resultado = run_calibracion(
        db,
        fetch_agua=lambda _s, _sc, g: _tif_agua({"Crítico": 1.0}, g),
        fetch_lluvia=lambda _f: 100.0,
        flood_path=ruta,
        version_flood_risk="v-test",
    )
    assert resultado["eventos_cargados"] == 1
    por_clave = {e["evento_key"]: e for e in resultado["eventos"]}
    assert por_clave["cal_sin"]["motivo"] == "sin candidata de imagen"
    assert por_clave["cal_con"]["filas"] == 4


def test_etl_falla_de_gee_por_evento_no_tumba_el_resto(db, aplicar_migraciones, tmp_path):
    """A GEE failure on one event skips THAT event; the rest still loads."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    _sembrar_eventos(db, ["cal_ok", "cal_mal"])
    grilla = leer_grilla_riesgo(ruta)

    def fetch_agua(_sensor: str, scene_id: str, g):
        if "cal_mal" in scene_id:
            raise RuntimeError("GEE quota exceeded")
        return _tif_agua({"Crítico": 0.5}, g)

    resultado = run_calibracion(
        db,
        fetch_agua=fetch_agua,
        fetch_lluvia=lambda _f: 50.0,
        flood_path=ruta,
        version_flood_risk="v-test",
    )
    por_clave = {e["evento_key"]: e for e in resultado["eventos"]}
    assert por_clave["cal_ok"]["filas"] == 4
    assert "RuntimeError" in por_clave["cal_mal"]["motivo"]


# ── S7/S11: the monotonicity verdict that gates the phrases ──────────────────


def test_veredicto_monotonia_mundo_coherente(tmp_path, aplicar_migraciones):
    """Water share growing Bajo→Crítico reads monotónico True (S7 esperable)."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    grilla = leer_grilla_riesgo(ruta)
    agua = _tif_agua({"Bajo": 0.0, "Medio": 0.3, "Alto": 0.6, "Crítico": 1.0}, grilla)

    veredicto = veredicto_monotonia(clasificar_agua_por_clase(ruta, agua))
    assert veredicto["monotonico"] is True
    assert veredicto["motivo"] is None


def test_veredicto_monotonia_mundo_invertido(tmp_path, aplicar_migraciones):
    """The gate itself: an inverted world (Bajo flooded, Crítico dry) MUST
    read False — this is the verdict that keeps S11's phrases unpublished."""
    ruta = _raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES])
    grilla = leer_grilla_riesgo(ruta)
    agua = _tif_agua({"Bajo": 0.9, "Medio": 0.5, "Alto": 0.2, "Crítico": 0.0}, grilla)

    veredicto = veredicto_monotonia(clasificar_agua_por_clase(ruta, agua))
    assert veredicto["monotonico"] is False


def test_veredicto_monotonia_empates_se_tolera(tmp_path):
    """Ties are tolerated (weak monotonicity): the gate is "crece"."""
    filas = [
        FilaClase(clase=clase, ha_clase=100.0, ha_con_agua=40.0, pct_con_agua=40.0)
        for clase in ("Bajo", "Medio", "Alto", "Crítico")
    ]
    assert veredicto_monotonia(filas)["monotonico"] is True


def test_veredicto_monotonia_clases_ausentes(tmp_path):
    filas = [FilaClase("Bajo", 100.0, 0.0, 0.0), FilaClase("Alto", 100.0, 10.0, 10.0)]
    veredicto = veredicto_monotonia(filas)
    assert veredicto["monotonico"] is False
    assert veredicto["motivo"] == "clases ausentes"


# ── the informe: validation table + leyenda-55 ───────────────────────────────


def _datos_informe(validacion: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "nombre": "Informe calibración",
        "generado_el": "2026-11-19T12:00:00+00:00",
        "area_ha": 1234.5,
        "cantidad_zonas": 1,
        "cuencas": ["cuenca-cal"],
        "riesgo": {"cobertura": "sin_cobertura", "clases": [], "area_ha": 1234.5},
        "drenaje": None,
        "suelos": None,
        "cobertura": None,
        "canales": None,
        "imagenes": [],
        "lluvia": {},
        "desglose": None,
        "umbral_alto_critico": "leyenda-55",
        "riesgo_validacion": validacion,
        "degradado": [],
        "fuentes": [],
    }


def _validacion_dataset() -> dict[str, Any]:
    return {
        "eventos": [
            {
                "evento_key": "mar_2015",
                "fecha": "2015-03-15",
                "sensor": "landsat8",
                "escena": "LC08_123",
                "lluvia_30d_mm": 187.4,
                "clases": {
                    "Bajo": {"ha_clase": 1000.0, "ha_con_agua": 10.0, "pct_con_agua": 1.0},
                    "Medio": {"ha_clase": 1000.0, "ha_con_agua": 100.0, "pct_con_agua": 10.0},
                    "Alto": {"ha_clase": 1000.0, "ha_con_agua": 300.0, "pct_con_agua": 30.0},
                    "Crítico": {"ha_clase": 500.0, "ha_con_agua": 400.0, "pct_con_agua": 80.0},
                },
            }
        ],
        "version_flood_risk": "v-test",
    }


def test_pdf_seccion_validacion_y_leyenda_55():
    """Section 2 renders the validation table + the leyenda-55 tag (S9/S4)."""
    from app.shared.pdf.builders_informe_area import build_informe_area_pdf
    from app.shared.pdf.base import BrandingInfo

    branding = BrandingInfo(
        nombre_organizacion="Consorcio 10 de Mayo",
        logo_path=None,
        color_primario="#1a5c2e",
    )
    pdf = build_informe_area_pdf(
        _datos_informe(_validacion_dataset()), branding, mapas={}
    ).getvalue()

    reader = pypdf.PdfReader(io.BytesIO(pdf))
    texto = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert "Validación contra agua observada" in texto
    assert "mar_2015" in texto
    assert "187,4" in texto  # es-AR rainfall figure
    assert "leyenda-55" in texto
    assert "legacy70" not in texto
    assert "MNDWI" in texto  # the method note travels with the table


def test_pdf_sin_validacion_omite_la_tabla():
    """No validation rows → no table, and the informe still builds."""
    from app.shared.pdf.builders_informe_area import build_informe_area_pdf
    from app.shared.pdf.base import BrandingInfo

    branding = BrandingInfo(
        nombre_organizacion="Consorcio 10 de Mayo",
        logo_path=None,
        color_primario="#1a5c2e",
    )
    pdf = build_informe_area_pdf(_datos_informe(None), branding, mapas={}).getvalue()

    reader = pypdf.PdfReader(io.BytesIO(pdf))
    texto = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Validación contra agua observada" not in texto


def test_dataset_validacion_desde_bd(db, aplicar_migraciones):
    """The service shapes table rows → per-event clases, NULL-safe rainfall."""
    from app.domains.geo.informe_area import service

    db.execute(
        text(
            "INSERT INTO riesgo_validacion_evento "
            "(id, evento_key, fecha, clase, ha_clase, ha_con_agua, pct_con_agua, "
            " lluvia_30d_mm, sensor, escena_id, version_flood_risk) "
            "VALUES (:id, 'mar_2015', CAST('2015-03-15' AS date), 'Crítico', 500.0, "
            "        400.0, 80.0, NULL, 'sentinel1', 'S1B_x', 'v-test')"
        ),
        {"id": uuid.uuid4()},
    )
    db.flush()

    dataset = service.riesgo_validacion_dataset(db)
    assert dataset is not None
    evento = dataset["eventos"][0]
    assert evento["sensor"] == "sentinel1"
    assert evento["lluvia_30d_mm"] is None  # NULL stays NULL — never a 0 mm
    assert evento["clases"]["Crítico"]["pct_con_agua"] == 80.0

    # Empty table → None (the section omits, the informe never fails).
    db.execute(text("DELETE FROM riesgo_validacion_evento"))
    db.flush()
    assert service.riesgo_validacion_dataset(db) is None


# ── ONE opt-in live GEE check (no DB writes; skipped without the env) ────────


@pytest.mark.skipif(
    not __import__("os").environ.get("CALIBRACION_LIVE_GEE"),
    reason="opt-in: set CALIBRACION_LIVE_GEE=1 to touch real GEE",
)
def test_live_gee_agua_y_chirps(tmp_path):  # pragma: no cover — network
    """Real GEE, read-only, bounded: one anchor's water mask + the 30-day
    CHIRPS sum. Reports REAL numbers for the PR (monotonicity still needs
    the real flood raster, measured on the box)."""
    resultado = {"agua": None, "chirps": None}

    grilla = leer_grilla_riesgo(_raster_riesgo(tmp_path / "riesgo.tif", [v for v, _c in BLOQUES]))
    from app.domains.geo.calibracion_riesgo import mascara_agua_gee

    agua = mascara_agua_gee("landsat8", "LANDSAT/LC08/C02/T1_TOA/LC08_231086_20150319", grilla)
    resultado["agua"] = bool(agua)
    if agua:
        filas = clasificar_agua_por_clase(str(tmp_path / "riesgo.tif"), agua)
        print(f"\nLIVE agua por clase: {[(f.clase, f.pct_con_agua) for f in filas]}")

    lluvia = lluvia_30d_gee(date(2015, 3, 15))
    resultado["chirps"] = lluvia
    print(f"\nLIVE CHIRPS 30d (2015-02-13..2015-03-15): {lluvia} mm")
    assert resultado["agua"] is not None, "la escena live no resolvió — revisar el id"
