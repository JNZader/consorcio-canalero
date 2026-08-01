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

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import shape as shapely_shape
from sqlalchemy import event, text
from sqlalchemy.orm import Session

# ``parcelas_catastro`` lives in the intelligence models module; import it so the
# session-scoped ``create_all`` builds the table when this file runs on its own.
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

OVERLAY_PATH = "/api/v2/geo/analisis-zona/overlay"

NODATA = -9999.0

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


# ── raster fixtures for the slice-2 flood_risk / drainage_need overlay ───────
# Mirror ``test_ficha_compute``'s raster seeding: a constant-value EPSG:4326
# GeoTIFF registered as a GeoLayer. A UNIFORM value lands every covered pixel in
# ONE class, so the per-class dissolve MUST collapse them to a few polygons — the
# assertion that proves ``unary_union`` runs (never one feature per pixel).


def _raster(
    tmp_path: Any,
    name: str,
    value: float,
    *,
    west: float,
    north: float,
    pixel: float,
    npix: int = 16,
    all_nodata: bool = False,
) -> str:
    fill = NODATA if all_nodata else value
    data = np.full((npix, npix), fill, dtype="float32")
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


def _raster_full(tmp_path: Any, name: str, value: float, **kw: Any) -> str:
    """A fine raster fully covering the fixture parcel (16×16 of 0.001°)."""
    return _raster(
        tmp_path, name, value, west=LON0 - 0.003, north=LAT0 + D + 0.003, pixel=0.001, npix=16, **kw
    )


# The production flood_risk / drainage_need COGs are already EPSG:32720 (UTM 20S) —
# the metric working CRS. A 32720 raster exercises the prod branch of
# ``vectorize_zonal_classes``: ``geom_crs`` (4326) != ``src_crs`` (32720) so the
# geometry is reprojected 4326→32720 onto the raster grid, and — because the raster
# IS already ``_WORK_CRS`` — ``to_work`` is the IDENTITY hop (``src_crs == _WORK_CRS``),
# simplifying natively in 32720 before the single 32720→4326 reproject. The 4326
# fixtures above never reach that identity guard; this one does.

# UTM 20S extent of the fixture parcel (LON0..LON0+D, LAT0..LAT0+D), padded to a
# whole-metre box that fully contains it — see the pyproj transform of the corners:
# easting ≈ 594457..595412, northing ≈ 6459118..6460235.
_UTM20S_WEST = 594400.0  # metres, easting of the raster's NW corner
_UTM20S_NORTH = 6460400.0  # metres, northing of the raster's NW corner


def _raster_32720(
    tmp_path: Any,
    name: str,
    value: float,
    *,
    pixel: float = 100.0,
    npix: int = 16,
    all_nodata: bool = False,
) -> str:
    """A constant-value EPSG:32720 GeoTIFF fully covering the fixture parcel.

    Mirrors ``_raster`` but writes the PRODUCTION CRS: a 16×100 m grid from the
    padded UTM 20S box covers ~1.6 km², enclosing the ~955×1108 m parcel footprint.
    """
    fill = NODATA if all_nodata else value
    data = np.full((npix, npix), fill, dtype="float32")
    path = tmp_path / name
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=npix,
        width=npix,
        count=1,
        dtype="float32",
        crs="EPSG:32720",
        transform=from_origin(_UTM20S_WEST, _UTM20S_NORTH, pixel, pixel),
        nodata=NODATA,
    ) as dst:
        dst.write(data, 1)
    return str(path)


def _registrar(db: Session, tipo: TipoGeoLayer, path: str, *, srid: int = 4326) -> None:
    db.add(
        GeoLayer(
            nombre=f"test-{tipo.value}",
            tipo=tipo,
            fuente=FuenteGeoLayer.MANUAL,
            archivo_path=path,
            formato=FormatoGeoLayer.GEOTIFF,
            srid=srid,
        )
    )
    db.flush()


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


@pytest.mark.parametrize("dataset", ["", None, "otro", "twi", "precipitacion"])
def test_overlay_dataset_desconocido_es_422(ficha_db, monkeypatch, dataset):
    """``suelos`` / ``flood_risk`` / ``drainage_need`` are served; anything else → 422."""
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
    assert body["datasets_soportados"] == ["suelos", "flood_risk", "drainage_need"]


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


# ── slice 2: flood_risk / drainage_need raster vectorization ─────────────────


def _assert_geom_valido_4326(geom: dict[str, Any]) -> None:
    assert geom["type"] in ("Polygon", "MultiPolygon")
    assert geom["coordinates"]
    forma = shapely_shape(geom)
    assert forma.is_valid, "la geometria vectorizada no es valida (auto-interseccion)"
    lon, lat = _primer_vertice(geom)
    assert -63.0 <= lon <= -61.0
    assert -33.0 <= lat <= -31.0


def test_overlay_flood_risk_vectoriza_por_clase(ficha_db, monkeypatch, tmp_path):
    """A uniform flood raster over the parcel → per-class Features; dissolve = FEW polygons."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_parcela(ficha_db)
    # value 40 → flood_risk bin "Medio" (30..55) for every covered pixel.
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, _raster_full(tmp_path, "flood.tif", 40.0))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "flood_risk"},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["dataset"] == "flood_risk"
    assert body["type"] == "FeatureCollection"
    assert body["features"], "un raster que cubre la parcela debe producir features"

    # clase == RANGE_CONFIGS["flood_risk"] label, i.e. the panel's RiesgoBins class.
    clases = {f["properties"]["clase"] for f in body["features"]}
    assert clases == {"Medio"}
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert "color" not in feature["properties"]
        _assert_geom_valido_4326(feature["geometry"])

    # DISSOLVE proof: a uniform 16×16 (=256 pixels) raster of ONE class must collapse
    # to a handful of polygons, NOT one feature per pixel. One connected class region
    # dissolves to a single polygon here.
    assert len(body["features"]) <= 3, f"dissolve no colapso los pixeles: {len(body['features'])}"


def test_overlay_drainage_need_vectoriza_por_clase(ficha_db, monkeypatch, tmp_path):
    """The drainage_need dataset vectorizes the same way, with its own class labels."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_parcela(ficha_db)
    # value 60 → drainage_need bin "Alto" (50..70).
    _registrar(ficha_db, TipoGeoLayer.DRAINAGE_NEED, _raster_full(tmp_path, "drain.tif", 60.0))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "drainage_need"},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["dataset"] == "drainage_need"
    assert {f["properties"]["clase"] for f in body["features"]} == {"Alto"}
    assert len(body["features"]) <= 3
    for feature in body["features"]:
        _assert_geom_valido_4326(feature["geometry"])


def test_overlay_flood_risk_crs_32720_prod_path(ficha_db, monkeypatch, tmp_path):
    """PROD CRS path: a flood raster in EPSG:32720 (as the real COGs) vectorizes to 4326.

    The 4326 fixtures above exercise the reproject branch (4326→32720→simplify→4326);
    the production COGs are ALREADY 32720, which runs the ``src_crs == _WORK_CRS``
    IDENTITY guard + native-32720 ``.simplify``. This is the branch that ships to prod
    and no other overlay test covers it. We seed a 32720 raster whose UTM 20S footprint
    encloses the fixture parcel, then assert the endpoint reprojects it back to 4326.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_parcela(ficha_db)
    # value 40 → flood_risk bin "Medio" (30..55), same class the 4326 test seeds.
    ruta = _raster_32720(tmp_path, "flood_32720.tif", 40.0)

    # The fixture MUST be in the production CRS, or this test silently degrades into a
    # duplicate of the 4326 path and never touches the identity guard.
    with rasterio.open(ruta) as src:
        assert src.crs.to_epsg() == 32720, "the prod-path fixture must be EPSG:32720"

    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, ruta, srid=32720)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "flood_risk"},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["dataset"] == "flood_risk"
    assert body["type"] == "FeatureCollection"
    assert body["features"], "a 32720 raster covering the parcel must produce features"

    # Same clase as the 4326 path: value 40 → "Medio". The class label is CRS-agnostic;
    # what changes is that the pixels were classified/simplified natively in 32720.
    clases = {f["properties"]["clase"] for f in body["features"]}
    assert clases == {"Medio"}

    # The 32720→4326 reproject ran: geometry is valid GeoJSON with lon/lat DEGREE
    # coordinates over the fixture region (NOT raw UTM metres in the 10^5..10^6 range).
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert "color" not in feature["properties"]
        _assert_geom_valido_4326(feature["geometry"])

    # DISSOLVE still collapses: one uniform class over the parcel → a handful of
    # polygons, never one feature per 32720 pixel.
    assert len(body["features"]) <= 3, f"dissolve no colapso los pixeles: {len(body['features'])}"


def test_overlay_raster_no_registrado_es_feature_collection_vacio(ficha_db, monkeypatch, tmp_path):
    """No flood raster registered → sin_cobertura, i.e. an EMPTY FeatureCollection 200."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_parcela(ficha_db)
    # No _registrar(...) → flood_risk is unregistered → empty, never fabricated.

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "flood_risk"},
        )

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["dataset"] == "flood_risk"
    assert body["features"] == []


def test_overlay_raster_disjunto_es_feature_collection_vacio(ficha_db, monkeypatch, tmp_path):
    """A raster whose extent does not overlap the parcel → empty FeatureCollection, 200."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_parcela(ficha_db)
    _registrar(
        ficha_db,
        TipoGeoLayer.FLOOD_RISK,
        _raster(tmp_path, "flood.tif", 40.0, west=-50.0, north=-20.0, pixel=0.001, npix=8),
    )

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "flood_risk"},
        )

    assert rs.status_code == 200, rs.text
    assert rs.json()["features"] == []


def test_overlay_raster_todo_nodata_es_feature_collection_vacio(ficha_db, monkeypatch, tmp_path):
    """A raster overlapping the parcel but all-nodata → empty, never a fabricated class."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_parcela(ficha_db)
    _registrar(
        ficha_db,
        TipoGeoLayer.FLOOD_RISK,
        _raster_full(tmp_path, "flood.tif", 40.0, all_nodata=True),
    )

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "flood_risk"},
        )

    assert rs.status_code == 200, rs.text
    assert rs.json()["features"] == []


def test_overlay_raster_ilegible_es_503(ficha_db, monkeypatch, tmp_path):
    """A registered file that is not a valid GeoTIFF → 503 raster_ilegible (§2.6)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_parcela(ficha_db)
    corrupto = tmp_path / "corrupto.tif"
    corrupto.write_bytes(b"esto no es un geotiff\x00\x01\x02")
    _registrar(ficha_db, TipoGeoLayer.FLOOD_RISK, str(corrupto))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOMENCLATURA, "dataset": "flood_risk"},
        )

    assert rs.status_code == 503, rs.text
    body = rs.json()
    assert body["codigo"] == "raster_ilegible"
    assert body["dataset"] == "flood_risk"
