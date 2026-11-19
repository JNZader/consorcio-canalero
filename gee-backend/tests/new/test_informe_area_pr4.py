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
        return etl_suelos.run_etl(
            db, fetch_json=lambda _url: wfs_suelos.pagina_wfs(features)
        )


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
                for f in db.execute(text("SELECT DISTINCT fecha_de_bajada FROM idecor_suelos_50mil")).scalars()
            }
        assert almacenados == 3  # re-run converged, never duplicated
        assert len(fechas) == 1  # one stamp per run, the second run's
    finally:
        with factory() as db:
            db.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
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
            db.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
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
                etl_suelos.run_etl(
                    db, fetch_json=lambda _u: wfs_suelos.pagina_wfs([rota])
                )
            # Fail-closed: the transaction was never committed, so the
            # previous state (empty) survives the refusal.
            assert db.execute(text("SELECT count(*) FROM idecor_suelos_50mil")).scalar_one() == 0
    finally:
        with factory() as db:
            db.execute(
                text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": str(zona_id)}
            )
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
    assert service.suelos_idecor_dataset(db, '{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}', 100.0) is None
    assert service.suelos_idecor_por_zona(db, [(uuid.uuid4(), 100.0)]) == {}
