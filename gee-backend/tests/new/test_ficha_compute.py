"""Real-compute integration tests for the ficha territorial (PR A3b).

`spec geo-analysis-endpoint` › "Per-class breakdown returned", "Empty suelos
table", "Nodata pixels are excluded from percentages", "Partial coverage
flagged". Covers A3b.1-A3b.7.

**PURELY BEHAVIORAL (TestClient), never a route-table walk** — same CI
module-identity pathology documented at length in ``test_ficha_router_contract``:
building an app and iterating ``app.routes`` comes back EMPTY even while a
``TestClient`` on the SAME app serves the route. The contract is proven only by
response codes/bodies from a locally built app, never by ``app.main`` and never
by inspecting the route table.

**Real PG.** ``parcelas_catastro`` / ``geo_layers`` / ``audit_log`` are ORM
tables ``create_all`` builds; ``suelos_catastro`` has no ORM model (the migration
owns it), so this module creates it via raw DDL inside the test transaction, the
same way ``test_ficha_migration`` does.

**Isolation.** ``analizar_zona`` COMMITS the audit row before compute (§2.5), so
the endpoint mutates the connection outside a plain fixture's rollback. The
``ficha_db`` fixture therefore joins the external transaction with a restarting
SAVEPOINT: the endpoint's ``commit`` only releases a savepoint, and the outer
rollback discards every seed + audit row at teardown. No cross-test leak.

**Feature flag.** The route is gated OFF by default; every test flips
``settings.ficha_enabled`` ON via monkeypatch (A3b turns compute real; the config
default stays False until a deployment enables it).
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# ``parcelas_catastro`` lives in the intelligence models module, which nothing in
# conftest imports eagerly — without this the session-scoped ``create_all`` skips
# the table when this file runs on its own (same trap conftest documents).
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

FICHA_PATH = "/api/v2/geo/analisis-zona"

# ── the parcel and its world, in EPSG:4326 ──────────────────────────────────
LON0, LAT0, D = -62.0, -32.0, 0.01  # ~105 ha near the consorcio (UTM 20S)
NOMENCLATURA = "19-04-12-0001-1"
NODATA = -9999.0

_PARCELA_WKT = (
    f"POLYGON(({LON0} {LAT0}, {LON0 + D} {LAT0}, {LON0 + D} {LAT0 + D}, "
    f"{LON0} {LAT0 + D}, {LON0} {LAT0}))"
)


def _multipoly(x0: float, x1: float) -> str:
    """A soil polygon spanning the full parcel height between lon ``x0`` and ``x1``."""
    return (
        f"MULTIPOLYGON((({x0} {LAT0}, {x1} {LAT0}, {x1} {LAT0 + D}, {x0} {LAT0 + D}, {x0} {LAT0})))"
    )


# lon slices of the 0.01° parcel → proportional metric area (same latitude band):
#   IVws  40%  |  IVsc 10%  |  NULL 30%  |  uncovered 20% → "sin dato"
_SUELOS = (
    ("IVws", _multipoly(LON0, LON0 + 0.004)),
    ("IVsc", _multipoly(LON0 + 0.004, LON0 + 0.005)),
    (None, _multipoly(LON0 + 0.005, LON0 + 0.008)),
)


@pytest.fixture
def ficha_db(test_engine) -> Session:
    """A session whose COMMITs are savepoint-scoped, so the endpoint cannot leak.

    ``analizar_zona`` commits the audit row mid-request; a plain
    connection-bound session would let that escape the per-test rollback. The
    restarting-savepoint recipe keeps the outer transaction open regardless.
    """
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
    """Register a full set of CHIRPS monthly normals covering the fixture region.

    B2 made monthly precipitation a HARD dependency: with ZERO precip normals
    registered the ficha now answers 503 ``dataset_no_cargado`` (spec
    ``precip-normals-pipeline`` › "Monthly series for a zone"). These A3b tests
    predate B2 and assert the soils / flood / drainage datasets, so a 200 now
    requires the precip product to exist. A single wide 0.05° raster (≈ CHIRPS
    native) registered under mes 1..12 + ``anual`` covers the ~105 ha fixture
    parcel with room to spare. Error-path tests (404 / cap / suelos-empty 503 /
    raster_ilegible) short-circuit BEFORE precip assembly, so these extra rows
    are harmless to them.
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


# ── seeding ─────────────────────────────────────────────────────────────────


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


def _seed_parcela(db: Session, *, nro_cuenta: str | None = "12345") -> None:
    db.execute(
        text(
            "INSERT INTO parcelas_catastro (nomenclatura, geometria, nro_cuenta) "
            "VALUES (:nom, ST_GeomFromText(:wkt, 4326), :cta)"
        ),
        {"nom": NOMENCLATURA, "wkt": _PARCELA_WKT, "cta": nro_cuenta},
    )


def _seed_suelos(db: Session) -> None:
    for i, (cap, wkt) in enumerate(_SUELOS):
        db.execute(
            text(
                "INSERT INTO suelos_catastro (simbolo, cap, geometria) "
                "VALUES (:sim, :cap, ST_GeomFromText(:wkt, 4326))"
            ),
            {"sim": f"S{i}", "cap": cap, "wkt": wkt},
        )


def _raster(
    tmp_path: Any,
    name: str,
    value: float,
    *,
    west: float,
    north: float,
    pixel: float,
    npix: int = 16,
    ncols: int | None = None,
    all_nodata: bool = False,
) -> str:
    """Write a constant-value EPSG:4326 GeoTIFF. ``all_nodata`` fills with NODATA."""
    ncols = ncols if ncols is not None else npix
    fill = NODATA if all_nodata else value
    data = np.full((npix, ncols), fill, dtype="float32")
    path = tmp_path / name
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=npix,
        width=ncols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(west, north, pixel, pixel),
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


def _raster_full(tmp_path: Any, name: str, value: float, **kw: Any) -> str:
    """A fine raster fully covering the parcel (16×16 of 0.001°)."""
    return _raster(
        tmp_path, name, value, west=LON0 - 0.003, north=LAT0 + D + 0.003, pixel=0.001, npix=16, **kw
    )


# ── A3b.1/A3b.2/A3b.3/A3b.4 — the full happy path ───────────────────────────


def test_parcela_ficha_completa(ficha_db, monkeypatch, tmp_path):
    """Parcel click → 200 with real soils %, risk %, correct area, full raster coverage."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))
    _registrar(ficha_db, TipoGeoLayer.DRAINAGE_NEED, _raster_full(tmp_path, "drain.tif", 60.0))

    area_m2 = ficha_db.execute(
        text(
            "SELECT ST_Area(ST_Transform(geometria, 32720)) FROM parcelas_catastro "
            "WHERE nomenclatura = :n"
        ),
        {"n": NOMENCLATURA},
    ).scalar_one()
    esperado_ha = area_m2 / 10_000.0

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 200, rs.text
    body = rs.json()

    # area_ha is the METRIC area (ST_Area in 32720), not the tiny 4326 degree area.
    assert esperado_ha > 50.0
    assert body["area_ha"] == pytest.approx(esperado_ha, rel=1e-3)

    # ── soils: IV (grouped IVws+IVsc) 50 %, sin clasificar 30 %, sin dato 20 % ──
    suelos = body["suelos"]
    assert suelos["cobertura"] == "parcial"  # 80 % covered, 20 % gap
    por_clase = {c["clase"]: c for c in suelos["clases"]}
    assert por_clase["IV"]["pct"] == pytest.approx(50.0, abs=1.0)
    assert set((por_clase["IV"]["detalle"] or "").split(",")) == {"IVsc", "IVws"}
    assert por_clase["sin clasificar"]["pct"] == pytest.approx(30.0, abs=1.0)
    assert por_clase["sin dato"]["pct"] == pytest.approx(20.0, abs=1.0)
    assert sum(c["pct"] for c in suelos["clases"]) == pytest.approx(100.0, abs=1.0)
    # sin dato is never merged with the NULL-cap "sin clasificar"
    assert "sin dato" != "sin clasificar"
    assert por_clase["sin dato"].get("detalle") is None

    # ── rasters: primitive vocabulary mapped to the wire ──
    flood = body["flood_risk"]
    assert flood["cobertura"] == "total"
    assert flood["cobertura_ratio"] == pytest.approx(1.0, abs=0.02)
    assert flood["pixel_count"] > 0
    assert {c["clase"] for c in flood["clases"]} == {"Medio"}  # value 40 → 30..55
    assert flood["clases"][0]["pct"] == pytest.approx(100.0, abs=0.5)

    drainage = body["drainage_need"]
    assert drainage["cobertura"] == "total"
    assert {c["clase"] for c in drainage["clases"]} == {"Alto"}  # value 60 → 50..70

    # A big parcel over a fine raster is NOT low-confidence (JDB-017 relative rule).
    assert flood["low_confidence"] is False

    # Client-side BPA join (design [R1]): the backend carries NO account block.
    assert "nro_cuenta" not in body
    assert "pilar_verde" not in body


# ── A3b.5 — 404 on unknown nomenclatura ─────────────────────────────────────


def test_404_nomenclatura_desconocida(ficha_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)  # suelos present so a 404 is about the parcel, not the dataset

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": "99-99-99-9999-9"})

    assert rs.status_code == 404
    body = rs.json()
    assert body["codigo"] == "parcela_no_encontrada"
    assert body["nomenclatura"] == "99-99-99-9999-9"


# ── A3b.4 — 503 dataset_no_cargado when suelos is empty ─────────────────────


def test_503_suelos_vacio(ficha_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)  # table exists but stays EMPTY
    _seed_parcela(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 503
    body = rs.json()
    assert body["codigo"] == "dataset_no_cargado"
    assert body["dataset"] == "suelos"


# ── ledger: a missing/disjoint raster is sin_cobertura, NOT a 0 % reading ────


def test_raster_disjunto_es_sin_cobertura(ficha_db, monkeypatch, tmp_path):
    """A raster whose extent does not overlap the parcel → sin_cobertura, empty, 0 px."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    # flood raster far away (disjoint) → non-overlap ValueError → coverage none.
    _registrar(
        ficha_db,
        TipoGeoLayer.FLOOD_RISK,
        _raster(tmp_path, "flood.tif", 40.0, west=-50.0, north=-20.0, pixel=0.001, npix=8),
    )

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 200, rs.text
    flood = rs.json()["flood_risk"]
    assert flood["cobertura"] == "sin_cobertura"
    assert flood["clases"] == []
    assert flood["pixel_count"] == 0
    # drainage_need was never registered → also sin_cobertura, never a dropped key.
    assert rs.json()["drainage_need"]["cobertura"] == "sin_cobertura"


def test_raster_todo_nodata_es_sin_cobertura(ficha_db, monkeypatch, tmp_path):
    """nodata ≠ 0 %: a raster overlapping the parcel but all-nodata is sin_cobertura."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(
        ficha_db,
        TipoGeoLayer.FLOOD_RISK,
        _raster_full(tmp_path, "flood.tif", 40.0, all_nodata=True),
    )

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 200, rs.text
    flood = rs.json()["flood_risk"]
    assert flood["cobertura"] == "sin_cobertura"
    assert flood["pixel_count"] == 0
    assert flood["clases"] == []


def test_raster_parcial_en_parcela_a_medias(ficha_db, monkeypatch, tmp_path):
    """A raster covering only the left half of the parcel → cobertura parcial."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    # 16×8 of 0.001° from the west edge → covers lon [-62.003, -61.995] ≈ left half.
    _registrar(
        ficha_db,
        TipoGeoLayer.FLOOD_RISK,
        _raster(
            tmp_path,
            "flood.tif",
            40.0,
            west=LON0 - 0.003,
            north=LAT0 + D + 0.003,
            pixel=0.001,
            npix=16,
            ncols=8,
        ),
    )

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 200, rs.text
    flood = rs.json()["flood_risk"]
    assert flood["cobertura"] == "parcial"
    assert 0.0 < flood["cobertura_ratio"] < 0.99


def test_parcela_chica_es_low_confidence(ficha_db, monkeypatch, tmp_path):
    """A parcel that is only a few coarse pixels wide flags low_confidence (JDB-017)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    # 4×4 of 0.005° (~26 ha/pixel) fully covering the ~105 ha parcel: ratio ≈ 4 < K=10.
    _registrar(
        ficha_db,
        TipoGeoLayer.FLOOD_RISK,
        _raster(
            tmp_path,
            "flood.tif",
            40.0,
            west=LON0 - 0.005,
            north=LAT0 + D + 0.005,
            pixel=0.005,
            npix=4,
        ),
    )

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 200, rs.text
    flood = rs.json()["flood_risk"]
    assert flood["cobertura"] == "total"
    assert flood["low_confidence"] is True


def test_parcela_nro_cuenta_null_es_200_sin_bpa(ficha_db, monkeypatch, tmp_path):
    """A parcel with NULL nro_cuenta returns 200 and no BPA/account block ([R1])."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db, nro_cuenta=None)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert "nro_cuenta" not in body
    assert "pilar_verde" not in body


# ── A3b.6 — audit durability: the row survives a compute failure ─────────────


def test_auditoria_persiste_tras_falla_de_compute(ficha_db, monkeypatch, tmp_path):
    """A raster that fails to read → 503 raster_ilegible, and the audit row is STILL there.

    The audit is committed before the semaphore (§2.5), so a later compute failure
    cannot erase the Ley 25.326 trace.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    # A file that exists but is not a valid GeoTIFF → rasterio raises (non-ValueError).
    corrupto = tmp_path / "corrupto.tif"
    corrupto.write_bytes(b"esto no es un geotiff\x00\x01\x02")
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, str(corrupto))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 503
    assert rs.json()["codigo"] == "raster_ilegible"

    filas = ficha_db.execute(
        text("SELECT count(*) FROM audit_log WHERE action = 'zona.analisis'")
    ).scalar_one()
    assert filas >= 1, "el rastro de auditoria se perdio pese al fallo de compute"


# ── A3b.7 — perf gate: 20 sequential requests, p95 ≤ 1.5 s ───────────────────


def test_perf_gate_p95(ficha_db, monkeypatch, tmp_path, capsys):
    """20 sequential requests on the fixture parcel; assert p95 ≤ 1.5 s (JD-A-009)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))
    _registrar(ficha_db, TipoGeoLayer.DRAINAGE_NEED, _raster_full(tmp_path, "drain.tif", 60.0))

    tiempos: list[float] = []
    cuerpo = {"tipo": "parcela", "nomenclatura": NOMENCLATURA}
    with TestClient(_app(ficha_db)) as cliente:
        for _ in range(20):
            t0 = time.perf_counter()
            rs = cliente.post(FICHA_PATH, json=cuerpo)
            tiempos.append(time.perf_counter() - t0)
            assert rs.status_code == 200, rs.text

    p95 = float(np.percentile(tiempos, 95))
    with capsys.disabled():
        print(
            f"\n[A3b.7 perf] p95={p95 * 1000:.1f} ms sobre 20 pedidos "
            f"(min={min(tiempos) * 1000:.1f} max={max(tiempos) * 1000:.1f})"
        )
    assert p95 <= 1.5, f"p95={p95:.3f}s supera el gate de 1.5s"


# ── F1 — statement_timeout is applied on the compute path (R1-002 + R4-002) ──


def test_statement_timeout_aplicado_en_compute(ficha_db, monkeypatch, tmp_path, test_engine):
    """The configured ficha statement_timeout is SET (transaction-local) per request.

    Behavioral: a huge legitimate parcel could otherwise pin a connection +
    threadpool thread unbounded. We assert, through the endpoint, that the
    request issued ``set_config('statement_timeout', <ms>, true)`` with the
    configured value — the bound that caps that risk.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import event as sa_event

    from app.config import settings

    _enable(monkeypatch)
    monkeypatch.setattr(settings, "ficha_statement_timeout_ms", 7000)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    vistos: list[Any] = []

    def _capturar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if "set_config" in statement and "statement_timeout" in statement:
            vistos.append(parameters)

    sa_event.listen(test_engine, "before_cursor_execute", _capturar)
    try:
        with TestClient(_app(ficha_db)) as cliente:
            rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})
    finally:
        sa_event.remove(test_engine, "before_cursor_execute", _capturar)

    assert rs.status_code == 200, rs.text
    assert vistos, "nunca se aplico statement_timeout en el request de ficha"
    # the CONFIGURED value was bound (as text — set_config takes text), not a literal.
    assert any("7000" in str(p) for p in vistos), vistos


# ── F2 — an unregistered raster leaves a breadcrumb (R4-001) ─────────────────


def test_raster_no_registrado_deja_rastro(ficha_db, monkeypatch, tmp_path):
    """No raster registered → sin_cobertura (unchanged) AND a per-dataset log line.

    A freshly-provisioned box whose flood/drainage pipeline has not run yet must
    leave observability, not silently answer sin_cobertura on every ficha.
    """
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    # No _registrar(...) at all → both flood_risk and drainage_need are unregistered.

    registros: list[tuple[str, Any]] = []
    orig_info = ficha_service.logger.info

    def _spy(event: str, *args: Any, **kw: Any) -> Any:
        registros.append((event, kw.get("dataset")))
        return orig_info(event, *args, **kw)

    monkeypatch.setattr(ficha_service.logger, "info", _spy)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 200, rs.text
    # Response is unchanged: still sin_cobertura for both secondary rasters.
    assert rs.json()["flood_risk"]["cobertura"] == "sin_cobertura"
    assert rs.json()["drainage_need"]["cobertura"] == "sin_cobertura"
    # The breadcrumb fired once per unregistered dataset.
    assert ("raster de ficha no registrado", "flood_risk") in registros
    assert ("raster de ficha no registrado", "drainage_need") in registros


# ── F3 — the LIVE parcela area cap rejects before any raster is opened (R3-001) ─


def test_cap_parcela_excedido_rechaza_antes_de_compute(ficha_db, monkeypatch, tmp_path):
    """An oversized parcela → 422 cap_excedido THROUGH the endpoint, no compute.

    The cap enforcement is live for ``tipo=parcela``; a broken cap-wiring would
    otherwise let all current tests pass. We shrink ``ficha_max_area_ha`` so the
    seeded ~105 ha parcel exceeds it, and prove NO raster was opened by making
    ``extract_zonal_profile`` explode if it is ever reached.
    """
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    monkeypatch.setattr(settings, "ficha_max_area_ha", 1.0)  # ~105 ha parcel now over cap
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese al cap_excedido — el cap no corto antes")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "cap_excedido"
    assert body["cap"] == "area_ha"


# ── R4-001 — a DB fault in the parcela resolver is a coded 503, never a 500 ───


class _FakeOrig(Exception):
    """Stand-in for the psycopg2 error under ``OperationalError.orig``."""

    def __init__(self, pgcode: str | None) -> None:
        super().__init__("simulated db fault")
        self.pgcode = pgcode


def test_parcela_db_timeout_es_503_analisis_timeout(ficha_db, monkeypatch, tmp_path):
    """A statement_timeout (57014) resolving the parcela → 503 ``analisis_timeout``.

    ``parcela`` and ``poligono`` share the compute tail, but each has its OWN
    resolver query; this pins the mapping for the parcela resolver too, proving the
    R4-001 gap is closed for BOTH tipos and never escapes as a 500 ``INTERNAL_ERROR``.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)

    # "parcelas_catastro" is unique to the parcela resolver query. Applied after
    # seeding so the INSERTs run for real; 57014 = statement_timeout / QueryCanceled.
    real_execute = ficha_db.execute

    def _fake(statement, *args, **kwargs):  # noqa: ANN001, ANN202
        if "parcelas_catastro" in str(statement):
            raise OperationalError("stmt", {}, _FakeOrig("57014"))
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(ficha_db, "execute", _fake)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})

    assert rs.status_code == 503, rs.text
    body = rs.json()
    assert body["codigo"] == "analisis_timeout"
    assert body["codigo"] != "INTERNAL_ERROR"
    assert "error" not in body  # flat FichaError body, not the nested 500 shape
