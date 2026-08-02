"""Real-compute integration tests for ``tipo=canal_buffer`` (curated retarget).

`spec geo-analysis-endpoint` › "Buffer distance cap" (JDB-006) and the §2.6 rows
that only become reachable once a canal is resolved through PostGIS: 404
``canal_no_encontrado`` and 422 ``cap_excedido`` naming ``area_ha`` for a buffer
that sweeps too large an area.

The geometry is DOUBLY server-derived: the caller sends only ``canal_ref`` +
``buffer_m``; the service resolves the CURATED ``canal_consorcio`` trace (the 60
consorcio canals, keyed by their GeoJSON string id) and sweeps it with
``ST_Buffer`` in EPSG:32720. This is the A7-slice-2 correction: ``canal_buffer``
used to resolve the pgRouting ``canal_network`` graph by an int id — the wrong
set — and now targets the curated canals by their string ``canal_ref``. So, unlike
``tipo=poligono``, there is a 404 (an unknown canal) and no ``geometria_invalida``
(the trace is not caller-drawn). Everything downstream — soils overlay, raster
loop, wire vocabulary, caps, audit, semaphore — is the SAME shared tail
(``_ficha_de_geometria``) as parcela/poligono, which is exactly what these tests
pin.

**PURELY BEHAVIORAL (TestClient), never a route-table walk** — the CI
module-identity pathology documented in ``test_ficha_router_contract`` /
``test_ficha_compute``: iterating ``app.routes`` on a freshly built app comes
back EMPTY while a ``TestClient`` on the SAME app serves the route.

**Real PG + restarting savepoint.** ``analizar_zona`` COMMITS the audit row
before compute (§2.5), so the endpoint mutates the connection outside a plain
fixture's rollback; the ``ficha_db`` fixture joins the external transaction with
a restarting SAVEPOINT, the same recipe ``test_ficha_poligono`` uses.

**Feature flag.** The route is gated OFF by default; every test flips
``settings.ficha_enabled`` ON via monkeypatch.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import event, text
from sqlalchemy.orm import Session

# The intelligence models module registers ``parcelas_catastro`` /
# ``zonas_operativas`` and their FK targets with ``Base.metadata``; without this
# eager import the session-scoped ``create_all`` fails to resolve
# ``flood_labels.zona_id`` when this file runs on its own (same trap
# ``test_ficha_compute`` documents).
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

FICHA_PATH = "/api/v2/geo/analisis-zona"

# Same world as ``test_ficha_poligono`` so the soils breakdown of a buffered
# canal running through the parcel is identical to clicking/drawing there.
LON0, LAT0, D = -62.0, -32.0, 0.01  # ~105 ha near the consorcio (UTM 20S)
NODATA = -9999.0

# A short canal trace INSIDE the parcel/soils/raster extent — buffering it a few
# hundred metres yields a thin strip fully covered by the fixtures.
_CANAL_WKT = f"LINESTRING({LON0 + 0.002} {LAT0 + 0.005}, {LON0 + 0.008} {LAT0 + 0.005})"

# A ~1° (≈ 94 km) trace: buffered 2 000 m each side it sweeps ≈ 37 600 ha, well
# over the 20 000 ha area cap while its bbox (~37 600 ha) stays under the 60 000
# ha envelope cap — so ``assert_within_caps`` fails on ``area_ha`` first.
_CANAL_LARGO_WKT = f"LINESTRING({LON0} {LAT0 + 0.005}, {LON0 + 1.0} {LAT0 + 0.005})"

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
    """A session whose COMMITs are savepoint-scoped, so the endpoint cannot leak."""
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
    """Register CHIRPS monthly normals covering the fixture region (B2 dependency).

    B2 made monthly precipitation a HARD dependency: with ZERO precip normals
    registered the ficha answers 503 ``dataset_no_cargado`` (spec
    ``precip-normals-pipeline``). These canal-buffer tests assert the soils /
    flood / drainage datasets, so a 200 now requires the precip product to exist.
    A single wide 0.05° raster registered under mes 1..12 + ``anual`` covers the
    buffered strip; error-path tests short-circuit before precip assembly, so the
    extra rows are harmless.
    """
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
    """Fresh app with ONLY the geo router mounted — never ``app.main``."""
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


def _crear_tabla_canal(db: Session) -> None:
    """The curated ``canal_consorcio`` registry — only ``id`` + ``geom`` are read.

    The real table is created by migration ``0020``; ``create_all`` never sees it
    (no ORM model), so the test owns the DDL, exactly like ``suelos_catastro``. A
    minimal shape (id TEXT PK + estado CHECK + geom) is enough for the resolver.
    """
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS canal_consorcio ("
            "  id TEXT PRIMARY KEY,"
            "  nombre TEXT NOT NULL,"
            "  estado TEXT NOT NULL,"
            "  geom geometry(LineString, 4326) NOT NULL,"
            "  CONSTRAINT ck_canal_consorcio_estado CHECK (estado IN ('relevado', 'propuesto')))"
        )
    )


def _seed_canal(db: Session, wkt: str, *, canal_ref: str = "canal-a") -> str:
    db.execute(
        text(
            "INSERT INTO canal_consorcio (id, nombre, estado, geom) "
            "VALUES (:id, :n, 'relevado', ST_GeomFromText(:wkt, 4326))"
        ),
        {"id": canal_ref, "n": f"Canal {canal_ref}", "wkt": wkt},
    )
    return canal_ref


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
    """A fine EPSG:4326 GeoTIFF fully covering the parcel extent (16×16 of 0.001°)."""
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


# ── happy path — a buffered curated canal reduces to the shared ficha tail ────


def test_canal_buffer_computa_la_franja_de_influencia(ficha_db, monkeypatch, tmp_path):
    """A canal buffered inside the fixtures → 200 with the uniform ficha schema."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_canal(ficha_db)
    canal_ref = _seed_canal(ficha_db, _CANAL_WKT)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))
    _registrar(ficha_db, TipoGeoLayer.DRAINAGE_NEED, _raster_full(tmp_path, "drain.tif", 60.0))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_buffer", "canal_ref": canal_ref, "buffer_m": 200},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["tipo"] == "canal_buffer"
    # A 200 m buffer of a ~600 m canal is a real strip in metric CRS, never the
    # tiny 4326 degree area — proof the buffer ran in EPSG:32720.
    assert body["area_ha"] > 5.0

    # Same shared compute tail as parcela/poligono: soils + both rasters present.
    assert body["suelos"]["cobertura"] in {"total", "parcial"}
    assert body["flood_risk"]["cobertura"] == "total"
    assert {c["clase"] for c in body["flood_risk"]["clases"]} == {"Medio"}  # 40 → 30..55
    assert body["drainage_need"]["cobertura"] == "total"

    # canal_buffer carries no BPA/account block, and no canal_cuenca extras.
    assert "nro_cuenta" not in body
    assert "pilar_verde" not in body
    assert body["geometria_cuenca"] is None
    assert body["variante"] is None


def test_canal_buffer_deja_una_fila_de_auditoria(ficha_db, monkeypatch, tmp_path):
    """One ``zona.analisis`` row, referencing the canal ref + buffer (§2.5)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_canal(ficha_db)
    canal_ref = _seed_canal(ficha_db, _CANAL_WKT)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_buffer", "canal_ref": canal_ref, "buffer_m": 200},
        )

    assert rs.status_code == 200, rs.text
    fila = ficha_db.execute(
        text("SELECT resource FROM audit_log WHERE action = 'zona.analisis' LIMIT 1")
    ).scalar_one()
    assert f"tipo=canal_buffer,ref={canal_ref}" in fila
    assert "buffer_m=200" in fila


# ── §2.6 — 404 canal_no_encontrado (unknown ref) ──────────────────────────────


def test_canal_desconocido_es_404_sin_raster(ficha_db, monkeypatch):
    """An unknown ``canal_ref`` → 404 ``canal_no_encontrado``, no raster opened.

    Resolution returns no row → the 404 fires before ``assert_within_caps`` and
    long before any raster loop. We prove NO raster was opened by making
    ``extract_zonal_profile`` explode if reached.
    """
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tabla_canal(ficha_db)  # table exists but empty

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese al canal inexistente")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_buffer", "canal_ref": "canal-inexistente", "buffer_m": 200},
        )

    assert rs.status_code == 404, rs.text
    body = rs.json()
    assert body["codigo"] == "canal_no_encontrado"
    assert body["canal_ref"] == "canal-inexistente"


def test_canal_desconocido_no_audita(ficha_db, monkeypatch):
    """The 404 fires BEFORE the audit commit — no ``zona.analisis`` row written."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_canal(ficha_db)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_buffer", "canal_ref": "canal-fantasma", "buffer_m": 200},
        )

    assert rs.status_code == 404, rs.text
    filas = ficha_db.execute(
        text("SELECT count(*) FROM audit_log WHERE action = 'zona.analisis'")
    ).scalar_one()
    assert filas == 0, "un canal inexistente no debe dejar rastro de auditoria"


# ── §2.6 — 422 cap_excedido naming buffer_m (schema cap) ───────────────────────


def test_buffer_sobre_cap_es_422_naming_buffer_m(ficha_db, monkeypatch):
    """``buffer_m`` over ``ficha_max_buffer_m`` → 422 ``cap_excedido`` naming buffer_m.

    The schema validator is the cheap gate: it rejects an over-cap distance on the
    wire, before any DB round-trip or canal lookup. No ``canal_consorcio`` row is
    even needed.
    """
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.domains.geo import ficha_service

    _enable(monkeypatch)

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se resolvio geometria pese al buffer sobre cap")

    monkeypatch.setattr(ficha_service, "_resolver_canal_buffer", _boom)

    over = settings.ficha_max_buffer_m + 1.0
    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "canal_buffer", "canal_ref": "canal-a", "buffer_m": over},
        )

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "cap_excedido"
    assert body["cap"] == "buffer_m"
    assert body["valor"] > body["limite"]


# ── §2.6 — 422 cap_excedido naming area_ha (buffered AREA over cap) ────────────


def test_area_barrida_sobre_cap_es_422_naming_area_ha(ficha_db, monkeypatch):
    """A long canal buffered at the max distance sweeps > area cap → 422 area_ha.

    This is the whole reason ``assert_within_caps`` runs on the BUFFERED geometry
    and not just on ``buffer_m`` (JDB-006): ``buffer_m`` is inside its schema cap
    (2 000 m), yet the area the buffer sweeps along a ~94 km canal is ~37 600 ha,
    well over the 20 000 ha area cap. The cap must catch the resolved zone. No
    raster is opened.
    """
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tabla_canal(ficha_db)
    canal_ref = _seed_canal(ficha_db, _CANAL_LARGO_WKT, canal_ref="canal-largo")

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese al area sobre cap")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={
                "tipo": "canal_buffer",
                "canal_ref": canal_ref,
                "buffer_m": settings.ficha_max_buffer_m,
            },
        )

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "cap_excedido"
    # area is checked before envelope in assert_within_caps, so area_ha wins.
    assert body["cap"] == "area_ha"
    assert body["valor"] > body["limite"]


# ── the limiter prices canal_buffer at cost 5 (design §2.2, JDB-006) ───────────


def test_canal_buffer_cuesta_5_en_el_limitador():
    """``canal_buffer`` is as expensive as a drawn polygon, never priced at 1.

    A cheap, import-only assertion on the router's cost table (NOT a route-table
    walk): the raster work of a buffered canal is the same as a polygon's, so the
    limiter must charge it 5, not the parcela-click price of 1.
    """
    from app.domains.geo.router_ficha import COSTO_POR_TIPO

    assert COSTO_POR_TIPO["canal_buffer"] == 5
    assert COSTO_POR_TIPO["canal_buffer"] == COSTO_POR_TIPO["poligono"]
