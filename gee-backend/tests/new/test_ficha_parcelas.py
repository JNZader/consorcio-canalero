"""Multi-parcel selection for the ficha territorial — ``tipo=parcelas`` (T4).

The user ctrl-clicks several catastro parcels and the ficha analyzes their
UNION. The wire carries only the nomenclaturas: the map selects from VECTOR
TILES, whose geometries are clipped/simplified per tile, so the union is rebuilt
SERVER-SIDE from ``parcelas_catastro`` — the same table the single-parcel
resolver reads.

Same conventions as ``test_ficha_compute``: real PostgreSQL, restarting-SAVEPOINT
isolation (the endpoint COMMITs its audit row mid-request), purely behavioral
through ``TestClient`` on a locally built app — never ``app.main``, never a
route-table walk — and the feature flag flipped ON via monkeypatch.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import event, text
from sqlalchemy.orm import Session

# ``parcelas_catastro`` lives in the intelligence models module; import it so the
# session-scoped ``create_all`` builds the table when this file runs on its own.
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

FICHA_PATH = "/api/v2/geo/analisis-zona"
OVERLAY_PATH = "/api/v2/geo/analisis-zona/overlay"

NODATA = -9999.0

# Three parcels in one latitude band, EPSG:4326. A and B are ADJACENT (they share
# the lon = LON0 + D edge) so their union area is exactly the sum; C OVERLAPS the
# right half of A, so a union that double-counted would be visible as extra area.
LON0, LAT0, D = -62.0, -32.0, 0.01
NOM_A = "19-04-12-0001-1"
NOM_B = "19-04-12-0002-2"
NOM_C = "19-04-12-0003-3"
NOM_AUSENTE = "99-99-99-9999-9"


def _wkt(x0: float, x1: float) -> str:
    return f"POLYGON(({x0} {LAT0}, {x1} {LAT0}, {x1} {LAT0 + D}, {x0} {LAT0 + D}, {x0} {LAT0}))"


def _multipoly(x0: float, x1: float) -> str:
    return (
        f"MULTIPOLYGON((({x0} {LAT0}, {x1} {LAT0}, {x1} {LAT0 + D}, {x0} {LAT0 + D}, {x0} {LAT0})))"
    )


_PARCELAS = {
    NOM_A: _wkt(LON0, LON0 + D),
    NOM_B: _wkt(LON0 + D, LON0 + 2 * D),
    NOM_C: _wkt(LON0 + D / 2, LON0 + 3 * D / 2),
}

# One soil polygon spanning the whole two-parcel strip, so the union always has
# soils coverage (``suelos_catastro`` empty is a hard 503 by design).
_SUELOS = (("IVws", _multipoly(LON0 - D, LON0 + 3 * D)),)


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


@pytest.fixture(autouse=True)
def _precip_normals(ficha_db, tmp_path):
    """A full set of CHIRPS monthly normals covering the fixture region.

    Precipitation is assembled on every 200 (B2), so without the 12 months + the
    annual raster registered the ficha would answer ``sin_cobertura`` noise here
    instead of exercising the union. Error-path tests short-circuit before this
    matters, so the extra rows are harmless to them.
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


def _seed_parcelas(db: Session, *nomenclaturas: str) -> None:
    for nomenclatura in nomenclaturas:
        db.execute(
            text(
                "INSERT INTO parcelas_catastro (nomenclatura, geometria, nro_cuenta) "
                "VALUES (:nom, ST_GeomFromText(:wkt, 4326), :cta)"
            ),
            {"nom": nomenclatura, "wkt": _PARCELAS[nomenclatura], "cta": "12345"},
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


def _area_ha(db: Session, nomenclatura: str) -> float:
    return float(
        db.execute(
            text(
                "SELECT ST_Area(ST_Transform(geometria, 32720)) / 10000.0 "
                "FROM parcelas_catastro WHERE nomenclatura = :n"
            ),
            {"n": nomenclatura},
        ).scalar_one()
    )


def _seed_base(db: Session, *nomenclaturas: str) -> None:
    _crear_tabla_suelos(db)
    _seed_parcelas(db, *nomenclaturas)
    _seed_suelos(db)


# ── the union is real: adjacent parcels sum, overlapping ones do not ─────────


def test_union_de_dos_parcelas_adyacentes_suma_las_areas(ficha_db, monkeypatch):
    """Two adjacent parcels → 200 whose ``area_ha`` is the SUM of both."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_B)
    esperado = _area_ha(ficha_db, NOM_A) + _area_ha(ficha_db, NOM_B)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B]})

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["tipo"] == "parcelas"
    assert esperado > 100.0  # the two ~105 ha parcels, not a degree-area artifact
    assert body["area_ha"] == pytest.approx(esperado, rel=1e-6)
    # Byte-compatible with a single-parcel ficha: same dataset keys, no identity.
    assert set(body) >= {"suelos", "flood_risk", "drainage_need", "precipitacion_mensual"}
    assert "nro_cuenta" not in body
    assert "nomenclaturas" not in body


def test_union_de_parcelas_superpuestas_no_duplica_area(ficha_db, monkeypatch):
    """C overlaps half of A → the union is 1.5 parcels, not 2 (``ST_Union`` dissolves)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_C)
    area_a = _area_ha(ficha_db, NOM_A)
    area_c = _area_ha(ficha_db, NOM_C)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_C]})

    assert rs.status_code == 200, rs.text
    area = rs.json()["area_ha"]
    # C is shifted by half a parcel, so the union covers 1.5 parcel widths.
    assert area == pytest.approx(1.5 * area_a, rel=1e-3)
    assert area < area_a + area_c - 1.0, "el area sumo la superposicion dos veces"


def test_orden_de_la_seleccion_no_cambia_el_resultado(ficha_db, monkeypatch):
    """The union is a SET operation: [A,B] and [B,A] answer the same area."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_B)

    with TestClient(_app(ficha_db)) as cliente:
        directo = cliente.post(
            FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B]}
        )
        inverso = cliente.post(
            FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_B, NOM_A]}
        )

    assert directo.status_code == 200, directo.text
    assert inverso.status_code == 200, inverso.text
    assert directo.json()["area_ha"] == pytest.approx(inverso.json()["area_ha"], rel=1e-9)


# ── all-or-nothing: a missing parcel is a 404 that NAMES it ──────────────────


def test_parcela_faltante_es_404_que_la_nombra(ficha_db, monkeypatch):
    """One unknown nomenclatura → 404, never a silent partial analysis."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_B)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_AUSENTE]}
        )

    assert rs.status_code == 404, rs.text
    body = rs.json()
    # SAME codigo as the single-parcel 404 so the UI keeps one branch.
    assert body["codigo"] == "parcela_no_encontrada"
    assert body["nomenclaturas"] == [NOM_AUSENTE]
    assert NOM_AUSENTE in body["detail"]


def test_todas_las_parcelas_faltantes_se_listan(ficha_db, monkeypatch):
    """Two unknown nomenclaturas → both are named, not just the first."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_AUSENTE, NOM_B]},
        )

    assert rs.status_code == 404, rs.text
    assert rs.json()["nomenclaturas"] == [NOM_AUSENTE, NOM_B]


# ── caps run over the UNION, before any raster is opened ─────────────────────


def test_union_sobre_el_cap_de_area_es_422_sin_abrir_rasters(ficha_db, monkeypatch):
    """A union over ``ficha_max_area_ha`` → 422 cap_excedido, no raster touched.

    Individually each parcel may be legal; the AREA THAT COSTS is the union, so
    the cap has to measure it — that is the whole reason the multi path re-runs
    ``assert_within_caps`` instead of trusting the per-parcel checks.
    """
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_B)
    area_a = _area_ha(ficha_db, NOM_A)
    # Between one parcel and two: each parcel passes alone, the union does not.
    monkeypatch.setattr(settings, "ficha_max_area_ha", area_a * 1.5)

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese al cap_excedido")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B]})

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "cap_excedido"
    assert body["cap"] == "area_ha"


# ── request-shape guards (schema, before any DB work) ───────────────────────


def test_nomenclatura_repetida_es_422(ficha_db, monkeypatch):
    """A duplicate is REJECTED, not silently deduped (documented decision)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_B)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B, NOM_A]}
        )

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "geometria_invalida"
    assert NOM_A in body["motivo"]


def test_una_sola_parcela_es_422(ficha_db, monkeypatch):
    """One parcel is ``tipo=parcela``; the multi shape refuses to duplicate it."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A]})

    assert rs.status_code == 422, rs.text
    assert rs.json()["codigo"] == "geometria_invalida"


def test_seleccion_sobre_el_maximo_es_422(ficha_db, monkeypatch):
    """More than ``FICHA_PARCELAS_MAX`` entries → 422 before any lookup runs."""
    from fastapi.testclient import TestClient

    from app.domains.geo.schemas_ficha import FICHA_PARCELAS_MAX

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A)
    demasiadas = [f"19-04-12-{i:04d}-0" for i in range(FICHA_PARCELAS_MAX + 1)]

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": demasiadas})

    assert rs.status_code == 422, rs.text
    assert rs.json()["codigo"] == "geometria_invalida"


def test_nomenclatura_vacia_es_422(ficha_db, monkeypatch):
    """A blank entry cannot smuggle an empty lookup into the selection."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, "   "]})

    assert rs.status_code == 422, rs.text
    assert rs.json()["codigo"] == "geometria_invalida"


# ── overlay clips to the SAME union ─────────────────────────────────────────


def test_overlay_recorta_a_la_union(ficha_db, monkeypatch):
    """The soils overlay of a multi selection covers the whole union, not one parcel."""
    from fastapi.testclient import TestClient
    from shapely.geometry import shape as shapely_shape

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_B)

    with TestClient(_app(ficha_db)) as cliente:
        una = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcela", "nomenclatura": NOM_A, "dataset": "suelos"},
        )
        dos = cliente.post(
            OVERLAY_PATH,
            json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B], "dataset": "suelos"},
        )

    assert una.status_code == 200, una.text
    assert dos.status_code == 200, dos.text
    assert dos.json()["type"] == "FeatureCollection"
    assert dos.json()["features"], "el overlay de la union quedo vacio"

    area_una = sum(shapely_shape(f["geometry"]).area for f in una.json()["features"])
    area_dos = sum(shapely_shape(f["geometry"]).area for f in dos.json()["features"])
    # The soil layer spans both parcels, so the two-parcel clip is ~twice the one-parcel clip.
    assert area_dos == pytest.approx(2 * area_una, rel=1e-3)


# ── degenerate geometry: every parcel resolves, the union does not ───────────


def _seed_parcela_wkt(db: Session, nomenclatura: str, wkt: str) -> None:
    """Seed one parcel with an ARBITRARY ring (the shared fixtures are all valid)."""
    db.execute(
        text(
            "INSERT INTO parcelas_catastro (nomenclatura, geometria, nro_cuenta) "
            "VALUES (:nom, ST_GeomFromText(:wkt, 4326), :cta)"
        ),
        {"nom": nomenclatura, "wkt": wkt, "cta": "12345"},
    )


# Two ZERO-AREA rings: closed and syntactically valid polygons whose interior is a
# line. ``ST_MakeValid`` repairs them into linear geometry and
# ``ST_CollectionExtract(..., 3)`` then keeps NOTHING, so the union of parcels that
# all exist has no polygonal component.
_DEGENERADA_1 = f"POLYGON(({LON0} {LAT0}, {LON0 + D} {LAT0}, {LON0} {LAT0}, {LON0} {LAT0}))"
_DEGENERADA_2 = (
    f"POLYGON(({LON0} {LAT0 + D}, {LON0 + D} {LAT0 + D}, {LON0} {LAT0 + D}, {LON0} {LAT0 + D}))"
)


def test_union_degenerada_es_422_no_500(ficha_db, monkeypatch):
    """Parcels that exist but collapse under ``ST_MakeValid`` → 422, never a 500.

    This is the branch between "a parcel is missing" (404) and "the union is
    usable" (200): every nomenclatura resolves, so the 404 does not fire, and the
    repaired union has no polygonal component, so the raster tail would be fed an
    EMPTY geometry. Without the explicit guard that is a 500 + a Sentry event for
    what is really bad source data.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _seed_parcela_wkt(ficha_db, NOM_A, _DEGENERADA_1)
    _seed_parcela_wkt(ficha_db, NOM_B, _DEGENERADA_2)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B]})

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "geometria_invalida"
    # NOT the 404: the parcels are there, the geometry is what is unusable.
    assert "nomenclaturas" not in body


def test_union_degenerada_no_abre_rasters(ficha_db, monkeypatch):
    """The degenerate union is rejected BEFORE any raster IO, like the caps are."""
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _seed_parcela_wkt(ficha_db, NOM_A, _DEGENERADA_1)
    _seed_parcela_wkt(ficha_db, NOM_B, _DEGENERADA_2)

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese a la union degenerada")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B]})

    assert rs.status_code == 422, rs.text


# ── the vertex cap is the ceiling a REAL selection hits first ────────────────


def _anillo_denso(x0: float, y0: float, lado: float, vertices: int) -> str:
    """A closed square-ish ring densified to ``vertices`` points.

    Small on purpose: the point is to exceed ``ficha_max_vertices`` while staying
    far below the area/envelope caps, which is exactly the shape of the problem —
    rural catastro parcels are vertex-dense long before they are large.
    """
    pasos = max(vertices - 1, 3)
    puntos = []
    for i in range(pasos):
        t = i / pasos
        # Walk the perimeter of the square once.
        if t < 0.25:
            x, y = x0 + lado * (t / 0.25), y0
        elif t < 0.5:
            x, y = x0 + lado, y0 + lado * ((t - 0.25) / 0.25)
        elif t < 0.75:
            x, y = x0 + lado * (1 - (t - 0.5) / 0.25), y0 + lado
        else:
            x, y = x0, y0 + lado * (1 - (t - 0.75) / 0.25)
        puntos.append(f"{x:.9f} {y:.9f}")
    puntos.append(puntos[0])
    return f"POLYGON(({', '.join(puntos)}))"


def test_union_sobre_el_cap_de_vertices_es_422_accionable(ficha_db, monkeypatch):
    """Two vertex-dense parcels → 422 ``cap_excedido`` with ``cap=vertices``.

    ``FICHA_PARCELAS_MAX`` (30) is NOT what stops a big selection: the union's
    vertex count is, and two realistic parcels already carry enough detail to
    reach it. The frontend mirrors both numbers, so this test is what keeps the
    client's "deseleccioná algunas parcelas" message pointing at a real ceiling.
    """
    from fastapi.testclient import TestClient

    from app.domains.geo import ficha_service

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    # ~700 vertices each, disjoint, so the union keeps both rings: > 1 000.
    _seed_parcela_wkt(ficha_db, NOM_A, _anillo_denso(LON0, LAT0, D, 700))
    _seed_parcela_wkt(ficha_db, NOM_B, _anillo_denso(LON0 + 2 * D, LAT0, D, 700))

    def _boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("se abrio un raster pese al cap_excedido")

    monkeypatch.setattr(ficha_service, "extract_zonal_profile", _boom)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_A, NOM_B]})

    assert rs.status_code == 422, rs.text
    body = rs.json()
    assert body["codigo"] == "cap_excedido"
    # NOT area_ha: two ~1 km parcels are tiny, the DETAIL is what breaks the cap.
    assert body["cap"] == "vertices"


def test_una_parcela_densa_sola_pasa_el_cap(ficha_db, monkeypatch):
    """The same parcel analyzed ALONE is fine — the cap measures the UNION.

    Which is precisely why deselecting is the actionable advice: the user is not
    over a per-parcel limit, they are over the limit of what they combined.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _crear_tabla_suelos(ficha_db)
    _seed_suelos(ficha_db)
    _seed_parcela_wkt(ficha_db, NOM_A, _anillo_denso(LON0, LAT0, D, 700))

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": NOM_A})

    assert rs.status_code == 200, rs.text


# ── the audit reference is bounded, deterministic and order-independent ──────


def test_referencia_auditable_es_acotada_y_ordenada():
    """A 30-parcel reference stays well inside ``audit_log.resource`` (512 chars).

    Truncation would destroy the only purpose of the reference — correlating the
    rows of one selection — so a long list degrades to ``count + digest`` instead
    of being cut mid-nomenclatura.
    """
    from app.domains.geo.ficha_service import referencia_auditable
    from app.domains.geo.schemas_ficha import FICHA_PARCELAS_MAX, FichaParcelasRequest

    muchas = [f"19-04-12-{i:04d}-{i % 10}" for i in range(FICHA_PARCELAS_MAX)]
    referencia = referencia_auditable(FichaParcelasRequest(tipo="parcelas", nomenclaturas=muchas))

    assert len(referencia) < 512
    assert referencia.startswith(f"tipo=parcelas,n={FICHA_PARCELAS_MAX},")

    # Order-independent: the SAME set of parcels always yields the same reference.
    invertida = referencia_auditable(
        FichaParcelasRequest(tipo="parcelas", nomenclaturas=list(reversed(muchas)))
    )
    assert invertida == referencia


def test_referencia_auditable_corta_lista_los_nombres():
    """A short selection keeps the ids readable — the digest is only a fallback."""
    from app.domains.geo.ficha_service import referencia_auditable
    from app.domains.geo.schemas_ficha import FichaParcelasRequest

    referencia = referencia_auditable(
        FichaParcelasRequest(tipo="parcelas", nomenclaturas=[NOM_B, NOM_A])
    )
    assert referencia == f"tipo=parcelas,n=2,ref={NOM_A}+{NOM_B}"


def test_auditoria_registra_la_seleccion(ficha_db, monkeypatch):
    """A multi-parcel ficha leaves ONE audit row carrying the bounded reference."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    _seed_base(ficha_db, NOM_A, NOM_B)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "parcelas", "nomenclaturas": [NOM_B, NOM_A]})

    assert rs.status_code == 200, rs.text
    recursos = (
        ficha_db.execute(text("SELECT resource FROM audit_log WHERE action = 'zona.analisis'"))
        .scalars()
        .all()
    )
    assert f"tipo=parcelas,n=2,ref={NOM_A}+{NOM_B}" in recursos


# ── rate limiting prices the multi selection like the other heavy tipos ──────


def test_costo_de_rate_limit_de_parcelas():
    """``parcelas`` is priced with the heavy tipos, never as a single parcel click."""
    from app.domains.geo.router_ficha import COSTO_POR_TIPO

    assert COSTO_POR_TIPO["parcelas"] == COSTO_POR_TIPO["poligono"]
    assert COSTO_POR_TIPO["parcelas"] > COSTO_POR_TIPO["parcela"]
