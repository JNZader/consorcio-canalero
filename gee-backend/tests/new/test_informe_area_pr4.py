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

import uuid
from typing import Any

import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.domains.geo.etl import idecor_suelos_50mil as etl_suelos
from app.domains.geo.informe_area import service
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
def tablas_canales(factory):
    """Committed canal_consorcio/red_vial/cruce_camino DDL (the migrations'
    own constants, guarded with to_regclass — these tables have no ORM
    model, so ``create_all`` never made them). Dropped at teardown.

    The migrations' ``ADD_ENUM_VALUE`` statements are deliberately NOT
    applied: the test enum already has every value the seed uses.
    """
    import importlib

    m20 = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")
    m21 = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
    m22 = importlib.import_module("app.db.migrations.versions.0022_add_cruce_camino")
    tablas = ("canal_consorcio", "red_vial", "cruce_camino")
    # Per-table guard: other suites leave red_vial/cruce_camino behind in
    # the shared test database while canal_consorcio is absent — an
    # all-or-nothing check would skip creating what is actually missing.
    creadas: dict[str, bool] = {}
    with factory() as db:
        existentes = {
            t: db.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar_one_or_none()
            for t in tablas
        }
        for tabla, statement in (
            ("canal_consorcio", m20.CREATE_CANAL_CONSORCIO),
            ("red_vial", m21.CREATE_RED_VIAL),
            ("cruce_camino", m22.CREATE_CRUCE_CAMINO),
        ):
            if existentes.get(tabla) is None:
                db.execute(text(statement))
                creadas[tabla] = True
        if existentes.get("canal_consorcio") is None:
            db.execute(text(m20.CREATE_CANAL_CONSORCIO_GEOM_INDEX))
        db.commit()
    yield
    # Deliberately NO teardown DROP: the ``db`` fixture's rollback
    # transaction still holds locks on these tables when this fixture
    # finalizes (fixture teardown order), and a DROP would block on it
    # forever. The tables stay EMPTY and committed — every reader treats
    # an empty canal table as honest zeros, and each run's guard only
    # creates what is missing.


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
