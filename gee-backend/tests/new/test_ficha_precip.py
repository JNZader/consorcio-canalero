"""Real-compute integration tests for monthly precipitation in the ficha (PR B2.1/B2.3).

`spec precip-normals-pipeline` › "Monthly series for a zone" + "Zone outside
precipitation coverage". The precipitation dataset is assembled in the shared
compute tail (``_ficha_de_geometria``) from the registered CHIRPS normals through
the SAME ``extract_zonal_profile`` primitive the flood/drainage rasters use.

Same harness as ``test_ficha_compute``: PURELY BEHAVIORAL (TestClient), real PG,
GEE/rasters mocked as small constant-value GeoTIFFs on disk. The precip layers are
registered as ``geo_layers`` rows carrying ``metadata_extra={"mes": …, "version":
…}`` and ``area_id`` — exactly what the B1b month-scoped lookup keys on.

Key regression (JDB-017): a parcel is ALWAYS sub-pixel against a ~5 km CHIRPS
normal, but precip passes ``K = 0`` so ``low_confidence`` stays False. The same
coarse raster flags ``low_confidence: true`` for flood_risk (K = 10) in
``test_ficha_compute``; here it must NOT.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import event, text
from sqlalchemy.orm import Session

# ``parcelas_catastro`` lives in the intelligence models module (same conftest
# trap documented in ``test_ficha_compute``): import it so ``create_all`` builds it.
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

FICHA_PATH = "/api/v2/geo/analisis-zona"

# ── the parcel and its world, in EPSG:4326 (mirror test_ficha_compute) ───────
LON0, LAT0, D = -62.0, -32.0, 0.01  # ~105 ha near the consorcio (UTM 20S)
NOMENCLATURA = "19-04-12-0001-1"
NODATA = -9999.0
AREA_ID = "consorcio"  # matches settings.ficha_precip_area_id default
VERSION = "2026-01-01T00:00:00+00:00"

_PARCELA_WKT = (
    f"POLYGON(({LON0} {LAT0}, {LON0 + D} {LAT0}, {LON0 + D} {LAT0 + D}, "
    f"{LON0} {LAT0 + D}, {LON0} {LAT0}))"
)


def _multipoly(x0: float, x1: float) -> str:
    return (
        f"MULTIPOLYGON((({x0} {LAT0}, {x1} {LAT0}, {x1} {LAT0 + D}, {x0} {LAT0 + D}, {x0} {LAT0})))"
    )


_SUELOS = (
    ("IVws", _multipoly(LON0, LON0 + 0.004)),
    ("IVsc", _multipoly(LON0 + 0.004, LON0 + 0.005)),
    (None, _multipoly(LON0 + 0.005, LON0 + 0.008)),
)


@pytest.fixture
def ficha_db(test_engine) -> Session:
    """Savepoint-scoped session so the endpoint's mid-request COMMIT cannot leak."""
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


def _seed_parcela(db: Session) -> None:
    db.execute(
        text(
            "INSERT INTO parcelas_catastro (nomenclatura, geometria, nro_cuenta) "
            "VALUES (:nom, ST_GeomFromText(:wkt, 4326), :cta)"
        ),
        {"nom": NOMENCLATURA, "wkt": _PARCELA_WKT, "cta": "12345"},
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
) -> str:
    """Write a constant-value EPSG:4326 GeoTIFF (nodata = -9999)."""
    data = np.full((npix, npix), value, dtype="float32")
    path = tmp_path / name
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=npix,
        width=npix,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(west, north, pixel, pixel),
        nodata=NODATA,
    ) as dst:
        dst.write(data, 1)
    return str(path)


def _raster_fino(tmp_path: Any, name: str, value: float) -> str:
    """A fine raster fully covering the parcel (16×16 of 0.001°)."""
    return _raster(
        tmp_path, name, value, west=LON0 - 0.003, north=LAT0 + D + 0.003, pixel=0.001, npix=16
    )


def _raster_grueso(tmp_path: Any, name: str, value: float) -> str:
    """A COARSE raster fully covering the parcel (4×4 of 0.005° ≈ 26 ha/pixel).

    The parcel is only ~2 pixels wide here — the exact geometry that flags
    ``low_confidence: true`` for flood_risk (K = 10) in ``test_ficha_compute``.
    """
    return _raster(
        tmp_path, name, value, west=LON0 - 0.005, north=LAT0 + D + 0.005, pixel=0.005, npix=4
    )


def _registrar_precip(
    db: Session, mes: Any, path: str, *, version: str = VERSION, area_id: str = AREA_ID
) -> None:
    db.add(
        GeoLayer(
            nombre=f"precip_normal_{mes}_{version}",
            tipo=TipoGeoLayer.PRECIP_NORMAL,
            fuente=FuenteGeoLayer.MANUAL,
            archivo_path=path,
            formato=FormatoGeoLayer.GEOTIFF,
            srid=4326,
            metadata_extra={
                "mes": mes,
                "version": version,
                "normal_period": "1991-2020",
                "fuente": "CHIRPS",
                "resolucion_m": 5000,
            },
            area_id=area_id,
        )
    )
    db.flush()


def _post(db: Session) -> Any:
    from fastapi.testclient import TestClient

    with TestClient(_app(db)) as cliente:
        return cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOMENCLATURA})


# ── B2.3 — serie is always 12 entries in CALENDAR order when covered ─────────


def test_precip_serie_12_meses_en_orden_calendario(ficha_db, monkeypatch, tmp_path):
    """12 registered monthly normals fully covering the parcel → 12 mm values, Jan..Dec."""
    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    for mes in range(1, 13):
        _registrar_precip(
            ficha_db, mes, _raster_fino(tmp_path, f"precip_{mes:02d}.tif", float(mes * 10))
        )
    _registrar_precip(ficha_db, "anual", _raster_fino(tmp_path, "precip_anual.tif", 1234.0))

    rs = _post(ficha_db)

    assert rs.status_code == 200, rs.text
    precip = rs.json()["precipitacion_mensual"]
    assert precip["cobertura"] == "total"
    assert precip["unidad"] == "mm"
    # exactly 12 entries, in calendar order 1..12
    assert [e["mes"] for e in precip["serie"]] == list(range(1, 13))
    # each mm is the raster mean for that month (value = mes * 10)
    for e in precip["serie"]:
        assert e["mm"] == pytest.approx(e["mes"] * 10.0, abs=0.5)
    assert precip["anual_mm"] == pytest.approx(1234.0, abs=0.5)


# ── B2.3 — no fabricated zeros outside coverage ──────────────────────────────


def test_precip_zona_fuera_de_cobertura_sin_cobertura_sin_ceros(ficha_db, monkeypatch, tmp_path):
    """12 normals registered but DISJOINT from the parcel → sin_cobertura, empty serie.

    The spec forbids inventing ``mm: 0`` for months whose raster does not overlap
    the zone (`precip-normals-pipeline` › "Zone outside precipitation coverage").
    """
    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    # rasters far away (over the Atlantic) → non-overlap → coverage "none" per month.
    for mes in range(1, 13):
        _registrar_precip(
            ficha_db,
            mes,
            _raster(
                tmp_path,
                f"precip_{mes:02d}.tif",
                float(mes * 10),
                west=-50.0,
                north=-20.0,
                pixel=0.001,
                npix=8,
            ),
        )

    rs = _post(ficha_db)

    assert rs.status_code == 200, rs.text
    precip = rs.json()["precipitacion_mensual"]
    assert precip["cobertura"] == "sin_cobertura"
    assert precip["serie"] == []  # NOT twelve mm:0 rows
    assert precip["anual_mm"] is None


# ── B2.3 — the JDB-017 K=0 override: a sub-pixel parcel is NOT low_confidence ─


def test_precip_parcela_subpixel_no_es_low_confidence(ficha_db, monkeypatch, tmp_path):
    """COARSE normals fully covering a sub-pixel parcel → low_confidence False (K=0).

    THIS is the JDB-017 regression: the identical coarse raster flags
    ``low_confidence: true`` for flood_risk (K = 10, see
    ``test_ficha_compute.test_parcela_chica_es_low_confidence``). Precip passes
    ``K = 0`` so it must stay False — a smooth interpolated normal sampled
    sub-pixel is exact, not approximate.
    """
    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    for mes in range(1, 13):
        _registrar_precip(
            ficha_db, mes, _raster_grueso(tmp_path, f"precip_{mes:02d}.tif", float(mes * 10))
        )
    _registrar_precip(ficha_db, "anual", _raster_grueso(tmp_path, "precip_anual.tif", 1234.0))

    rs = _post(ficha_db)

    assert rs.status_code == 200, rs.text
    precip = rs.json()["precipitacion_mensual"]
    assert precip["cobertura"] == "total"
    assert len(precip["serie"]) == 12
    # the load-bearing assertion — K=0 never flags, even on a sub-pixel parcel.
    assert precip["low_confidence"] is False


# ── B2.1 — zero months registered → SOFT degrade to sin_cobertura ────────────


def test_precip_cero_meses_registrados_es_sin_cobertura(ficha_db, monkeypatch, tmp_path):
    """No precip normals at all → 200 with precip ``sin_cobertura``, ficha still served.

    SOFT degradation: precipitation is informational, so a missing CHIRPS product
    must NOT 503 the whole ficha (unlike suelos, which is structural). suelos IS
    loaded, so the ficha resolves and only the precip block reports no coverage.
    """
    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    # no _registrar_precip(...) at all

    rs = _post(ficha_db)

    assert rs.status_code == 200, rs.text
    precip = rs.json()["precipitacion_mensual"]
    assert precip["cobertura"] == "sin_cobertura"
    assert precip["serie"] == []


# ── B2.1 — an INCOMPLETE product (some months missing) → sin_cobertura ────────


def test_precip_meses_faltantes_es_sin_cobertura(ficha_db, monkeypatch, tmp_path):
    """Only 11 of 12 months registered → sin_cobertura for the whole dataset.

    A partial year is not published as authoritative and the missing month is NOT
    fabricated as ``mm: 0`` (design §4).
    """
    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    for mes in range(1, 13):
        if mes == 6:
            continue  # June missing → incomplete product
        _registrar_precip(
            ficha_db, mes, _raster_fino(tmp_path, f"precip_{mes:02d}.tif", float(mes * 10))
        )

    rs = _post(ficha_db)

    assert rs.status_code == 200, rs.text
    precip = rs.json()["precipitacion_mensual"]
    assert precip["cobertura"] == "sin_cobertura"
    assert precip["serie"] == []


# ── B2.1 — area_id isolation: normals of another area are not read ───────────


def test_precip_solo_lee_su_area_id(ficha_db, monkeypatch, tmp_path):
    """Normals registered under a DIFFERENT area_id are invisible → sin_cobertura.

    The month-scoped lookup filters ``area_id = settings.ficha_precip_area_id``;
    a foreign deployment's rasters must never leak into this consorcio's ficha. With
    soft degradation the isolation shows up as this consorcio seeing zero months
    (200 sin_cobertura), never as reading another area's rasters.
    """
    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)
    for mes in range(1, 13):
        _registrar_precip(
            ficha_db,
            mes,
            _raster_fino(tmp_path, f"precip_{mes:02d}.tif", float(mes * 10)),
            area_id="otro_consorcio",
        )

    rs = _post(ficha_db)

    assert rs.status_code == 200, rs.text
    precip = rs.json()["precipitacion_mensual"]
    assert precip["cobertura"] == "sin_cobertura"
    assert precip["serie"] == []
