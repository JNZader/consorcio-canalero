"""On-map overlay endpoint tests — A(b) slice 1 (soils only).

``POST /api/v2/geo/analisis-zona/overlay`` returns the analysis CLIPPED to the
analyzed zone as a GeoJSON FeatureCollection so the map can paint it. Slice 1 is
soils only (the exact PostGIS vector path); flood_risk/drainage_need raster
vectorization is slice 2.

Same test conventions as ``test_ficha_compute`` (real PG, restarting-SAVEPOINT
isolation because the endpoint COMMITs its audit row mid-request, purely
behavioral through ``TestClient`` — never a route-table walk, flag flipped ON via
monkeypatch). The overlay never touches the precip product, so — unlike the ficha
compute tests — no CHIRPS normals need to be registered here.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

# ``parcelas_catastro`` lives in the intelligence models module; import it so the
# session-scoped ``create_all`` builds the table when this file runs on its own.
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401

OVERLAY_PATH = "/api/v2/geo/analisis-zona/overlay"

# The parcel and its soils, in EPSG:4326 — same layout as ``test_ficha_compute``.
LON0, LAT0, D = -62.0, -32.0, 0.01
NOMENCLATURA = "19-04-12-0001-1"

_PARCELA_WKT = (
    f"POLYGON(({LON0} {LAT0}, {LON0 + D} {LAT0}, {LON0 + D} {LAT0 + D}, "
    f"{LON0} {LAT0 + D}, {LON0} {LAT0}))"
)


def _multipoly(x0: float, x1: float) -> str:
    return (
        f"MULTIPOLYGON((({x0} {LAT0}, {x1} {LAT0}, {x1} {LAT0 + D}, {x0} {LAT0 + D}, {x0} {LAT0})))"
    )


# IVws (40%) | IVsc (10%) | NULL cap (30%) — normalized caps: IV, IV, "sin clasificar".
_SUELOS = (
    ("IVws", _multipoly(LON0, LON0 + 0.004)),
    ("IVsc", _multipoly(LON0 + 0.004, LON0 + 0.005)),
    (None, _multipoly(LON0 + 0.005, LON0 + 0.008)),
)


@pytest.fixture
def ficha_db(test_engine) -> Session:
    """Savepoint-scoped session: the endpoint's mid-request COMMIT cannot leak."""
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


# ── the happy path: per-class clipped features ──────────────────────────────


def test_overlay_suelos_devuelve_feature_collection_por_clase(ficha_db, monkeypatch):
    """Parcel overlay → 200 FeatureCollection; every feature carries a normalized clase."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_parcela(ficha_db)
    _seed_suelos(ficha_db)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "suelos"},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["dataset"] == "suelos"
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == len(_SUELOS)  # one feature per intersecting soil polygon

    # ``clase`` matches the ficha soils panel's normalized caps exactly (IVws → IV;
    # IVsc → IV; NULL cap → "sin clasificar"). No color on the wire — the client maps it.
    clases = {f["properties"]["clase"] for f in body["features"]}
    assert clases == {"IV", "sin clasificar"}
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert "clase" in feature["properties"]
        assert "color" not in feature["properties"]

    # Geometry is valid GeoJSON in EPSG:4326 (lon/lat within the fixture region).
    for feature in body["features"]:
        geom = feature["geometry"]
        assert geom["type"] in ("Polygon", "MultiPolygon")
        assert geom["coordinates"]
        lon, lat = _primer_vertice(geom)
        assert -63.0 <= lon <= -61.0
        assert -33.0 <= lat <= -31.0


def _primer_vertice(geom: dict[str, Any]) -> tuple[float, float]:
    coords: Any = geom["coordinates"]
    while isinstance(coords[0], list):
        coords = coords[0]
    return float(coords[0]), float(coords[1])


# ── zero coverage: no intersecting soils → empty FeatureCollection, NOT an error ─


def test_overlay_sin_suelos_es_feature_collection_vacio(ficha_db, monkeypatch):
    """A zone with no soil polygons → 200 with an EMPTY features list, never fabricated."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)  # table exists but stays EMPTY
    _seed_parcela(ficha_db)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "suelos"},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["dataset"] == "suelos"
    assert body["type"] == "FeatureCollection"
    assert body["features"] == []


# ── the feature gate: switched off → 503, before any work ───────────────────


def test_overlay_flag_off_es_503(ficha_db, monkeypatch):
    """With the ficha disabled the overlay answers 503, same gate as /analisis-zona."""
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "suelos"},
        )

    assert rs.status_code == 503, rs.text
    assert rs.json()["codigo"] == "funcionalidad_no_disponible"


# ── slice guard: a non-suelos dataset is a clean 422, not a silent empty ─────


@pytest.mark.parametrize("dataset", ["flood_risk", "drainage_need", "", None, "otro"])
def test_overlay_dataset_no_suelos_es_422(ficha_db, monkeypatch, dataset):
    """Only ``dataset="suelos"`` is served in slice 1; anything else → 422."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)

    cuerpo: dict[str, Any] = {"tipo": "parcela", "nomenclatura": NOMENCLATURA}
    if dataset is not None:
        cuerpo["dataset"] = dataset

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(OVERLAY_PATH, json=cuerpo)

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "dataset_no_soportado"
    assert body["datasets_soportados"] == ["suelos"]


# ── an unknown parcela still 404s through the overlay resolver ───────────────


def test_overlay_parcela_desconocida_es_404(ficha_db, monkeypatch):
    """The overlay reuses ``_resolver_parcela`` → an unknown nomenclatura is 404."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": "99-99-99-9999-9", "dataset": "suelos"},
        )

    assert rs.status_code == 404, rs.text
    assert rs.json()["codigo"] == "parcela_no_encontrada"


# ── caller-drawn polygon: overlay clips a poligono request too ──────────────


def test_overlay_poligono_recorta_por_clase(ficha_db, monkeypatch):
    """A ``tipo=poligono`` overlay clips the drawn geometry and colors by clase."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)

    # A polygon covering the western half of the fixture parcel → intersects the
    # IVws + IVsc soils (the NULL-cap slice starts at LON0+0.005, still partly in).
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [LON0, LAT0],
                [LON0 + 0.006, LAT0],
                [LON0 + 0.006, LAT0 + D],
                [LON0, LAT0 + D],
                [LON0, LAT0],
            ]
        ],
    }

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH, json={"tipo": "poligono", "geometry": geometry, "dataset": "suelos"}
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["features"]
    assert {f["properties"]["clase"] for f in body["features"]} <= {"IV", "sin clasificar"}
