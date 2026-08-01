"""Real-compute integration tests for ``tipo=poligono`` (PR A5).

`spec geo-analysis-endpoint` › "Self-intersecting drawn polygon" (JDB-008) and
the two §2.6 rows A3a-ii deferred because they were only reachable once a
caller-supplied geometry resolved through PostGIS: 422 ``geometria_invalida``
and 422 ``cap_excedido`` naming ``area_ha`` for a drawn polygon.

The geometry comes from the REQUEST body, not from a DB lookup, so unlike
``tipo=parcela`` there is no 404 and no ``parcelas_catastro`` seed. Everything
else — soils overlay, raster loop, wire vocabulary, caps, audit, semaphore — is
the SAME path as parcela (``_ficha_de_geometria``), which is exactly what these
tests pin.

**PURELY BEHAVIORAL (TestClient), never a route-table walk** — the CI
module-identity pathology documented in ``test_ficha_router_contract`` /
``test_ficha_compute``: iterating ``app.routes`` on a freshly built app comes
back EMPTY while a ``TestClient`` on the SAME app serves the route. The contract
is proven only by response codes/bodies, never by ``app.main`` and never by
inspecting the route table.

**Real PG + restarting savepoint.** ``analizar_zona`` COMMITS the audit row
before compute (§2.5), so the endpoint mutates the connection outside a plain
fixture's rollback; the ``ficha_db`` fixture joins the external transaction with
a restarting SAVEPOINT, the same recipe ``test_ficha_compute`` uses.

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
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# The intelligence models module registers ``parcelas_catastro`` /
# ``zonas_operativas`` and their FK targets with ``Base.metadata``; without this
# eager import the session-scoped ``create_all`` fails to resolve
# ``flood_labels.zona_id`` when this file runs on its own (same trap
# ``test_ficha_compute`` documents).
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

FICHA_PATH = "/api/v2/geo/analisis-zona"

# Same world as ``test_ficha_compute`` so the soils breakdown is identical: the
# drawn polygon that covers the whole parcel extent must produce the same
# per-class result as clicking that parcel.
LON0, LAT0, D = -62.0, -32.0, 0.01  # ~105 ha near the consorcio (UTM 20S)
NODATA = -9999.0

# A valid drawn polygon covering the full parcel extent (closed ring, CCW).
_PARCELA_COORDS = [
    [LON0, LAT0],
    [LON0 + D, LAT0],
    [LON0 + D, LAT0 + D],
    [LON0, LAT0 + D],
    [LON0, LAT0],
]

# A well-formed GeoJSON ring (closed, 4 positions, valid coords → passes the cheap
# schema validators) whose three vertices are COLLINEAR: it encloses no area, so
# ST_MakeValid collapses it to a line and ST_CollectionExtract(..., 3) yields an
# EMPTY polygon → 422 ``geometria_invalida`` (verified against PostGIS: this shape
# is reliably empty, unlike a near-collinear ring that float noise keeps tiny).
_DEGENERADO = [
    [LON0, LAT0],
    [LON0 + D, LAT0],
    [LON0 + 2 * D, LAT0],
    [LON0, LAT0],
]

_SUELOS = (
    ("IVws", (LON0, LON0 + 0.004)),
    ("IVsc", (LON0 + 0.004, LON0 + 0.005)),
    (None, (LON0 + 0.005, LON0 + 0.008)),
)


def _poligono(coords: list[list[float]]) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [coords]}


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


# ── A5.1 happy path — a drawn polygon reduces to the parcela result ──────────


def test_poligono_dibujado_completo(ficha_db, monkeypatch, tmp_path):
    """A valid drawn polygon over the parcel extent → 200, same soils/raster shape."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))
    _registrar(ficha_db, TipoGeoLayer.DRAINAGE_NEED, _raster_full(tmp_path, "drain.tif", 60.0))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH, json={"tipo": "poligono", "geometry": _poligono(_PARCELA_COORDS)}
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["tipo"] == "poligono"
    # Metric area of a ~0.01°×0.01° box near -32° lat is ~105 ha, never the tiny
    # 4326 degree area — proof the polygon was projected to 32720.
    assert body["area_ha"] > 50.0

    suelos = body["suelos"]
    assert suelos["cobertura"] == "parcial"  # 80 % covered, 20 % gap
    por_clase = {c["clase"]: c for c in suelos["clases"]}
    assert por_clase["IV"]["pct"] == pytest.approx(50.0, abs=1.0)
    assert set((por_clase["IV"]["detalle"] or "").split(",")) == {"IVsc", "IVws"}
    assert por_clase["sin clasificar"]["pct"] == pytest.approx(30.0, abs=1.0)
    assert por_clase["sin dato"]["pct"] == pytest.approx(20.0, abs=1.0)

    assert body["flood_risk"]["cobertura"] == "total"
    assert {c["clase"] for c in body["flood_risk"]["clases"]} == {"Medio"}  # 40 → 30..55
    assert body["drainage_need"]["cobertura"] == "total"

    # poligono carries no BPA/account block — there is no single parcel to join.
    assert "nro_cuenta" not in body
    assert "pilar_verde" not in body


def test_poligono_bowtie_se_repara_y_computa(ficha_db, monkeypatch, tmp_path):
    """A figure-eight ring is REPAIRED by ST_MakeValid into valid polygons → 200.

    This is the positive half of JDB-008: a self-intersection that decomposes into
    real area must NOT be rejected — the repair is exactly what makes a hand-drawn
    ring usable. Only a repair that leaves nothing polygonal is a 422 (next test).
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    # Figure-eight over the parcel: crossing diagonals → two triangles after repair.
    bowtie = [
        [LON0, LAT0],
        [LON0 + D, LAT0 + D],
        [LON0 + D, LAT0],
        [LON0, LAT0 + D],
        [LON0, LAT0],
    ]

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "poligono", "geometry": _poligono(bowtie)})

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["tipo"] == "poligono"
    assert body["area_ha"] > 0.0  # the two repaired triangles have real area


# ── A5.4 / §2.6 — geometria_invalida reachable for poligono (JDB-008) ────────


def test_poligono_degenerado_es_422_sin_raster(ficha_db, monkeypatch, tmp_path):
    """A collinear (zero-area) ring collapses to a line under ST_MakeValid → 422.

    ``ST_CollectionExtract(ST_MakeValid(...), 3)`` yields an EMPTY polygon, which
    is 422 ``geometria_invalida`` — never a silently wrong ST_Intersection. We
    prove NO raster was opened by making ``extract_zonal_profile`` explode if
    reached (the rejection happens in geometry resolution, before compute).
    """
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese a la geometria invalida")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "poligono", "geometry": _poligono(_DEGENERADO)})

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "geometria_invalida"
    assert "motivo" in body


def test_poligono_audita_nada_cuando_geometria_invalida(ficha_db, monkeypatch):
    """The 422 fires BEFORE the audit commit — no ``zona.analisis`` row is written."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "poligono", "geometry": _poligono(_DEGENERADO)})

    assert rs.status_code == 422, rs.text
    filas = ficha_db.execute(
        text("SELECT count(*) FROM audit_log WHERE action = 'zona.analisis'")
    ).scalar_one()
    assert filas == 0, "una geometria rechazada no debe dejar rastro de auditoria"


# ── A5.4 / §2.6 — cap_excedido area_ha reachable through the wire ────────────


def test_poligono_area_sobre_cap_es_422_naming_area_ha(ficha_db, monkeypatch):
    """A large drawn polygon → 422 ``cap_excedido`` naming ``area_ha``, no raster.

    The area cap is the whole reason it exists for a user-drawn polygon: nothing
    in the schema bounds a caller-supplied geometry's AREA (only its vertex
    count). ``assert_within_caps`` over the resolved 32720 shape is the authority
    (§2.1). A ~0.3°×0.3° box near -32° is ~90 000 ha, well over the 20 000 ha cap.
    """
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese al cap_excedido — el cap no corto antes")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    grande = [
        [LON0, LAT0],
        [LON0 + 0.3, LAT0],
        [LON0 + 0.3, LAT0 + 0.3],
        [LON0, LAT0 + 0.3],
        [LON0, LAT0],
    ]

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "poligono", "geometry": _poligono(grande)})

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "cap_excedido"
    # area is checked before envelope in assert_within_caps, so area_ha wins.
    assert body["cap"] == "area_ha"
    assert body["valor"] > body["limite"]


# ── R4-001 — a DB fault becomes a coded FichaError, never a 500 + Sentry ─────


class _FakeOrig(Exception):
    """Stand-in for the psycopg2 error under ``OperationalError.orig``."""

    def __init__(self, pgcode: str | None) -> None:
        super().__init__("simulated db fault")
        self.pgcode = pgcode


def _inyectar_falla_db(monkeypatch: Any, db: Session, marcador: str, pgcode: str | None) -> None:
    """Make ``db.execute`` raise a real ``OperationalError`` on the target query.

    The fake fires only when ``marcador`` appears in the statement text, so the
    per-request ``set_config`` and the pre-compute audit INSERT still run for
    real — only the geometry resolver / soils overlay explodes, exactly where the
    R4-001 gap lived. Applied AFTER seeding so the DDL/seed statements are untouched.
    """
    real_execute = db.execute

    def _fake(statement: Any, *args: Any, **kwargs: Any) -> Any:
        if marcador in str(statement):
            raise OperationalError("stmt", {}, _FakeOrig(pgcode))
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", _fake)


def test_poligono_db_timeout_es_503_analisis_timeout_y_libera_slot(ficha_db, monkeypatch, tmp_path):
    """A statement_timeout (57014) during the soils overlay → 503 ``analisis_timeout``.

    The overlay runs INSIDE the semaphore, so this also proves the slot is
    released on the DB-fault path (finally), and that the flat FichaError contract
    is honoured — never a bare 500 ``INTERNAL_ERROR`` from the generic handler.
    """
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    # Fresh, deterministic semaphore so the release assertion below is exact.
    ficha_service.reset_ficha_slots()
    # 57014 is fired on the soils overlay — inside slot_de_computo().
    _inyectar_falla_db(monkeypatch, ficha_db, "suelos_catastro", "57014")

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH, json={"tipo": "poligono", "geometry": _poligono(_PARCELA_COORDS)}
        )

    assert rs.status_code == 503, rs.text
    body = rs.json()
    assert body["codigo"] == "analisis_timeout"
    assert body["codigo"] != "INTERNAL_ERROR"
    assert set(body) >= {"detail", "codigo"}  # flat FichaError body, not the nested 500 shape
    assert "error" not in body

    # The slot must be back: acquire every slot non-blocking, proving none leaked.
    from app.config import settings

    slots = ficha_service.get_ficha_slots()
    adquiridos = [slots.acquire(blocking=False) for _ in range(settings.ficha_max_concurrency)]
    try:
        assert all(adquiridos), "el semaforo no se libero tras la falla de DB"
    finally:
        for ok in adquiridos:
            if ok:
                slots.release()


def test_poligono_db_error_generico_es_503_base_no_disponible(ficha_db, monkeypatch):
    """A non-57014 ``OperationalError`` in the resolver → 503 ``base_de_datos_no_disponible``.

    A connection drop / deadlock is real infrastructure trouble, so it maps to a
    DISTINCT codigo from the expected-under-abuse timeout (the codigo is what makes
    ``ficha_error_handler`` log it at ERROR, not WARNING) — but still a coded 503,
    never a 500.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)

    # "reparada" is unique to _POLIGONO_SQL → the fault hits geometry resolution,
    # before the audit commit and before the semaphore. 08006 = connection failure.
    _inyectar_falla_db(monkeypatch, ficha_db, "reparada", "08006")

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH, json={"tipo": "poligono", "geometry": _poligono(_PARCELA_COORDS)}
        )

    assert rs.status_code == 503, rs.text
    body = rs.json()
    assert body["codigo"] == "base_de_datos_no_disponible"
    assert body["codigo"] != "analisis_timeout"
    assert "error" not in body  # flat contract, not the nested 500 body
