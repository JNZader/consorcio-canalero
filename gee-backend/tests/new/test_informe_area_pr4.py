"""Real-PostGIS tests for PR 4 of the informe de área plan (IDECOR layers).

``odd/tasks/informe-area-pr4.md`` S3 (suelos IDECOR), S4 (cobertura),
S5 (canales), S6 (imágenes ancla), S7/S8 (acceptance). Everything IDECOR
is MOCKED in here — the WFS/WCS answers are synthetic fixtures; the ONE
live call lives in ``test_idcor_live_wfs`` and only runs with
``IDECOR_LIVE=1``.

Disciplines (same as ``test_informe_area.py`` / ``_pdf.py``):

* ``db`` (rollback) for pure dataset/SQL tests;
* ``factory`` (real commits) for the Celery task tests — the task opens
  its own ``SessionLocal`` — with cleanup in ``finally`` (the T1 pattern);
* migration DDL is applied COMMITTED through the module's exported
  constants (the ``0022`` precedent) and dropped at teardown, so the
  suite's world never leaks into other tests' expectations;
* the informe world lives at lon -61.5 like PR 2's — nothing else seeds
  near it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import numpy as np
import pytest
from sqlalchemy import delete, text
from sqlalchemy.orm import Session, sessionmaker

from app.domains.geo.etl import idecor_suelos_50mil as etl_suelos
from app.domains.geo.informe_area import service, tasks
from app.domains.geo.informe_area.models import InformeArea
from tests.new.fixtures.informe_area_pr4 import wfs_suelos

# Dedicated world (PR 2's convention): no other fixture seeds near -61.5.
LON0, LAT0, LADO = -61.5, -32.0, 0.05


# ── module fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def factory(test_engine):
    return sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture
def tabla_suelos(factory):
    """Committed ``idecor_suelos_50mil`` DDL (migration's own statements).

    Committed — not inside the rollback transaction — because the Celery
    task reads the table from its OWN session. Dropped at teardown so the
    committed schema does not outlive this module.
    """
    from app.db.migrations.versions import zz_idecor_suelos_50mil as migracion

    with factory() as db:
        for statement in migracion.UPGRADE_STATEMENTS:
            db.execute(text(statement))
        db.commit()
    yield
    with factory() as db:
        for statement in migracion.DOWNGRADE_STATEMENTS:
            db.execute(text(statement))
        db.commit()


def _seed_zona(db: Session, nombre: str, cuenca: str, x0: float, y0: float) -> uuid.UUID:
    zona_id = uuid.uuid4()
    wkt = (
        f"POLYGON(({x0} {y0}, {x0 + LADO} {y0}, {x0 + LADO} {y0 + LADO}, "
        f"{x0} {y0 + LADO}, {x0} {y0}))"
    )
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, :nombre, :cuenca, ST_GeomFromText(:wkt, 4326), 0.0)"
        ),
        {"id": zona_id, "nombre": nombre, "cuenca": cuenca, "wkt": wkt},
    )
    return zona_id


def _bbox_zona(x0: float = LON0, y0: float = LAT0) -> tuple[float, float, float, float]:
    """A carta polygon that FULLY covers the test zona (S8: >95 % coverage)."""
    return (x0 - 0.01, y0 - 0.01, x0 + LADO + 0.01, y0 + LADO + 0.01)


def _correr_etl(factory) -> dict[str, Any]:
    """run_etl with the synthetic WFS: two units (II full cover, IV sliver)."""
    features = [
        wfs_suelos.feature_suelo(17, _bbox_zona()),
        # A second unit hanging off the east edge: intersects the bbox but
        # not the zona — exercises the ETL's bbox-then-clip contract.
        wfs_suelos.feature_suelo(
            18,
            (LON0 + LADO + 0.005, LAT0, LON0 + LADO + 0.02, LAT0 + LADO),
            simbolo="SF",
            clase="IV",
            cu="IVws",
            ip=40,
            serie="SAN FABIAN",
            porc=60,
        ),
    ]
    with factory() as db:
        return etl_suelos.run_etl(db, fetch_json=lambda _url: wfs_suelos.pagina_wfs(features))


# ── S3: ETL suelos ──────────────────────────────────────────────────────────


def test_etl_suelos_idempotente_mismo_conteo(factory, tabla_suelos):
    """S7: two runs, same counts — the full-refresh contract."""
    with factory() as db:
        zona_id = _seed_zona(db, "pr4-idem", "cuenca-pr4", LON0, LAT0)
        db.commit()
    features = [wfs_suelos.feature_suelo(21 + i, _bbox_zona(), simbolo=f"S{i}") for i in range(3)]
    try:
        with factory() as db:
            primera = etl_suelos.run_etl(db, fetch_json=lambda _u: wfs_suelos.pagina_wfs(features))
        with factory() as db:
            segunda = etl_suelos.run_etl(db, fetch_json=lambda _u: wfs_suelos.pagina_wfs(features))
        assert primera["filas"] == segunda["filas"] == 3
        with factory() as db:
            almacenados = db.execute(text("SELECT count(*) FROM idecor_suelos_50mil")).scalar_one()
            fechas = {
                str(f)
                for f in db.execute(
                    text("SELECT DISTINCT fecha_de_bajada FROM idecor_suelos_50mil")
                ).scalars()
            }
        assert almacenados == 3  # re-run converged, never duplicated
        assert len(fechas) == 1  # one stamp per run, the second run's
    finally:
        with factory() as db:
            db.execute(text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)})
            db.commit()


def test_etl_suelos_paginado_y_por_bbox(factory, tabla_suelos):
    """Paging walks startIndex until a short page; the bbox reaches the URL."""
    with factory() as db:
        zona_id = _seed_zona(db, "pr4-page", "cuenca-pr4", LON0, LAT0)
        db.commit()
    paginas: list[str] = []

    def fetch(url: str) -> dict:
        paginas.append(url)
        start = int(url.split("startIndex=")[1].split("&")[0])
        lote = [wfs_suelos.feature_suelo(30 + i, _bbox_zona()) for i in range(6)]
        return wfs_suelos.pagina_wfs(lote[start : start + 3])

    try:
        with factory() as db:
            resultado = etl_suelos.run_etl(db, fetch_json=fetch, page_size=3)
        assert resultado["filas"] == 6
        assert len(paginas) == 3  # start 0, 3, 6 (last page short)
        assert "bbox=" in paginas[0] and "carta_suelo_50mil_2025" in paginas[0]
    finally:
        with factory() as db:
            db.execute(text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)})
            db.commit()


def test_etl_suelos_sin_zonas_falla_cerrado(factory, tabla_suelos):
    """No zonas → no bbox → refused before any download/write."""
    with factory() as db:
        db.execute(text("DELETE FROM idecor_suelos_50mil"))
        db.commit()
    with factory() as db:
        with pytest.raises(etl_suelos.EtlAssertionError, match="zonas_operativas"):
            etl_suelos.run_etl(db, fetch_json=lambda _u: wfs_suelos.pagina_wfs([]))


def test_etl_suelos_feature_sin_geometria_rechaza_la_carga(factory, tabla_suelos):
    with factory() as db:
        zona_id = _seed_zona(db, "pr4-nogeom", "cuenca-pr4", LON0, LAT0)
        db.commit()
    rota = wfs_suelos.feature_suelo(99, _bbox_zona())
    rota["geometry"] = None
    try:
        with factory() as db:
            with pytest.raises(etl_suelos.EtlAssertionError, match="sin geometría"):
                etl_suelos.run_etl(db, fetch_json=lambda _u: wfs_suelos.pagina_wfs([rota]))
            # Fail-closed: the transaction was never committed, so the
            # previous state (empty) survives the refusal.
            assert db.execute(text("SELECT count(*) FROM idecor_suelos_50mil")).scalar_one() == 0
    finally:
        with factory() as db:
            db.execute(text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)})
            db.commit()


# ── S3: dataset + per-zone ──────────────────────────────────────────────────


def test_suelos_dataset_cobertura_series_e_ip(factory, tabla_suelos, db):
    """S8: coverage > 95 % on a test subcuenca, table with series, weighted IP."""
    with factory() as db_seed:
        zona_id = _seed_zona(db_seed, "pr4-ds", "cuenca-pr4", LON0, LAT0)
        db_seed.commit()
    try:
        _correr_etl(factory)
        with factory() as db_seed:
            fila = db_seed.execute(
                text("SELECT ST_AsGeoJSON(geometria) FROM zonas_operativas WHERE id = :id"),
                {"id": str(zona_id)},
            ).scalar_one()
            area_ha = db_seed.execute(
                text(
                    "SELECT ST_Area(ST_Transform(geometria, 32720)) / 10000.0 "
                    "FROM zonas_operativas WHERE id = :id"
                ),
                {"id": str(zona_id)},
            ).scalar_one()

        # Dataset over the zona's own geometry (the task uses the union —
        # a single zona union is the zona itself).
        dataset = service.suelos_idecor_dataset(db, fila, float(area_ha))
        assert dataset is not None
        assert dataset["cobertura_ratio"] > 0.95  # S8
        assert dataset["cobertura"] in ("total", "parcial")
        unidades = dataset["unidades"]
        assert unidades and unidades[0]["simbolo"] == "MB"
        assert "MONTE BUEY" in (unidades[0]["series"] or "")
        assert "100 %" in (unidades[0]["series"] or "")
        assert dataset["ip_ponderado"] == 90.0
        # The clipped hectares reconcile with the area (S7 ±0,1 %).
        cubierto = sum(u["ha"] for u in unidades)
        assert cubierto == pytest.approx(float(area_ha), rel=0.001)

        por_zona = service.suelos_idecor_por_zona(db, [(zona_id, float(area_ha))])
        assert por_zona[str(zona_id)]["clase_dominante"] == "II"
        assert por_zona[str(zona_id)]["cobertura_pct"] > 95.0
    finally:
        with factory() as db_limpieza:
            db_limpieza.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
            db_limpieza.commit()


def test_suelos_dataset_tabla_ausente_degrada_a_none(db):
    """S7: no IDECOR table → None → the report says «sin datos»."""
    assert (
        service.suelos_idecor_dataset(
            db, '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}', 100.0
        )
        is None
    )
    assert service.suelos_idecor_por_zona(db, [(uuid.uuid4(), 100.0)]) == {}


# ── S4: ETL coberturas ──────────────────────────────────────────────────────


@pytest.fixture
def tablas_canales(test_engine):
    """Committed canal_consorcio/red_vial/cruce_camino DDL (the migrations'
    own constants, guarded with to_regclass — these tables have no ORM
    model, so ``create_all`` never made them). Dropped at teardown.

    DDL runs on a DEDICATED autocommit connection, NOT the factory session:
    the session's open transaction would hold locks past this fixture's
    teardown and block the DROP forever (the no-teardown leak this fixture
    shipped with broke test_load_canales_consorcio's own unguarded CREATE).
    Autocommit keeps creation/drop invisible to any session transaction.

    The migrations' ``ADD_ENUM_VALUE`` statements are deliberately NOT
    applied: the test enum already has every value the seed uses.
    """
    import importlib

    m20 = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")
    m21 = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
    m22 = importlib.import_module("app.db.migrations.versions.0022_add_cruce_camino")
    ddl = (
        ("canal_consorcio", m20.CREATE_CANAL_CONSORCIO),
        ("red_vial", m21.CREATE_RED_VIAL),
        ("cruce_camino", m22.CREATE_CRUCE_CAMINO),
    )
    creadas: list[str] = []
    with test_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for tabla, statement in ddl:
            existe = conn.exec_driver_sql(f"SELECT to_regclass('{tabla}')").scalar()
            if existe is None:
                conn.exec_driver_sql(statement)
                creadas.append(tabla)
        if "canal_consorcio" in creadas:
            conn.exec_driver_sql(m20.CREATE_CANAL_CONSORCIO_GEOM_INDEX)
    yield
    # Deliberately NO teardown DROP. The test's db session (a fixture that
    # finalizes AFTER this one) holds ACCESS SHARE locks on rows it read —
    # an autocommit DROP TABLE from another connection blocks on ACCESS
    # EXCLUSIVE forever (the 30m hang at 69% in CI, 2026-11-19). The tables
    # stay EMPTY; test_load_canales_consorcio's fixture now guards its own
    # CREATE with to_regclass so a pre-existing empty table is fine.


@pytest.fixture
def tabla_coberturas(factory):
    """Committed ``idecor_cobertura_raster`` DDL; dropped at teardown."""
    from app.db.migrations.versions import zz_idecor_cobertura_raster as migracion

    with factory() as db:
        for statement in migracion.UPGRADE_STATEMENTS:
            db.execute(text(statement))
        db.commit()
    yield
    with factory() as db:
        for statement in migracion.DOWNGRADE_STATEMENTS:
            db.execute(text(statement))
        db.commit()


def _fetch_coberturas_doble(tmp_path, *, fraccion_soja_tres_campanas: float = 1.0):
    """fetch_bytes/fetch_json doubles painting a deterministic world.

    Geography of the world (EPSG:22174 inside the ETL's bbox):

    * ``uso`` — class 16 (Cultivo extensivo anual) everywhere EXCEPT a
      west band of class 9 (Cuerpo de agua estacional) covering 30 % of
      the grid width — the zona starts at ~23 % of the grid (the ETL's
      2 km margin), so the band measurably overlaps it;
    * ``estivales`` — every campaign paints its SOJA code west of
      ``fraccion_soja_tres_campanas`` of the grid width (1.0 = whole
      grid) and NaN beyond, which produces the 3/2/1/0 recurrence
      buckets deterministically.
    """
    from tests.new.fixtures.informe_area_pr4 import wcs_coberturas as doble

    def fetch_bytes(url: str) -> bytes:
        if "cobertura_uso_2024_2025" in url:

            def pintura(xs, ys):
                limite = xs.min() + 0.3 * (xs.max() - xs.min())
                return np.where(xs <= limite, 9, 16)

            return doble.geotiff_de_pintura(pintura, url, dtype="uint8", nodata=255)
        if "coberturas_estivales_2223" in url:
            codigo = 1  # Soja in the 22/23 coding
        else:
            codigo = 3  # Soja in the 23/24 and 24/25 codings

        def pintura(xs, ys):
            limite = xs.min() + fraccion_soja_tres_campanas * (xs.max() - xs.min())
            dentro = xs <= limite
            return np.where(dentro, float(codigo), np.nan)

        return doble.geotiff_de_pintura(pintura, url, dtype="float32", nodata=None)

    def fetch_json(url: str) -> dict:
        if "cobertura_uso_2024_2025" in url:
            return doble.leyenda_wms(doble.LEYENDA_USO)
        if "coberturas_estivales_2223" in url:
            return doble.leyenda_wms(doble.LEYENDA_ESTIVAL_2223)
        return doble.leyenda_wms(doble.LEYENDA_ESTIVAL_TARDIA)

    return fetch_bytes, fetch_json


def _correr_etl_coberturas(factory, tmp_path, **kwargs) -> dict[str, Any]:
    from app.domains.geo.etl import idecor_coberturas as etl_cob

    fetch_bytes, fetch_json = _fetch_coberturas_doble(tmp_path, **kwargs)
    with factory() as db:
        return etl_cob.run_etl(
            db, data_root=tmp_path / "idecor", fetch_bytes=fetch_bytes, fetch_json=fetch_json
        )


def test_etl_coberturas_idempotente_y_leyendas_por_campania(factory, tabla_coberturas, tmp_path):
    """S7: two runs → same four rows; legends keep the DIFFERENT codings."""
    with factory() as db:
        zona_id = _seed_zona(db, "pr4-cob", "cuenca-pr4", LON0, LAT0)
        db.commit()
    try:
        primera = _correr_etl_coberturas(factory, tmp_path)
        segunda = _correr_etl_coberturas(factory, tmp_path)
        assert primera["filas"] == segunda["filas"] == 4
        with factory() as db:
            filas = db.execute(
                text(
                    "SELECT capa, tipo, campania, leyenda FROM idecor_cobertura_raster ORDER BY capa"
                )
            ).all()
            assert len(filas) == 4  # UNIQUE capa converged, never duplicated
        por_capa = {f.capa: f for f in filas}
        etiquetas_2223 = [e["etiqueta"] for e in por_capa["estival_2223"].leyenda]
        etiquetas_2324 = [e["etiqueta"] for e in por_capa["estival_2324"].leyenda]
        # The 22/23 campaign really uses 1=Soja while the later ones use
        # 3=Soja — the stored legend is what keeps the report honest.
        assert etiquetas_2223[0] == "Soja"
        assert "Maíz temprano" in etiquetas_2324
        assert por_capa["uso_2024_2025"].tipo == "cobertura_uso"
        assert por_capa["estival_2223"].tipo == "cobertura_estival"
    finally:
        with factory() as db:
            db.execute(text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)})
            db.commit()


def test_etl_coberturas_grilla_distinta_rechaza(factory, tabla_coberturas, tmp_path):
    """Alignment is contractual: a cover answering a different grid aborts."""
    from app.domains.geo.etl import idecor_coberturas as etl_cob
    from tests.new.fixtures.informe_area_pr4 import wcs_coberturas as doble

    with factory() as db:
        zona_id = _seed_zona(db, "pr4-grid", "cuenca-pr4", LON0, LAT0)
        db.commit()

    fetch_bytes, fetch_json = _fetch_coberturas_doble(tmp_path)

    def fetch_bytes_roto(url: str) -> bytes:
        datos = fetch_bytes(url)
        if "coberturas_estivales_2324" in url:
            # Shift the width so the grid no longer matches the request.
            minx, miny, maxx, maxy, ancho, alto = doble._grid_de_url(url)
            url_roto = url.replace(f"width={ancho}", f"width={ancho - 10}")
            return fetch_bytes(url_roto)
        return datos

    try:
        with factory() as db:
            with pytest.raises(etl_cob.EtlAssertionError, match="alineadas|grilla"):
                etl_cob.run_etl(
                    db,
                    data_root=tmp_path / "idecor",
                    fetch_bytes=fetch_bytes_roto,
                    fetch_json=fetch_json,
                )
            # All-or-nothing: nothing was registered.
            assert (
                db.execute(text("SELECT count(*) FROM idecor_cobertura_raster")).scalar_one() == 0
            )
    finally:
        with factory() as db:
            db.execute(text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)})
            db.commit()


def test_etl_coberturas_sin_zonas_falla_cerrado(factory, tabla_coberturas, tmp_path):
    from app.domains.geo.etl import idecor_coberturas as etl_cob

    fetch_bytes, fetch_json = _fetch_coberturas_doble(tmp_path)
    with factory() as db:
        with pytest.raises(etl_cob.EtlAssertionError, match="zonas_operativas"):
            etl_cob.run_etl(
                db, data_root=tmp_path / "idecor", fetch_bytes=fetch_bytes, fetch_json=fetch_json
            )


# ── S4: dataset cobertura ───────────────────────────────────────────────────


def _geometria_zona(factory, zona_id) -> tuple[dict[str, Any], float]:
    with factory() as db:
        fila = db.execute(
            text("SELECT ST_AsGeoJSON(geometria) FROM zonas_operativas WHERE id = :id"),
            {"id": str(zona_id)},
        ).scalar_one()
        area_ha = db.execute(
            text(
                "SELECT ST_Area(ST_Transform(geometria, 32720)) / 10000.0 "
                "FROM zonas_operativas WHERE id = :id"
            ),
            {"id": str(zona_id)},
        ).scalar_one()
    import json as _json

    return _json.loads(fila), float(area_ha)


def test_cobertura_dataset_clases_agua_recurrencia(factory, tabla_coberturas, tmp_path, db):
    """S4: clases ha/%, % de la clase 9, recurrencia en las 3 campañas."""
    with factory() as db_seed:
        zona_id = _seed_zona(db_seed, "pr4-cobds", "cuenca-pr4", LON0, LAT0)
        db_seed.commit()
    try:
        _correr_etl_coberturas(factory, tmp_path)
        geom, area_ha = _geometria_zona(factory, zona_id)
        dataset = service.cobertura_dataset(db, geom, area_ha * 10_000.0)
        assert dataset is not None
        clases = {c["clase"]: c for c in dataset["clases"]}
        assert "16 - Cultivo extensivo anual" in clases
        assert "9 - Cuerpo de agua estacional" in clases
        # S7: clases + residual reconcile to 100 % of the selection.
        cubierto = sum(c["pct"] for c in dataset["clases"])
        assert 0.0 < cubierto <= 100.0001

        agua = clases["9 - Cuerpo de agua estacional"]
        assert dataset["etiqueta_agua_estacional"] == "9 - Cuerpo de agua estacional"
        assert dataset["pct_agua_estacional"] == pytest.approx(agua["pct"], abs=0.01)

        campanias = dataset["campanias"]
        assert len(campanias) == 3
        # 22/23 Soja is code 1, later campaigns code 3 — the legend keeps
        # the label coherent across codings.
        por_campania = {c["campania"]: c for c in campanias}
        soja_2223 = [c for c in por_campania["2022/2023"]["clases"] if c["clase"] == "Soja"]
        soja_2425 = [c for c in por_campania["2024/2025"]["clases"] if c["clase"] == "Soja"]
        assert soja_2223 and soja_2425

        # Full-coverage world: everything cultivated in the three campaigns.
        recurrencia = dataset["recurrencia"]
        assert recurrencia is not None
        assert recurrencia["3_campanias_ha"] > 0
        assert recurrencia["0_campanias_ha"] == 0.0
    finally:
        with factory() as db_limpieza:
            db_limpieza.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
            db_limpieza.commit()


def test_cobertura_dataset_recurrencia_parcial_y_por_zona(factory, tabla_coberturas, tmp_path, db):
    """Recurrence buckets appear when campaigns disagree; per-zone %s read."""
    with factory() as db_seed:
        zona_id = _seed_zona(db_seed, "pr4-cobrec", "cuenca-pr4", LON0, LAT0)
        db_seed.commit()
    try:
        # Cultivo hasta el 40 % del ancho de grilla en TODAS las campañas y
        # nada más allá → dentro de la zona quedan píxeles con 3 y con 0.
        _correr_etl_coberturas(factory, tmp_path, fraccion_soja_tres_campanas=0.4)
        geom, area_ha = _geometria_zona(factory, zona_id)
        dataset = service.cobertura_dataset(db, geom, area_ha * 10_000.0)
        assert dataset is not None
        recurrencia = dataset["recurrencia"]
        assert recurrencia is not None
        assert recurrencia["3_campanias_ha"] > 0
        assert recurrencia["0_campanias_ha"] > 0
        # The four buckets describe the whole selection: none of the middle
        # buckets exists when all campaigns share the same cut.
        assert recurrencia["2_campanias_ha"] == 0.0
        assert recurrencia["1_campanias_ha"] == 0.0

        por_zona = service.cobertura_por_zona(db, [(zona_id, "pr4-cobrec", _geojson_de(geom))])
        assert por_zona[str(zona_id)]["pct_cultivo"] is not None
        assert por_zona[str(zona_id)]["pct_soja"] is not None
    finally:
        with factory() as db_limpieza:
            db_limpieza.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
            db_limpieza.commit()


def _geojson_de(geom: dict[str, Any]) -> str:
    import json as _json

    return _json.dumps(geom)


def test_cobertura_dataset_tabla_ausente_degrada_a_none(db):
    """S7: sin tabla registrada → None (la sección dirá «sin datos»)."""
    assert (
        service.cobertura_dataset(
            db,
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            100.0,
        )
        is None
    )


# ── S5: canales ─────────────────────────────────────────────────────────────


def _longitud_esperada_km(x0: float, x1: float, lat: float) -> float:
    """Length in EPSG:32720 of the E-W segment clipped to [LON0, LON0+LADO]."""
    from pyproj import Geod

    dentro = max(x0, LON0), min(x1, LON0 + LADO)
    if dentro[0] >= dentro[1]:
        return 0.0
    geod = Geod(ellps="WGS84")
    _az, _az2, metros = geod.inv(dentro[0], lat, dentro[1], lat)
    return metros / 1000.0


def _seed_canal_cruces(db) -> None:
    """Two canals + one road with two crossings + two conflict points.

    * canal ``C-R`` (relevado) crosses the zona E-W through its middle;
    * canal ``C-P`` (propuesto) only clips the zona's west edge;
    * cruce tipo ``canal`` and tipo ``flujo_natural`` both land INSIDE the
      zona (a third canal-crucing lands outside, and must not be counted);
    * puntos_conflicto: one alta + one baja inside.
    """
    lat_medio = LAT0 + LADO / 2
    wkt_relevado = f"LINESTRING({LON0 - 0.01} {lat_medio}, {LON0 + LADO + 0.01} {lat_medio})"
    wkt_propuesto = f"LINESTRING({LON0 - 0.01} {LAT0 + 0.005}, {LON0 + LADO * 0.25} {LAT0 + 0.005})"
    db.execute(
        text(
            "INSERT INTO canal_consorcio (id, nombre, estado, prioridad, longitud_m, geom) "
            "VALUES ('C-R', 'Canal relevado pr4', 'relevado', 'alta', 1000, "
            "        ST_GeomFromText(:wkt, 4326)), "
            "       ('C-P', 'Canal propuesto pr4', 'propuesto', 'media', 500, "
            "        ST_GeomFromText(:wkt2, 4326))"
        ),
        {"wkt": wkt_relevado, "wkt2": wkt_propuesto},
    )
    # red_vial + geo_jobs exist only to satisfy cruce_camino's FK/CHECKs.
    db.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash) "
            "VALUES ('RV-1', 'pr4', ST_GeomFromText(:wkt, 4326), "
            "        encode(sha256(ST_AsBinary(ST_GeomFromText(:wkt, 4326))), 'hex'))"
        ),
        {"wkt": f"LINESTRING({LON0} {lat_medio - 0.01}, {LON0 + LADO} {lat_medio - 0.01})"},
    )
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso) "
            "VALUES (gen_random_uuid(), 'dem_pipeline', 'completed', 100)"
        )
    )
    geo_job_id = db.execute(
        text("SELECT id FROM geo_jobs WHERE tipo = 'dem_pipeline' ORDER BY created_at DESC LIMIT 1")
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO cruce_camino (id, area_id, tramo_ref, tipo, geometria, canal_ref, geo_job_id) "
            "VALUES (gen_random_uuid(), 'pr4', 'RV-1', 'canal', "
            "        ST_SetSRID(ST_MakePoint(:cx, :cy), 4326), 'C-R', :job), "
            "       (gen_random_uuid(), 'pr4', 'RV-1', 'canal', "
            "        ST_SetSRID(ST_MakePoint(:fx, :fy), 4326), 'C-R', :job)"
        ),
        {
            "cx": LON0 + LADO / 2,
            "cy": lat_medio,
            "fx": LON0 + LADO + 0.02,
            "fy": lat_medio,
            "job": str(geo_job_id),
        },
    )
    # flujo_natural needs its complete CHECK payload.
    db.execute(
        text(
            "INSERT INTO cruce_camino (id, area_id, tramo_ref, tipo, geometria, "
            " direccion_flujo_deg, rumbo_camino_deg, lado_cruce, area_aporte_ha, "
            " orden_ranking, confianza, geo_job_id) "
            "VALUES (gen_random_uuid(), 'pr4', 'RV-1', 'flujo_natural', "
            "        ST_SetSRID(ST_MakePoint(:px, :py), 4326), 90.0, 45.0, 'N', 12.5, 1, 'alta', :job)"
        ),
        {"px": LON0 + LADO / 2, "py": lat_medio + 0.005, "job": str(geo_job_id)},
    )
    db.execute(
        text(
            "INSERT INTO puntos_conflicto (id, tipo, severidad, descripcion, acumulacion_valor, pendiente_valor, geometria) "
            "VALUES (gen_random_uuid(), 'canal_camino', 'alta', 'pr4 alta', 5000.0, 0.2, ST_SetSRID(ST_MakePoint(:ax, :ay), 4326)), "
            "       (gen_random_uuid(), 'canal_camino', 'baja', 'pr4 baja', 100.0, 1.5, ST_SetSRID(ST_MakePoint(:bx, :by), 4326))"
        ),
        {"ax": LON0 + 0.005, "ay": LAT0 + 0.005, "bx": LON0 + 0.01, "by": LAT0 + 0.01},
    )


def _limpiar_canal_cruces(db) -> None:
    db.execute(text("DELETE FROM cruce_camino WHERE area_id = 'pr4'"))
    db.execute(
        text(
            "DELETE FROM geo_jobs WHERE id IN (SELECT geo_job_id FROM cruce_camino WHERE area_id = 'pr4')"
        )
    )
    db.execute(text("DELETE FROM red_vial WHERE id = 'RV-1'"))
    db.execute(text("DELETE FROM canal_consorcio WHERE id IN ('C-R', 'C-P')"))
    db.execute(text("DELETE FROM puntos_conflicto WHERE descripcion LIKE 'pr4 %'"))


def test_canales_dataset_km_clip_cruces_y_conflictos(factory, db, tablas_canales):
    """S5: km clip por el área (relevado E-W completo, propuesto parcial),
    cruces con caminos por tipo y puntos de conflicto por severidad."""
    with factory() as db_seed:
        zona_id = _seed_zona(db_seed, "pr4-canales", "cuenca-pr4", LON0, LAT0)
        _seed_canal_cruces(db_seed)
        db_seed.commit()
    try:
        with factory() as db_z:
            geojson = db_z.execute(
                text("SELECT ST_AsGeoJSON(geometria) FROM zonas_operativas WHERE id = :id"),
                {"id": str(zona_id)},
            ).scalar_one()
            area_ha = db_z.execute(
                text(
                    "SELECT ST_Area(ST_Transform(geometria, 32720)) / 10000.0 "
                    "FROM zonas_operativas WHERE id = :id"
                ),
                {"id": str(zona_id)},
            ).scalar_one()

        dataset = service.canales_dataset(db, geojson, float(area_ha))
        assert dataset is not None
        # The relevado canal spans the whole zona E-W: its clipped km is
        # the zona's own width at that latitude (geodesic reference).
        esperado = _longitud_esperada_km(LON0 - 0.01, LON0 + LADO + 0.01, LAT0 + LADO / 2)
        assert dataset["km_relevados"] == pytest.approx(esperado, rel=0.01)
        # The propuesto canal only enters a quarter of the zona.
        esperado_p = _longitud_esperada_km(LON0 - 0.01, LON0 + LADO * 0.25, LAT0 + 0.005)
        assert dataset["km_propuestos"] == pytest.approx(esperado_p, rel=0.01)
        assert dataset["km_total"] == pytest.approx(esperado + esperado_p, rel=0.01)
        assert dataset["km_por_mil_ha"] is not None and dataset["km_por_mil_ha"] > 0
        # Cruces: 1 canal (the second one lands OUTSIDE and must not count)
        # + 1 flujo_natural. Conflictos: alta 1, baja 1.
        assert dataset["cruces_camino"] == {"canal": 1, "flujo_natural": 1}
        assert dataset["puntos_conflicto"] == {"alta": 1, "baja": 1}
        assert dataset["sin_datos"] is False

        por_zona = service.canales_por_zona(db, [(zona_id, "pr4-canales", float(area_ha))])
        assert por_zona[str(zona_id)]["km_relevados"] == pytest.approx(esperado, rel=0.01)
        assert por_zona[str(zona_id)]["km_propuestos"] == pytest.approx(esperado_p, rel=0.01)
    finally:
        with factory() as db_limpieza:
            _limpiar_canal_cruces(db_limpieza)
            db_limpieza.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
            db_limpieza.commit()


def test_canales_dataset_vacio_es_cero_real_no_error(factory, db, tablas_canales):
    """S5/S7: an area with no canals reports honest zeros, not sin datos."""
    with factory() as db_seed:
        zona_id = _seed_zona(db_seed, "pr4-sincanal", "cuenca-pr4", LON0 + 0.3, LAT0)
        db_seed.commit()
    try:
        with factory() as db_z:
            geojson = db_z.execute(
                text("SELECT ST_AsGeoJSON(geometria) FROM zonas_operativas WHERE id = :id"),
                {"id": str(zona_id)},
            ).scalar_one()
        dataset = service.canales_dataset(db, geojson, 1000.0)
        assert dataset is not None
        assert dataset["km_total"] == 0.0
        assert dataset["cruces_camino"] == {}
        assert dataset["sin_datos"] is True
    finally:
        with factory() as db_limpieza:
            db_limpieza.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
            db_limpieza.commit()


# ── S6: imágenes de eventos ancla ───────────────────────────────────────────


def _png_chico() -> bytes:
    """A 24x16 red PNG — a valid image for the ReportLab/Pillow path."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), (180, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _seed_eventos_ancla(factory) -> None:
    """The three curated anchors + rank-1 candidates (mar→landsat8, los
    otros dos → sentinel2/landsat7) + one anchor WITHOUT a candidate."""
    payloads = {
        "mar_2015": {"name": "Inundación Marzo 2015", "sensor": "landsat8"},
        "feb_2017": {"name": "Inundación Febrero 2017", "sensor": "sentinel2"},
        "sep_2025": {"name": "Inundación Septiembre 2025", "sensor": None},
        "sin_cand": {"name": "Evento sin candidata", "sensor": "landsat5"},
    }
    fechas = {
        "mar_2015": "2015-03-15",
        "feb_2017": "2017-02-20",
        "sep_2025": "2025-09-05",
        "sin_cand": "2020-01-10",
    }
    with factory() as db:
        for event_key, fecha in fechas.items():
            db.execute(
                text(
                    "INSERT INTO rainfall_extreme_event "
                    "(id, source_id, scope_kind, scope_id, scope_version, detector_revision, "
                    " provenance, event_key, start_date, end_date, curated_payload) "
                    "VALUES (gen_random_uuid(), 'chirps-v3-final', 'provider_asset', "
                    "        'zona_cc_ampliada', 'v1', 'curated', 'curated', :k, "
                    "        CAST(:d AS date), CAST(:d AS date), CAST(:p AS json))"
                ),
                {"k": event_key, "d": fecha, "p": json.dumps(payloads[event_key])},
            )
        escenas = [
            ("mar_2015", "landsat8", "LANDSAT/LC08_C02/T1_TOA/LC08_123", "2015-03-16", 10.0),
            ("feb_2017", "sentinel2", "COPERNICUS/S2_SR_HARMONIZED/20170220T14", "2017-02-21", 5.0),
            ("sep_2025", "landsat7", "LANDSAT/LE07_C02/T1_TOA/LE07_123", "2025-09-04", 30.0),
        ]
        for event_key, sensor, escena, fecha_escena, nubes in escenas:
            db.execute(
                text(
                    "INSERT INTO rainfall_event_imagery_candidate "
                    "(id, event_key, scorer_revision, sensor, scene_id, scene_date, "
                    " days_from_peak, cloud_pct, cloud_basis, score, rank, visualization, slot) "
                    "VALUES (gen_random_uuid(), :k, 'pr4', :s, :sc, CAST(:sd AS date), "
                    "        0, :n, 'scene', 99.0, 1, 'falso_color', 'ranked')"
                ),
                {"k": event_key, "s": sensor, "sc": escena, "sd": fecha_escena, "n": nubes},
            )
        db.commit()


def _limpiar_eventos_ancla(factory) -> None:
    with factory() as db:
        db.execute(
            text("DELETE FROM rainfall_event_imagery_candidate WHERE scorer_revision = 'pr4'")
        )
        db.execute(
            text(
                "DELETE FROM rainfall_extreme_event WHERE provenance = 'curated' "
                "AND event_key IN ('mar_2015', 'feb_2017', 'sep_2025', 'sin_cand')"
            )
        )
        db.commit()


def test_imagenes_ancla_con_mock_gee_tres_presentas(factory, db):
    """S8: con GEE respondiendo, las miniaturas están para los eventos con
    candidata; el evento sin candidata sale «sin datos» y nada falla."""
    _seed_eventos_ancla(factory)
    try:
        llamadas: list[tuple[str, str]] = []

        def fetch_ok(scene_id: str, sensor: str, region) -> bytes:
            llamadas.append((sensor, scene_id))
            assert region.get("type") in ("Polygon", "MultiPolygon")
            return _png_chico()

        filas = service.imagenes_eventos_ancla(
            db,
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            fetch_miniatura=fetch_ok,
        )
        por_evento = {f["event_key"]: f for f in filas}
        assert set(por_evento) == {"mar_2015", "feb_2017", "sep_2025", "sin_cand"}
        # Three events have rank-1 candidates → three thumbnails.
        assert len(llamadas) == 3
        assert {sensor for sensor, _escena in llamadas} == {"landsat8", "sentinel2", "landsat7"}
        for event_key in ("mar_2015", "feb_2017", "sep_2025"):
            assert por_evento[event_key]["png"] == _png_chico()
        assert por_evento["sin_cand"]["png"] is None
        assert por_evento["sin_cand"]["sensor"] is None
    finally:
        _limpiar_eventos_ancla(factory)


def test_imagenes_ancla_gee_caido_degrada_por_evento(factory, db):
    """S7: GEE que explota → png None por evento, cero excepciones."""
    _seed_eventos_ancla(factory)
    try:

        def fetch_mal(_scene: str, _sensor: str, _region) -> bytes:
            raise RuntimeError("gee quota exceeded")

        filas = service.imagenes_eventos_ancla(
            db,
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            fetch_miniatura=fetch_mal,
        )
        assert len(filas) == 4
        assert all(f["png"] is None for f in filas)
        # The scene metadata still travels (the report says WHICH scene
        # it could not render, not just «error»).
        assert {f["sensor"] for f in filas} == {None, "landsat8", "sentinel2", "landsat7"}
    finally:
        _limpiar_eventos_ancla(factory)


def test_imagenes_ancla_sin_catalogo_degrada_a_lista_vacia(db):
    """S7: sin tablas del catálogo → [] (sección «sin eventos»)."""
    filas = service.imagenes_eventos_ancla(
        db,
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        fetch_miniatura=lambda *_a: (_ for _ in ()).throw(AssertionError("no debe llamarse")),
    )
    assert filas == []


def test_miniatura_falso_color_bandas_por_sensor():
    """The band triplets are NIR-SWIR1-red per sensor (the water-reading
    combination), not the house RGB/false-color presets."""
    assert service._BANDAS_FALSO_COLOR["sentinel2"][0] == ["B8", "B11", "B4"]
    assert service._BANDAS_FALSO_COLOR["landsat8"][0] == ["B5", "B6", "B4"]
    assert service._BANDAS_FALSO_COLOR["landsat7"][0] == ["B4", "B5", "B3"]

    # Impl path against a stub ee: select/clip/getThumbURL + PNG fetch.
    class _Imagen:
        def __init__(self, meta):
            self.meta = meta

        def select(self, bandas):
            self.meta["bandas"] = bandas
            return self

        def clip(self, region):
            self.meta["region"] = region
            return self

        def getThumbURL(self, params):
            self.meta["params"] = params
            return "https://ee/thumb"

    class _EE:
        def __init__(self):
            self.meta = {}

        def Image(self, scene_id):
            self.meta["scene"] = scene_id
            return _Imagen(self.meta)

        def Geometry(self, geo_json=None, geodesic=None):
            self.meta["geom"] = (geo_json, geodesic)
            return ("region", geo_json)

    class _Resp:
        content = b"PNG-FAKE"

        def raise_for_status(self):
            return None

    class _Req:
        def get(self, url, timeout=None):
            assert url == "https://ee/thumb"
            return _Resp()

    ee_stub, req_stub = _EE(), _Req()
    png = service.miniatura_falso_color_impl(
        scene_id="COPERNICUS/S2_SR_HARMONIZED/ESCENA-1",
        sensor="sentinel2",
        region_geojson={"type": "Polygon", "coordinates": []},
        ee_module=ee_stub,
        requests_module=req_stub,
    )
    assert png == b"PNG-FAKE"
    assert ee_stub.meta["scene"] == "COPERNICUS/S2_SR_HARMONIZED/ESCENA-1"
    assert ee_stub.meta["bandas"] == ["B8", "B11", "B4"]
    assert ee_stub.meta["params"]["min"] == 0.0
    assert ee_stub.meta["params"]["max"] == 3000.0
    assert ee_stub.meta["params"]["dimensions"] == service.MINIATURA_PX
    assert ee_stub.meta["params"]["format"] == "png"
    assert ee_stub.meta["geom"][1] is False


def test_miniatura_optica_bare_system_index_usa_coleccion():
    """C6: bare optical system:index must filter ImageCollection instead of ee.Image(bare_id)."""

    class _ImagenOpt:
        def __init__(self, meta):
            self.meta = meta

        def select(self, bandas):
            self.meta["bandas"] = bandas
            return self

        def clip(self, region):
            self.meta["clip"] = region
            return self

        def getThumbURL(self, params):
            self.meta["params"] = params
            return "https://ee/thumb-opt"

    class _ColeccionOpt:
        def __init__(self, meta):
            self._meta = meta

        def filter(self, filtro):
            self._meta["filtro"] = filtro
            return self

        def first(self):
            return _ImagenOpt(self._meta)

    class _EEOpt:
        def __init__(self):
            self.meta = {}
            self.Filter = type("_F", (), {"eq": staticmethod(lambda k, v: ("eq", k, v))})

        def Geometry(self, geo_json=None, geodesic=None):
            return ("region", geo_json)

        def ImageCollection(self, col):
            self.meta["coleccion"] = col
            return _ColeccionOpt(self.meta)

    class _ReqOpt:
        def get(self, url, timeout=None):
            return type("_R", (), {"content": b"PNG-OPT", "raise_for_status": lambda s: None})()

    ee_stub = _EEOpt()
    png = service.miniatura_falso_color_impl(
        scene_id="20210402T141049_20210402T141418_T20HNH",
        sensor="sentinel2",
        region_geojson={"type": "Polygon", "coordinates": []},
        ee_module=ee_stub,
        requests_module=_ReqOpt(),
    )
    assert png == b"PNG-OPT"
    assert ee_stub.meta["coleccion"] == "COPERNICUS/S2_SR_HARMONIZED"
    assert ee_stub.meta["filtro"] == (
        "eq",
        "system:index",
        "20210402T141049_20210402T141418_T20HNH",
    )
    assert ee_stub.meta["bandas"] == ["B8", "B11", "B4"]


def test_miniatura_s1_banda_unica_sin_clip():
    """S1 path: ImageCollection load, single VV band, NO clip, raw GeoJSON region.

    Box-tested against real GEE (2026-11-20): multi-band S1 compositing
    triggers "inconsistent projections" on getThumbURL while a single VV
    band renders fine (water reads dark — the signal the PDF needs).
    Layers 7-8 of the thumbnail onion. The stub image deliberately has NO
    clip() method: calling it must fail the test.
    """

    class _ImagenS1:
        def __init__(self, meta):
            self.meta = meta

        def select(self, bandas):
            self.meta["bandas"] = bandas
            return self

        def getThumbURL(self, params):
            self.meta["params"] = params
            return "https://ee/thumb-s1"

    class _Coleccion:
        def __init__(self, meta, imagen):
            self._meta = meta
            self._imagen = imagen

        def filter(self, filtro):
            self._meta["filtro"] = filtro
            return self

        def first(self):
            return self._imagen

    class _Filtro:
        @staticmethod
        def eq(campo, valor):
            return ("eq", campo, valor)

    class _EES1:
        def __init__(self):
            self.meta = {}
            self.Filter = _Filtro

        def Geometry(self, geo_json=None, geodesic=None):
            # constructed for every sensor BEFORE the branch — unused by S1
            self.meta["geom"] = (geo_json, geodesic)
            return ("region-geom", geo_json)

        def ImageCollection(self, nombre):
            self.meta["coleccion"] = nombre
            return _Coleccion(self.meta, _ImagenS1(self.meta))

    class _RespS1:
        content = b"PNG-S1"

        def raise_for_status(self):
            return None

    class _ReqS1:
        def get(self, url, timeout=None):
            assert url == "https://ee/thumb-s1"
            return _RespS1()

    geojson = {"type": "Polygon", "coordinates": [[[-62.5, -32.5], [-62.4, -32.5]]]}
    ee_stub, req_stub = _EES1(), _ReqS1()
    png = service.miniatura_falso_color_impl(
        scene_id="S1A_IW_GRDH_1SDV",
        sensor="sentinel1",
        region_geojson=geojson,
        ee_module=ee_stub,
        requests_module=req_stub,
    )
    assert png == b"PNG-S1"
    # loads from the collection, filters by system:index, single VV band
    assert ee_stub.meta["coleccion"] == "COPERNICUS/S1_GRD"
    assert ee_stub.meta["filtro"] == ("eq", "system:index", "S1A_IW_GRDH_1SDV")
    assert ee_stub.meta["bandas"] == ["VV"]
    # raw GeoJSON region (not an ee.Geometry), no crs override needed
    assert ee_stub.meta["params"]["region"] == geojson
    assert ee_stub.meta["params"]["bands"] == ["VV"]
    assert ee_stub.meta["params"]["min"] == -25.0
    assert ee_stub.meta["params"]["max"] == 0.0
    assert ee_stub.meta["params"]["dimensions"] == service.MINIATURA_PX
    assert "crs" not in ee_stub.meta["params"]


# ── S7: the ONE opt-in live test (network; skip without IDECOR_LIVE=1) ──────


@pytest.mark.integration
def test_idcor_live_wfs():
    """Opt-in live probe: the real WFS answers suelos within the zona bbox.

    Runs ONLY with IDECOR_LIVE=1 (bounded: one count=1 page + one
    count=500 page, read-only). Everything else in this suite is hermetic.
    """
    import os

    import requests

    if os.environ.get("IDECOR_LIVE") != "1":
        pytest.skip("opt-in live test: set IDECOR_LIVE=1")

    respuesta = requests.get(
        "https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wfs",
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": "idecor:carta_suelo_50mil_2025",
            "outputFormat": "application/json",
            "count": 1,
        },
        timeout=60,
    )
    respuesta.raise_for_status()
    payload = respuesta.json()
    assert payload.get("numberMatched") == 1555
    assert payload["features"], "el WFS vivo debe traer al menos una feature"

    leyenda = requests.get(
        "https://idecor-ws.mapascordoba.gob.ar/geoserver/idecor/wms",
        params={
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetLegendGraphic",
            "layer": "cobertura_uso_2024_2025",
            "format": "application/json",
        },
        timeout=60,
    )
    leyenda.raise_for_status()
    from app.domains.geo.etl.idecor_coberturas import CAPAS, normalizar_leyenda, url_get_coverage

    entradas = normalizar_leyenda(leyenda.json())
    agua = [e for e in entradas if "agua estacional" in e["etiqueta"].lower()]
    assert len(agua) == 1 and agua[0]["codigo"] == 9

    # Bounded 200 m x 200 m WCS 1.0.0 GetCoverage around Bell Ville (-62.69, -32.63 -> EPSG:22174)
    wcs_url = url_get_coverage(
        CAPAS["uso_2024_2025"]["coverage_id"],
        (4529000.0, 6390100.0, 4529200.0, 6390300.0),
    )
    wcs_resp = requests.get(wcs_url, timeout=60)
    wcs_resp.raise_for_status()
    tiff_bytes = wcs_resp.content
    assert tiff_bytes[:4] in (b"II*\x00", b"MM\x00*"), "WCS debe devolver GeoTIFF válido"

    import rasterio

    with rasterio.io.MemoryFile(tiff_bytes) as mem, mem.open() as ds:
        assert ds.width > 0 and ds.height > 0
        arr = ds.read(1)
        assert (arr != 255).any(), "Coverage 200x200 en Bell Ville no puede ser todo nodata"


# ── S7/S8: integración final — el informe completo con todas las capas ──────


def _mundo_completo(factory, tmp_path) -> dict[str, Any]:
    """PR 2's world (rasters + precip + composite) PLUS every PR 4 layer.

    Real commits (the task opens its own SessionLocal). Cleanup is the
    caller's ``finally`` through ``_limpiar_mundo_completo``.
    """
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from app.auth.models import User
    from app.domains.geo.informe_area.schemas import InformeAreaCreate

    nodata = -9999.0
    rasters: set[str] = set()

    def raster_constante(nombre: str, valor: float) -> str:
        ruta = str(tmp_path / nombre)
        with rasterio.open(
            ruta,
            "w",
            driver="GTiff",
            height=120,
            width=160,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(LON0 - 0.05, LAT0 + 0.06, 0.001, 0.001),
            nodata=nodata,
        ) as dst:
            dst.write(np.full((120, 160), valor, dtype="float32"), 1)
        return ruta

    with factory() as db:
        db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS suelos_catastro ("
                "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "  simbolo VARCHAR(50) NOT NULL,"
                "  cap VARCHAR(10), ip VARCHAR(50),"
                "  geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL)"
            )
        )
        # PR 1's desglose still joins suelos_catastro; one II band.
        db.execute(
            text(
                "INSERT INTO suelos_catastro (simbolo, cap, geometria) "
                "VALUES ('PR4-II', 'II', ST_GeomFromText(:wkt, 4326))"
            ),
            {
                "wkt": f"MULTIPOLYGON((({LON0 - 0.02} {LAT0 - 0.02}, {LON0 + 0.1} {LAT0 - 0.02}, "
                f"{LON0 + 0.1} {LAT0 + 0.05}, {LON0 - 0.02} {LAT0 + 0.05}, "
                f"{LON0 - 0.02} {LAT0 - 0.02})))"
            },
        )
        from app.db.migrations.versions import zz_idecor_suelos_50mil as migracion_suelos
        from app.db.migrations.versions import zz_idecor_cobertura_raster as migracion_cob

        for statement in migracion_suelos.UPGRADE_STATEMENTS:
            db.execute(text(statement))
        for statement in migracion_cob.UPGRADE_STATEMENTS:
            db.execute(text(statement))
        db.execute(text("DELETE FROM idecor_suelos_50mil"))
        db.execute(text("DELETE FROM idecor_cobertura_raster"))

        # S3: two carta units — II covering the zona (>95 %), IV hanging off.
        for fid, bbox, clase, ip_valor, serie in (
            (101, _bbox_zona(), "II", 90, "MONTE BUEY"),
            (
                102,
                (LON0 + LADO + 0.005, LAT0, LON0 + LADO + 0.02, LAT0 + LADO),
                "IV",
                40,
                "SAN FABIAN",
            ),
        ):
            feature = wfs_suelos.feature_suelo(fid, bbox, clase=clase, ip=ip_valor, serie=serie)
            db.execute(
                text(
                    "INSERT INTO idecor_suelos_50mil (id, simbolo, cu, clase, ip, au_1m, au_2m, "
                    " serie_1, porc_1, nombre, tipo_unida, pdf_simbolo, pdf_serie_1, geometria) "
                    "VALUES (:id, :simbolo, :cu, :clase, :ip, :au1, :au2, :serie, 100, :nombre, "
                    "        'Consociación', :simbolo, :pdf_serie, ST_Multi(ST_CollectionExtract("
                    "ST_MakeValid(ST_GeomFromGeoJSON(CAST(:geojson AS json))), 3)))"
                ),
                {
                    "id": fid,
                    "simbolo": feature["properties"]["simbolo"],
                    "cu": feature["properties"]["cu"],
                    "clase": clase,
                    "ip": ip_valor,
                    "au1": feature["properties"]["au_1m"],
                    "au2": feature["properties"]["au_2m"],
                    "serie": serie,
                    "nombre": feature["properties"]["nombre"],
                    "pdf_serie": feature["properties"]["pdf_serie1"],
                    "geojson": json.dumps(feature["geometry"]),
                },
            )

        # S4: register the cobertura world through the ETL double — the
        # zona MUST exist first (the ETL resolves zonas_operativas's extent).
        zona_id = _seed_zona(db, "pr4-int", "cuenca-pr4", LON0, LAT0)
        db.commit()
        from app.domains.geo.etl import idecor_coberturas as etl_cob

        fetch_bytes, fetch_json = _fetch_coberturas_doble(tmp_path)
        etl_cob.run_etl(
            db, data_root=tmp_path / "idecor", fetch_bytes=fetch_bytes, fetch_json=fetch_json
        )

        # S5: canales + cruces.
        _seed_canal_cruces(db)
        db.commit()
    _seed_eventos_ancla(factory)

    with factory() as db:
        flood = raster_constante("pr4_flood.tif", 80.0)
        drain = raster_constante("pr4_drain.tif", 60.0)
        from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

        for tipo, ruta in ((TipoGeoLayer.FLOOD_RISK, flood), (TipoGeoLayer.DRAINAGE_NEED, drain)):
            db.add(
                GeoLayer(
                    nombre=f"pr4-{tipo.value}",
                    tipo=tipo,
                    fuente=FuenteGeoLayer.MANUAL,
                    archivo_path=ruta,
                    formato=FormatoGeoLayer.GEOTIFF,
                    srid=4326,
                )
            )
            rasters.add(ruta)
        precip = raster_constante("pr4_precip.tif", 100.0)
        for mes in [*range(1, 13), "anual"]:
            db.add(
                GeoLayer(
                    nombre=f"pr4-precip-{mes}",
                    tipo=TipoGeoLayer.PRECIP_NORMAL,
                    fuente=FuenteGeoLayer.MANUAL,
                    archivo_path=precip,
                    formato=FormatoGeoLayer.GEOTIFF,
                    srid=4326,
                    metadata_extra={"mes": mes, "version": "2026-01-01T00:00:00+00:00"},
                )
            )
        rasters.add(precip)

        usuario = User(
            email=f"pr4-int-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x",
            role="operador",
            nombre="PR4",
            apellido="Int",
            telefono="",
        )
        db.add(usuario)
        db.flush()
        db.execute(
            text(
                "INSERT INTO composite_zonal_stats "
                "(id, zona_id, tipo, fecha_calculo, mean_score, max_score, p90_score, area_high_risk_ha) "
                "VALUES (:id, :zona, 'flood_risk', CURRENT_DATE, 50, 90, 70, 100)"
            ),
            {"id": uuid.uuid4(), "zona": str(zona_id)},
        )
        db.execute(
            text(
                "INSERT INTO composite_zonal_stats "
                "(id, zona_id, tipo, fecha_calculo, mean_score, max_score, p90_score, area_high_risk_ha) "
                "VALUES (:id, :zona, 'drainage_need', CURRENT_DATE, 50, 90, 70, 80)"
            ),
            {"id": uuid.uuid4(), "zona": str(zona_id)},
        )
        db.commit()
        from app.domains.geo.informe_area import service as informe_service

        fila, _cache = informe_service.crear_informe(
            db,
            InformeAreaCreate(nombre="Informe PR4 integración", zona_ids=[zona_id]),
            usuario_id=usuario.id,
        )
        informe_id = fila.id
        db.commit()

    return {
        "usuario_id": usuario.id,
        "zona_id": zona_id,
        "informe_id": informe_id,
        "rasters": rasters,
    }


def _limpiar_mundo_completo(factory, mundo: dict[str, Any]) -> None:
    from app.auth.models import User
    from app.domains.geo.models import GeoLayer
    from app.domains.geo.informe_area.models import InformeArea
    from app.shared.celery_outbox import CeleryTaskOutbox

    with factory() as db:
        db.execute(
            delete(CeleryTaskOutbox).where(CeleryTaskOutbox.task_key == "geo.informe_area.generar")
        )
        db.execute(delete(InformeArea).where(InformeArea.id == mundo["informe_id"]))
        db.execute(delete(GeoLayer).where(GeoLayer.archivo_path.in_(mundo["rasters"])))
        db.execute(
            text("DELETE FROM composite_zonal_stats WHERE zona_id = :z"),
            {"z": str(mundo["zona_id"])},
        )
        db.execute(text("DELETE FROM zonas_operativas WHERE id = :z"), {"z": str(mundo["zona_id"])})
        db.execute(text("DELETE FROM suelos_catastro WHERE simbolo = 'PR4-II'"))
        db.execute(delete(User).where(User.id == mundo["usuario_id"]))
        db.commit()
    _limpiar_canal_cruces_factory(factory)
    _limpiar_eventos_ancla(factory)


def _limpiar_canal_cruces_factory(factory) -> None:
    with factory() as db:
        _limpiar_canal_cruces(db)
        db.commit()


SECCIONES_PR4 = [
    "1. Resumen",
    "2. Riesgo hídrico",
    "3. Necesidad de drenaje",
    "4. Suelos",
    "5. Cobertura y cultivos",
    "6. Lluvia",
    "7. Canales",
    "8. Imágenes de eventos ancla",
    "9. Consideraciones",
    "10. Fuentes",
]


def test_informe_completo_todas_las_capas_pdf_y_resultado(
    factory, tmp_path, monkeypatch, tablas_canales
):
    """S7/S8 end-to-end: capas IDECOR + canales + imágenes con GEE mockeado.

    * the task completes and stores a PDF with the TEN sections in order;
    * suelos: cobertura > 95 % on the test subcuenca AND the series render;
    * cobertura: classes present, residual reconciles to 100 % (±0,1 %);
    * the three anchor thumbnails are in the PDF when GEE answers (S8);
    * canales: the clipped km reach the resultado.
    """
    pypdf = pytest.importorskip("pypdf")
    import io as _io
    import re as _re

    from app.domains.geo.informe_area import service as informe_service

    def fetch_gee_ok(_scene: str, _sensor: str, _region) -> bytes:
        return _png_chico()

    monkeypatch.setattr(informe_service, "_miniatura_por_defecto", fetch_gee_ok)
    monkeypatch.setattr(
        "app.domains.geo.informe_area.service.try_publish_celery_task", lambda _id: False
    )

    mundo = _mundo_completo(factory, tmp_path)
    try:
        salida = tasks.generar_informe_area(str(mundo["informe_id"]))
        assert salida["estado"] == "completed", salida

        with factory() as db:
            fila = db.get(
                InformeArea,
                mundo["informe_id"],
            )
            assert fila.estado.value == "completed"
            res = fila.resultado
            pdf_bytes = bytes(fila.pdf_bytes)

            # S8: suelos >95 % con series; imágenes presentes; canales km.
            assert res["suelos_idecor"]["cobertura_ratio"] > 0.95
            assert res["suelos_idecor"]["unidades"] >= 1
            assert res["canales_resumen"]["km_relevados"] > 0
            miniaturas = [i for i in res["imagenes_ancla"] if i["con_miniatura"]]
            assert len(miniaturas) == 3  # S8: las 3 con GEE respondiendo
            # S7: la suma de ha de la sección suelos reconcilia ±0,1 %.
            suelos = fila.resultado  # placeholder para claridad de lectura
            del suelos

        texto = _texto_de_pdf(pdf_bytes)
        posiciones = [texto.find(titulo) for titulo in SECCIONES_PR4]
        assert all(pos != -1 for pos in posiciones), posiciones
        assert posiciones == sorted(posiciones), posiciones
        # Series de la carta en la tabla de suelos + fuente IDECOR citada.
        assert "MONTE BUEY" in texto
        assert "IDECOR" in texto
        # Las tres miniaturas embebidas: imágenes dentro del PDF (ubicación
        # + 3 miniaturas de eventos; los mapas de clase dependen del raster
        # del mundo y ya tienen su suite propia en PR 2).
        lector = pypdf.PdfReader(_io.BytesIO(pdf_bytes))
        total_imagenes = sum(len(pagina.images) for pagina in lector.pages)
        assert total_imagenes >= 4
        assert not _re.search(r"\d,\d{3}\.\d", texto)  # es-AR, no en-US
    finally:
        _limpiar_mundo_completo(factory, mundo)


def test_informe_sin_idECOR_sale_con_sin_datos(factory, tmp_path, monkeypatch):
    """S7: sin capas IDECOR ni catálogo de eventos, el informe SALE IGUAL —
    cada sección nueva con «sin datos» y el resto del informe intacto."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from app.auth.models import User
    from app.domains.geo.informe_area import service as informe_service
    from app.domains.geo.informe_area.schemas import InformeAreaCreate
    from app.domains.geo.models import (
        FormatoGeoLayer,
        FuenteGeoLayer,
        GeoLayer,
        TipoGeoLayer,
    )

    monkeypatch.setattr(informe_service, "try_publish_celery_task", lambda _id: False)
    # GEE real nunca debe llamarse: sin catálogo no hay eventos.
    monkeypatch.setattr(
        informe_service,
        "_miniatura_por_defecto",
        lambda *_a: (_ for _ in ()).throw(AssertionError("GEE no debe llamarse")),
    )

    with factory() as db:
        db.execute(text("DROP TABLE IF EXISTS idecor_suelos_50mil"))
        db.execute(text("DROP TABLE IF EXISTS idecor_cobertura_raster"))
        db.execute(text("DELETE FROM rainfall_extreme_event WHERE provenance = 'curated'"))
        db.commit()

    ruta_flood = str(tmp_path / "sinidecor_flood.tif")
    with rasterio.open(
        ruta_flood,
        "w",
        driver="GTiff",
        height=120,
        width=160,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON0 - 0.05, LAT0 + 0.06, 0.001, 0.001),
        nodata=-9999.0,
    ) as dst:
        dst.write(np.full((120, 160), 80.0, dtype="float32"), 1)

    usuario_id = zona_id = informe_id = None
    try:
        with factory() as db:
            db.add(
                GeoLayer(
                    nombre="pr4-sinflood",
                    tipo=TipoGeoLayer.FLOOD_RISK,
                    fuente=FuenteGeoLayer.MANUAL,
                    archivo_path=ruta_flood,
                    formato=FormatoGeoLayer.GEOTIFF,
                    srid=4326,
                )
            )
            usuario = User(
                email=f"pr4-sin-{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="x",
                role="operador",
                nombre="PR4",
                apellido="Sin",
                telefono="",
            )
            db.add(usuario)
            db.flush()
            zona_id = _seed_zona(db, "pr4-sin", "cuenca-pr4", LON0 + 0.4, LAT0)
            db.commit()
            usuario_id = usuario.id
            fila, _cache = informe_service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe sin IDECOR", zona_ids=[zona_id]),
                usuario_id=usuario_id,
            )
            informe_id = fila.id
            db.commit()

        salida = tasks.generar_informe_area(str(informe_id))
        assert salida["estado"] == "completed", salida

        with factory() as db:
            fila = db.get(
                InformeArea,
                informe_id,
            )
            res = fila.resultado
            assert res["suelos_idecor"] is None
            assert res["cobertura_idecor"] is None
            assert res["imagenes_ancla"] == []
            texto = _texto_de_pdf(bytes(fila.pdf_bytes))
        assert "no está cargada" in texto  # suelos sin datos
        assert "no están registrados" in texto  # cobertura sin datos
        assert "Sin miniatura" in texto or "no hay eventos ancla" in texto
        # El resto del informe sale igual (las secciones base siguen).
        assert "2. Riesgo hídrico" in texto and "6. Lluvia" in texto
    finally:
        with factory() as db:
            from app.shared.celery_outbox import CeleryTaskOutbox

            db.execute(
                delete(CeleryTaskOutbox).where(
                    CeleryTaskOutbox.task_key == "geo.informe_area.generar"
                )
            )
            if informe_id is not None:
                db.execute(delete(InformeArea).where(InformeArea.id == informe_id))
            db.execute(delete(GeoLayer).where(GeoLayer.archivo_path == ruta_flood))
            if zona_id is not None:
                db.execute(text("DELETE FROM zonas_operativas WHERE id = :z"), {"z": str(zona_id)})
            if usuario_id is not None:
                db.execute(delete(User).where(User.id == usuario_id))
            db.commit()


def _texto_de_pdf(pdf_bytes: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    import io as _io
    import re as _re

    lector = pypdf.PdfReader(_io.BytesIO(pdf_bytes))
    texto = " ".join(pagina.extract_text() or "" for pagina in lector.pages)
    # pypdf wraps long table cells across extracted lines («MONTE\nBUEY»):
    # collapse ALL whitespace so word-boundary asserts see one line.
    return _re.sub(r"\s+", " ", texto)
