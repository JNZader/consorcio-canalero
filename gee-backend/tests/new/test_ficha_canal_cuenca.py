"""Real-compute integration tests for ``tipo=canal_cuenca`` (A7 slice 2, wire).

The ``canal_cuenca`` ficha resolves a canal's PRECOMPUTED upstream catchment —
``generate_canal_catchments`` stored a dissolved MultiPolygon in ``canal_catchment``
keyed by ``(canal_ref, variante)``. This slice wires that lookup into the ficha
response + the on-map overlay. The tests pin:

* a precomputed catchment → 200 with the uniform ficha datasets (byte-compatible
  with parcela/poligono), the echoed ``variante`` and the additive
  ``geometria_cuenca`` outline;
* the three distinct coded failures the resolver must keep apart:
    - canal unknown in ``canal_consorcio``           → 404 ``canal_no_encontrado``;
    - canal known but no catchment row yet            → 503 ``cuenca_no_computada``;
    - catchment row is oversized (``geometria`` NULL) → 422 ``cuenca_demasiado_grande``;
* the ``/analisis-zona/overlay`` endpoint clips to the CATCHMENT for
  ``tipo=canal_cuenca`` (so the A(b) "ver recortado" overlay follows the basin).

Real PG (the catchment lookup + the FK to ``canal_consorcio``) with the same
restarting-savepoint ``ficha_db`` fixture the sibling ficha tests use; the route
is gated OFF by default and flipped on per test.
"""

from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

_MIGRATION = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")

FICHA_PATH = "/api/v2/geo/analisis-zona"
OVERLAY_PATH = "/api/v2/geo/analisis-zona/overlay"

LON0, LAT0, D = -62.0, -32.0, 0.01  # same world as the other ficha tests
NODATA = -9999.0

# The stored catchment sits INSIDE the parcel/soils/raster extent so the shared
# tail reports real soils + raster coverage. A ~0.006° × 0.01° patch (UTM 20S ≈
# 565 m × 1105 m ≈ 62 ha), well under the 20 000 ha area cap.
_CATCHMENT_WKT = (
    f"MULTIPOLYGON((("
    f"{LON0} {LAT0}, {LON0 + 0.006} {LAT0}, {LON0 + 0.006} {LAT0 + D}, "
    f"{LON0} {LAT0 + D}, {LON0} {LAT0})))"
)

_SUELOS = (
    ("IVws", (LON0, LON0 + 0.004)),
    ("IVsc", (LON0 + 0.004, LON0 + 0.005)),
    (None, (LON0 + 0.005, LON0 + 0.008)),
)


def _multipoly_wkt(x0: float, x1: float) -> str:
    return (
        f"MULTIPOLYGON((({x0} {LAT0}, {x1} {LAT0}, {x1} {LAT0 + D}, {x0} {LAT0 + D}, {x0} {LAT0})))"
    )


@pytest.fixture
def ficha_db(test_engine) -> Session:
    connection = test_engine.connect()
    trans = connection.begin()
    session = Session(bind=connection)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart(sess: Any, transaction: Any) -> None:  # pragma: no cover - event glue
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    yield session

    session.close()
    trans.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def _precip_normals_para_ficha(ficha_db, tmp_path):
    """Register CHIRPS monthly normals covering the region (B2 hard dependency)."""
    ruta = str(tmp_path / "precip_region.tif")
    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=40,
        width=40,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-63.0, -31.0, 0.05, 0.05),
        nodata=NODATA,
    ) as dst:
        dst.write(np.full((40, 40), 100.0, dtype="float32"), 1)
    for mes in [*range(1, 13), "anual"]:
        ficha_db.add(
            GeoLayer(
                nombre=f"precip_normal_{mes}",
                tipo=TipoGeoLayer.PRECIP_NORMAL,
                fuente=FuenteGeoLayer.MANUAL,
                archivo_path=ruta,
                formato=FormatoGeoLayer.GEOTIFF,
                srid=4326,
                metadata_extra={"mes": mes, "version": "2026-01-01T00:00:00+00:00"},
                area_id="consorcio",
            )
        )
    ficha_db.flush()


def _app(db: Session) -> Any:
    from fastapi import FastAPI

    from app.db.session import get_db
    from app.domains.geo.ficha_errors import install_ficha_error_handler
    from app.domains.geo.router import router as geo_router
    from app.domains.geo.router_ficha import install_ficha_openapi_schemas

    app = FastAPI()
    app.include_router(geo_router, prefix="/api/v2/geo")
    install_ficha_error_handler(app)
    install_ficha_openapi_schemas(app)
    app.dependency_overrides[get_db] = lambda: db
    return app


def _enable(monkeypatch: Any) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)


def _crear_tablas_canal(db: Session) -> None:
    """Build ``canal_consorcio`` + ``canal_catchment`` from migration 0020's DDL.

    They are migration-only (no ORM model), so the test owns the DDL — but from the
    single source of truth (``UPGRADE_STATEMENTS``) rather than a hand-copy, so a
    schema drift breaks here too. ``geo_layers`` already exists (ORM ``create_all``)
    as the FK target of ``flow_dir_layer_id``.
    """
    for statement in _MIGRATION.UPGRADE_STATEMENTS:
        db.execute(text(statement))


def _seed_canal(db: Session, canal_ref: str = "canal-a", *, estado: str = "relevado") -> str:
    db.execute(
        text(
            "INSERT INTO canal_consorcio (id, nombre, estado, geom) "
            "VALUES (:id, :n, :estado, ST_GeomFromText(:wkt, 4326))"
        ),
        {
            "id": canal_ref,
            "n": f"Canal {canal_ref}",
            "estado": estado,
            "wkt": f"LINESTRING({LON0 + 0.002} {LAT0 + 0.005}, {LON0 + 0.006} {LAT0 + 0.005})",
        },
    )
    return canal_ref


def _seed_catchment(
    db: Session,
    canal_ref: str,
    *,
    variante: str = "relevado",
    wkt: str | None = _CATCHMENT_WKT,
    oversized: bool = False,
    area_ha: float = 62.0,
) -> None:
    """Insert a precomputed catchment row. ``wkt=None`` = oversized (geometria NULL)."""
    geom_sql = "NULL" if wkt is None else "ST_GeomFromText(:wkt, 4326)"
    db.execute(
        text(
            "INSERT INTO canal_catchment "
            "(canal_ref, variante, geometria, area_ha, oversized, version) "
            f"VALUES (:ref, :v, {geom_sql}, :area, :oversized, 'v1')"
        ),
        {
            "ref": canal_ref,
            "v": variante,
            "oversized": oversized,
            "area": area_ha,
            **({} if wkt is None else {"wkt": wkt}),
        },
    )


def _crear_tabla_suelos(db: Session) -> None:
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS suelos_catastro ("
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  simbolo VARCHAR(50) NOT NULL,"
            "  cap VARCHAR(10),"
            "  ip VARCHAR(50),"
            "  geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL)"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_suelos_catastro_geom "
            "ON suelos_catastro USING GIST (geometria)"
        )
    )


def _seed_suelos(db: Session) -> None:
    for i, (cap, (x0, x1)) in enumerate(_SUELOS):
        db.execute(
            text(
                "INSERT INTO suelos_catastro (simbolo, cap, geometria) "
                "VALUES (:sim, :cap, ST_GeomFromText(:wkt, 4326))"
            ),
            {"sim": f"S{i}", "cap": cap, "wkt": _multipoly_wkt(x0, x1)},
        )


def _raster_full(tmp_path: Any, name: str, value: float) -> str:
    data = np.full((16, 16), value, dtype="float32")
    path = tmp_path / name
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=16,
        width=16,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON0 - 0.003, LAT0 + D + 0.003, 0.001, 0.001),
        nodata=NODATA,
    ) as dst:
        dst.write(data, 1)
    return str(path)


def _registrar(db: Session, tipo: TipoGeoLayer, path: str) -> None:
    db.add(
        GeoLayer(
            nombre=f"test-{tipo.value}",
            tipo=tipo,
            fuente=FuenteGeoLayer.MANUAL,
            archivo_path=path,
            formato=FormatoGeoLayer.GEOTIFF,
            srid=4326,
        )
    )
    db.flush()


def _seed_full_world(db: Session, tmp_path: Any) -> str:
    _crear_tablas_canal(db)
    canal_ref = _seed_canal(db)
    _seed_catchment(db, canal_ref)
    _crear_tabla_suelos(db)
    _seed_suelos(db)
    _registrar(db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))
    _registrar(db, TipoGeoLayer.DRAINAGE_NEED, _raster_full(tmp_path, "drain.tif", 60.0))
    return canal_ref


# ── happy path — a precomputed catchment reduces to the shared ficha tail ─────


def test_canal_cuenca_computa_sobre_la_cuenca_precalculada(ficha_db, monkeypatch, tmp_path):
    """A precomputed catchment → 200, uniform datasets + variante + geometria_cuenca."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    canal_ref = _seed_full_world(ficha_db, tmp_path)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": canal_ref, "variante": "relevado"},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["tipo"] == "canal_cuenca"
    assert body["area_ha"] > 5.0  # the metric catchment area, not a 4326 degree area

    # Byte-compatible datasets with parcela/poligono — same shared tail.
    assert body["suelos"]["cobertura"] in {"total", "parcial"}
    assert body["flood_risk"]["cobertura"] == "total"
    assert {c["clase"] for c in body["flood_risk"]["clases"]} == {"Medio"}  # 40 → 30..55
    assert body["drainage_need"]["cobertura"] == "total"

    # canal_cuenca-only additive fields: the echoed variante + the outline to draw.
    assert body["variante"] == "relevado"
    assert body["geometria_cuenca"] is not None
    assert body["geometria_cuenca"]["type"] in {"Polygon", "MultiPolygon"}


def test_canal_cuenca_default_variante_es_relevado(ficha_db, monkeypatch, tmp_path):
    """Omitting ``variante`` defaults to ``relevado`` (v1's only stored variante)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    canal_ref = _seed_full_world(ficha_db, tmp_path)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "canal_cuenca", "canal_ref": canal_ref})

    assert rs.status_code == 200, rs.text
    assert rs.json()["variante"] == "relevado"


def test_canal_cuenca_deja_una_fila_de_auditoria(ficha_db, monkeypatch, tmp_path):
    """One ``zona.analisis`` row referencing the canal ref + variante (§2.5)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    canal_ref = _seed_full_world(ficha_db, tmp_path)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": canal_ref, "variante": "relevado"},
        )

    assert rs.status_code == 200, rs.text
    fila = ficha_db.execute(
        text("SELECT resource FROM audit_log WHERE action = 'zona.analisis' LIMIT 1")
    ).scalar_one()
    assert f"tipo=canal_cuenca,ref={canal_ref}" in fila
    assert "variante=relevado" in fila


# ── R3-001/R3-002 — a realistic high-vertex basin the BATCH stores is servable ─


def test_canal_cuenca_basin_de_muchos_vertices_es_servible_end_to_end(
    ficha_db, monkeypatch, tmp_path
):
    """Producer→consumer invariant: a >1000-vertex basin run through the ACTUAL
    batch (``generate_canal_catchments``) must resolve 200 at the ficha — the batch
    simplifies + cap-gates so a stored (non-oversized) catchment always passes
    ``assert_within_caps(tipo='canal_cuenca')``.

    This closes the R3-002 blind spot (the happy-path ``_CATCHMENT_WKT`` is a
    5-vertex rectangle that never exercises the vertices cap). Reverting the batch
    simplify/gate makes this FAIL: the raw pixel-staircase geometry the batch would
    then store trips ``ficha_max_vertices`` → 422 ``cuenca_demasiado_grande``.
    """
    from fastapi.testclient import TestClient
    from pyproj import Transformer
    from shapely.geometry import Point

    from app.config import settings
    from app.domains.geo.etl import generate_canal_catchments as gcc
    from app.domains.geo.ficha_service import _contar_vertices_shapely
    from tests.new import test_generate_canal_catchments as batch

    _enable(monkeypatch)
    _crear_tablas_canal(ficha_db)
    # The base flow_dir layer the batch resolves against (fake raster, EPSG:32720).
    batch._register_flow_dir(ficha_db)

    # A 400 m-radius disc with 1200 segments, centered (via a 4326→32720 round trip)
    # on the SAME world the ficha rasters cover, so the batch reprojects it straight
    # back onto the raster/soils extent. ~50 ha, area/envelope-valid, >1000 raw
    # vertices — servable ONLY because the batch simplifies before storing.
    to_utm = Transformer.from_crs(4326, 32720, always_xy=True)
    cx, cy = to_utm.transform(LON0 + 0.003, LAT0 + 0.005)
    hi_basin = Point(cx, cy).buffer(400.0, quad_segs=300)
    assert _contar_vertices_shapely(hi_basin) > settings.ficha_max_vertices

    canal_ref = _seed_canal(ficha_db)  # real trace so the batch reaches the dissolve
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))
    _registrar(ficha_db, TipoGeoLayer.DRAINAGE_NEED, _raster_full(tmp_path, "drain.tif", 60.0))

    result = gcc.generate_catchments(
        ficha_db,
        area_id=batch.AREA,
        rasterio_module=batch._FakeRasterio(),
        rasterize_fn=batch._fake_rasterize,
        shapes_fn=batch._shapes_returning(hi_basin),
        get_wbt=lambda: batch._RecordingWbt(),
    )
    assert result.computed == 1
    assert result.oversized == 0

    # The batch stored a simplified geometry under the read-path vertices cap.
    npoints = ficha_db.execute(
        text(
            "SELECT ST_NPoints(geometria) FROM canal_catchment "
            "WHERE canal_ref = :ref AND variante = 'relevado'"
        ),
        {"ref": canal_ref},
    ).scalar_one()
    assert npoints <= settings.ficha_max_vertices

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": canal_ref, "variante": "relevado"},
        )

    # 200, NOT 422 on the vertices cap — a realistic stored catchment is servable.
    assert rs.status_code == 200, rs.text
    assert rs.json()["tipo"] == "canal_cuenca"


# ── §2.6 — 503 cuenca_no_computada (canal exists, no catchment row) ────────────


def test_cuenca_no_precalculada_es_503_sin_raster(ficha_db, monkeypatch):
    """A known canal with NO catchment row → 503 ``cuenca_no_computada``, no raster."""
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tablas_canal(ficha_db)
    canal_ref = _seed_canal(ficha_db)  # canal exists, but no _seed_catchment

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese a la cuenca no computada")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": canal_ref, "variante": "relevado"},
        )

    assert rs.status_code == 503, rs.text
    body = rs.json()
    assert body["codigo"] == "cuenca_no_computada"
    assert body["canal_ref"] == canal_ref
    assert body["variante"] == "relevado"


def test_cuenca_no_precalculada_no_audita(ficha_db, monkeypatch):
    """The 503 fires BEFORE the audit commit — no ``zona.analisis`` row written."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tablas_canal(ficha_db)
    canal_ref = _seed_canal(ficha_db)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": canal_ref},
        )

    assert rs.status_code == 503, rs.text
    filas = ficha_db.execute(
        text("SELECT count(*) FROM audit_log WHERE action = 'zona.analisis'")
    ).scalar_one()
    assert filas == 0, "una cuenca no computada no debe dejar rastro de auditoria"


# ── §2.6 — 422 cuenca_demasiado_grande (oversized row, geometria NULL) ─────────


def test_cuenca_oversized_es_422(ficha_db, monkeypatch):
    """An oversized catchment (geometria NULL, oversized=true) → 422, coded."""
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tablas_canal(ficha_db)
    canal_ref = _seed_canal(ficha_db)
    _seed_catchment(ficha_db, canal_ref, wkt=None, oversized=True, area_ha=30000.0)

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese a la cuenca oversized")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": canal_ref, "variante": "relevado"},
        )

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "cuenca_demasiado_grande"
    assert body["canal_ref"] == canal_ref


# ── §2.6 — 404 canal_no_encontrado (unknown canal) ─────────────────────────────


def test_canal_cuenca_canal_desconocido_es_404(ficha_db, monkeypatch):
    """An unknown ``canal_ref`` → 404 ``canal_no_encontrado`` (distinct from 503)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tablas_canal(ficha_db)  # tables exist but empty

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": "canal-inexistente"},
        )

    assert rs.status_code == 404, rs.text
    body = rs.json()
    assert body["codigo"] == "canal_no_encontrado"
    assert body["canal_ref"] == "canal-inexistente"


# ── overlay clips to the CATCHMENT for tipo=canal_cuenca ──────────────────────


def test_overlay_suelos_recorta_a_la_cuenca(ficha_db, monkeypatch, tmp_path):
    """``/overlay`` dataset=suelos tipo=canal_cuenca → soils clipped to the catchment."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    canal_ref = _seed_full_world(ficha_db, tmp_path)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={
                "tipo": "canal_cuenca",
                "canal_ref": canal_ref,
                "variante": "relevado",
                "dataset": "suelos",
            },
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["dataset"] == "suelos"
    assert body["type"] == "FeatureCollection"
    # The catchment overlaps the IVws/IVsc soils → at least one clipped feature,
    # each carrying the normalized capability label the panel groups by.
    assert len(body["features"]) >= 1
    clases = {f["properties"]["clase"] for f in body["features"]}
    assert clases & {"IV", "sin clasificar"}


def test_overlay_canal_cuenca_no_computada_es_503(ficha_db, monkeypatch):
    """The overlay honors the SAME not-computed failure as the ficha compute path."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tablas_canal(ficha_db)
    canal_ref = _seed_canal(ficha_db)  # no catchment

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "canal_cuenca", "canal_ref": canal_ref, "dataset": "suelos"},
        )

    assert rs.status_code == 503, rs.text
    assert rs.json()["codigo"] == "cuenca_no_computada"
