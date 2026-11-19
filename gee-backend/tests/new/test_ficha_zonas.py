"""Real-compute integration tests for ``tipo=zonas`` + preview (informe de área PR 1).

`odd/tasks/informe-area-pr1.md` S1-S4 + S8. Covers:

* ``POST /api/v2/geo/analisis-zona/preview`` — the geometry-only Revisar step:
  union-not-sum over overlapping subcuencas (S4, tol 0,01 ha), desglose + fuera
  = total (±0,1 %), geodesic vs EPSG:32720 (<0,2 %), ``modo=trabajo`` past the
  35 000 ha zonas cap (decision L2 — NOT the 20 000 parcel default), whole-cuenca
  expansion with dedup, and the 60-zona bound at both layers (the schema cap on
  ``zona_ids`` and the RESOLVED total after cuenca expansion).
* ``POST /api/v2/geo/analisis-zona`` with ``tipo="zonas"`` — the ficha compute
  over the resolved union with ``desglose_por_subcuenca`` derived from STORED
  data only: ``composite_zonal_stats`` (``pct_alto_critico`` + the ``leyenda-55``
  threshold tag until #738 lands in PR 5), ``suelos_catastro`` (dominant class)
  and the registered CHIRPS annual normal (``lluvia_anual_mm``).
* A rough local p95 of the preview logic with 60 zonas (the L2 acceptance
  condition). The assert is deliberately loose: this box is not prod, the number
  is printed for the report.

**PURELY BEHAVIORAL (TestClient)**, never a route-table walk — same CI
module-identity pathology ``test_ficha_compute`` documents.

**Real PG + restarting savepoint.** Both endpoints COMMIT an audit row before
answering, so the ``ficha_db`` fixture joins the external transaction with a
restarting SAVEPOINT — the endpoint's ``commit`` only releases a savepoint and
the outer rollback discards every seed + audit row at teardown.

**Feature flag.** The router is gated OFF by default; every test flips
``settings.ficha_enabled`` ON via monkeypatch (S7: it stays off in production
until Javier decides).
"""

from __future__ import annotations

import statistics
import time
import uuid
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import event, text
from sqlalchemy.orm import Session

# ``zonas_operativas`` / ``composite_zonal_stats`` live in the intelligence
# models module, which conftest imports eagerly — this re-import is the belt to
# the suspenders every other ficha module wears.
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

FICHA_PATH = "/api/v2/geo/analisis-zona"
PREVIEW_PATH = "/api/v2/geo/analisis-zona/preview"

# Same world as ``test_ficha_compute``: ~105 ha per 0.01° square near the
# consorcio (UTM 20S), where the geodesic/planimetric difference is ~0.05 %.
LON0, LAT0, D = -62.0, -32.0, 0.01
NODATA = -9999.0

# A 0.2° square measures ~42 000 ha — over the 35 000 ha zonas cap and under
# the 150 000 ha envelope cap, so the AREA cap is the one that fires.
LADO_ZONA_GRANDE = 0.2


@pytest.fixture
def ficha_db(test_engine) -> Session:
    """A session whose COMMITs are savepoint-scoped, so the endpoints cannot leak."""
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

    Makes ``precipitacion_mensual`` a real dataset (B2 made it a hard dependency)
    and gives the desglose an annual raster to read ``lluvia_anual_mm`` from —
    the stored-data path S8 requires.
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


def _seed_zona(
    db: Session,
    nombre: str,
    cuenca: str,
    x0: float,
    y0: float,
    *,
    lado: float = D,
) -> uuid.UUID:
    """Insert one square ``zonas_operativas`` row; returns its id.

    The id is generated client-side: ``create_all`` builds this table from the
    ORM model (whose uuid default is client-side), so unlike the migration's
    ``gen_random_uuid()`` server default a raw INSERT must carry one.
    """
    zona_id = uuid.uuid4()
    wkt = (
        f"POLYGON(({x0} {y0}, {x0 + lado} {y0}, {x0 + lado} {y0 + lado}, "
        f"{x0} {y0 + lado}, {x0} {y0}))"
    )
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, :nombre, :cuenca, ST_GeomFromText(:wkt, 4326), 0.0)"
        ),
        {"id": zona_id, "nombre": nombre, "cuenca": cuenca, "wkt": wkt},
    )
    return zona_id


def _seed_suelo(db: Session, cap: str | None, x0: float, x1: float) -> None:
    """A soil band spanning the fixture's latitude range between lon ``x0..x1``."""
    wkt = (
        f"MULTIPOLYGON((({x0} {LAT0 - 0.01}, {x1} {LAT0 - 0.01}, "
        f"{x1} {LAT0 + 0.05}, {x0} {LAT0 + 0.05}, {x0} {LAT0 - 0.01})))"
    )
    db.execute(
        text(
            "INSERT INTO suelos_catastro (simbolo, cap, geometria) "
            "VALUES (:sim, :cap, ST_GeomFromText(:wkt, 4326))"
        ),
        {"sim": f"S-{cap or 'null'}", "cap": cap, "wkt": wkt},
    )


def _seed_composite_alto(db: Session, zona_id: uuid.UUID, area_high_risk_ha: float) -> None:
    """One stored ``composite_zonal_stats`` flood_risk row for the zone."""
    db.execute(
        text(
            "INSERT INTO composite_zonal_stats "
            "(id, zona_id, tipo, fecha_calculo, mean_score, max_score, p90_score, "
            " area_high_risk_ha) "
            "VALUES (:id, :zona_id, 'flood_risk', CURRENT_DATE, 50.0, 90.0, 70.0, :ha)"
        ),
        {"id": uuid.uuid4(), "zona_id": zona_id, "ha": area_high_risk_ha},
    )


def _raster_cobertura_total(tmp_path: Any, name: str, value: float) -> str:
    """A fine constant raster fully covering every fixture zone."""
    path = tmp_path / name
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=96,
        width=96,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON0 - 0.05, LAT0 + 0.15, 0.001, 0.001),
        nodata=NODATA,
    ) as dst:
        dst.write(np.full((96, 96), value, dtype="float32"), 1)
    return str(path)


def _registrar(db: Session, tipo: TipoGeoLayer, path: str) -> None:
    db.add(
        GeoLayer(
            nombre=f"test-{tipo.value}-{uuid.uuid4().hex[:6]}",
            tipo=tipo,
            fuente=FuenteGeoLayer.MANUAL,
            archivo_path=path,
            formato=FormatoGeoLayer.GEOTIFF,
            srid=4326,
        )
    )
    db.flush()


def _sembrar_mundo(db: Session, tmp_path: Any) -> dict[str, uuid.UUID]:
    """Two adjacent zonas of cuenca-alfa + one overlapping zona of cuenca-beta.

    Soils: ``IVws`` covers only zona A1 (dominant ``IV`` there); ``VIIe`` covers
    everything east of it (dominant ``VII`` on A2 and B1). A stored composite row
    exists for A1 ONLY (42 ha of ~105 → ~40 %), so the other two rows must report
    ``pct_alto_critico=None`` — no fabricated figures from missing stored data.
    """
    _crear_tabla_suelos(db)
    zona_a1 = _seed_zona(db, "A1", "cuenca-alfa", LON0, LAT0)
    zona_a2 = _seed_zona(db, "A2", "cuenca-alfa", LON0 + D, LAT0)
    # B1 overlaps A2 by half a square width (S4's "dos subcuencas que se pisan").
    zona_b1 = _seed_zona(db, "B1", "cuenca-beta", LON0 + D + D / 2, LAT0)
    _seed_suelo(db, "IVws", LON0, LON0 + D)
    _seed_suelo(db, "VIIe", LON0 + D, LON0 + 0.1)
    _seed_composite_alto(db, zona_a1, 42.0)
    _registrar(db, TipoGeoLayer.FLOOD_RISK, _raster_cobertura_total(tmp_path, "flood.tif", 40.0))
    _registrar(db, TipoGeoLayer.DRAINAGE_NEED, _raster_cobertura_total(tmp_path, "drain.tif", 60.0))
    db.flush()
    return {"a1": zona_a1, "a2": zona_a2, "b1": zona_b1}


def _preview(cliente: Any, zona_ids: list[uuid.UUID], cuencas: list[str] | None = None) -> Any:
    cuerpo: dict[str, Any] = {"zona_ids": [str(z) for z in zona_ids]}
    if cuencas is not None:
        cuerpo["cuencas"] = cuencas
    return cliente.post(PREVIEW_PATH, json=cuerpo)


def _union_esperada_ha(db: Session, zona_ids: list[uuid.UUID]) -> float:
    """Independent in-test measurement of the union (EPSG:32720) — not the code under test."""
    fila = db.execute(
        text(
            "SELECT ST_Area(ST_Transform(ST_Union(geometria), 32720)) / 10000.0 AS ha "
            "FROM zonas_operativas WHERE id = ANY(CAST(:ids AS uuid[]))",
        ),
        {"ids": [str(z) for z in zona_ids]},
    ).one()
    return float(fila.ha)


# ── preview: S4 measurement semantics ───────────────────────────────────────


def test_preview_dos_zonas_solapadas_dan_la_union(ficha_db, monkeypatch):
    """S4: two overlapping subcuencas answer the UNION area, not the sum (0,01 ha)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    solapada = _seed_zona(ficha_db, "solapada-1", "cuenca-x", LON0, LAT0)
    vecina = _seed_zona(ficha_db, "solapada-2", "cuenca-x", LON0 + D / 2, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [solapada, vecina])

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    esperado = _union_esperada_ha(ficha_db, [solapada, vecina])
    assert abs(cuerpo["area_total_ha"] - esperado) <= 0.01
    # the union is strictly smaller than the sum: the overlap is counted once
    suma = sum(sub["ha"] for sub in cuerpo["subcuencas"])
    assert cuerpo["area_total_ha"] < suma
    assert suma - cuerpo["area_total_ha"] == pytest.approx(esperado / 3.0, rel=0.01)
    # an overlapping selection must not report a negative "fuera" either
    assert cuerpo["fuera_de_subcuencas_ha"] == 0.0


def test_preview_desglose_mas_fuera_es_total(ficha_db, monkeypatch):
    """S4: per-zone desglose + fuera = total (±0,1 %) on a non-overlapping selection."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    zona_1 = _seed_zona(ficha_db, "adyacente-1", "cuenca-y", LON0, LAT0)
    zona_2 = _seed_zona(ficha_db, "adyacente-2", "cuenca-y", LON0 + D, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [zona_1, zona_2])

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    suma_mas_fuera = (
        sum(sub["ha"] for sub in cuerpo["subcuencas"]) + cuerpo["fuera_de_subcuencas_ha"]
    )
    assert suma_mas_fuera == pytest.approx(cuerpo["area_total_ha"], rel=0.001)
    # adjacent subcuencas tile their union exactly: nothing lies outside them
    assert cuerpo["fuera_de_subcuencas_ha"] == pytest.approx(0.0, abs=1e-3)


def test_preview_geodesica_contra_32720(ficha_db, monkeypatch):
    """S4: the geodesic reference and the EPSG:32720 area agree within 0,2 %."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    zona_1 = _seed_zona(ficha_db, "geo-1", "cuenca-z", LON0, LAT0)
    zona_2 = _seed_zona(ficha_db, "geo-2", "cuenca-z", LON0 + D / 2, LAT0 + D / 4)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [zona_1, zona_2])

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    plana, geodesica = cuerpo["area_total_ha"], cuerpo["area_total_ha_geodesica"]
    assert plana > 0
    assert abs(geodesica - plana) / plana < 0.002


def test_preview_sobre_el_cap_zonas_modo_trabajo(ficha_db, monkeypatch):
    """L2/S3: >35 000 ha answers modo=trabajo + aviso — NOT the 20 000 parcel cap.

    The fixture zone measures ~42 000 ha: past the zonas cap (35 000, decision
    L2) and past the inherited parcel cap (20 000) — the response must reflect
    the ZONAS threshold, and the preview must answer, never 422.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    grande = _seed_zona(ficha_db, "zona-gigante", "cuenca-g", LON0, LAT0, lado=LADO_ZONA_GRANDE)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [grande])

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    assert cuerpo["area_total_ha"] > 35_000.0
    assert cuerpo["modo"] == "trabajo"
    assert cuerpo["aviso_cap"] is True


def test_preview_bajo_el_cap_zonas_modo_online(ficha_db, monkeypatch):
    """The boundary is the zonas cap: ~42 000 ha is trabajo, ~105 ha is online."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    chica = _seed_zona(ficha_db, "zona-chica", "cuenca-c", LON0, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [chica])

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    assert cuerpo["modo"] == "online"
    assert cuerpo["aviso_cap"] is False


def test_preview_cuencas_expanden_y_deduplican(ficha_db, monkeypatch):
    """S8: ``cuencas`` pulls the whole watershed; an explicit id inside it is not doubled."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    a1 = _seed_zona(ficha_db, "alfa-1", "cuenca-alfa", LON0, LAT0)
    a2 = _seed_zona(ficha_db, "alfa-2", "cuenca-alfa", LON0 + D, LAT0)
    _seed_zona(ficha_db, "beta-1", "cuenca-beta", LON0 + 2 * D, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [a1], cuencas=["cuenca-alfa"])
        solo_cuenca = _preview(cliente, [], cuencas=["cuenca-alfa"])

    assert rs.status_code == 200, rs.text
    nombres = [sub["nombre"] for sub in rs.json()["subcuencas"]]
    assert nombres == ["alfa-1", "alfa-2"]  # a1 listed ONCE despite id + cuenca
    assert rs.json()["area_total_ha"] == pytest.approx(
        _union_esperada_ha(ficha_db, [a1, a2]), abs=0.01
    )
    # cuencas-only selection (empty zona_ids) is legal per the preview contract
    assert solo_cuenca.status_code == 200, solo_cuenca.text
    assert [sub["nombre"] for sub in solo_cuenca.json()["subcuencas"]] == [
        "alfa-1",
        "alfa-2",
    ]


def test_preview_zona_desconocida_404(ficha_db, monkeypatch):
    """All-or-nothing like ``tipo=parcelas``: an unknown id is a 404, never a partial."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    conocida = _seed_zona(ficha_db, "conocida", "cuenca-k", LON0, LAT0)
    fantasma = uuid.uuid4()

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [conocida, fantasma])

    assert rs.status_code == 404
    cuerpo = rs.json()
    assert cuerpo["codigo"] == "zona_no_encontrada"
    assert cuerpo["zonas"] == [str(fantasma)]


def test_preview_cuenca_sin_zonas_404(ficha_db, monkeypatch):
    """A cuenca name matching zero zonas is a 404, not a silently shrunk selection."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    conocida = _seed_zona(ficha_db, "conocida", "cuenca-k", LON0, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [conocida], cuencas=["cuenca-inexistente"])

    assert rs.status_code == 404
    cuerpo = rs.json()
    assert cuerpo["codigo"] == "cuenca_no_encontrada"
    assert cuerpo["cuenca"] == "cuenca-inexistente"


def test_preview_mas_de_60_zona_ids_422(ficha_db, monkeypatch):
    """The schema cap: 61 zona_ids never reaches the database."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    ids = [uuid.uuid4() for _ in range(61)]

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, ids)

    assert rs.status_code == 422
    assert rs.json()["codigo"] == "geometria_invalida"


def test_preview_cuencas_que_resuelven_mas_de_60_zonas_422(ficha_db, monkeypatch):
    """The RESOLVED cap: a cuenca expansion over 60 zonas is 422 ``cap_excedido``.

    The schema only bounds ``zona_ids``; whole-cuenca expansion resolves rows the
    caller never listed, so ``_resolver_zonas`` re-checks the total.
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    for i in range(61):
        _seed_zona(ficha_db, f"masiva-{i:02d}", "cuenca-masiva", LON0 + (i % 20) * D, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [], cuencas=["cuenca-masiva"])

    assert rs.status_code == 422
    cuerpo = rs.json()
    assert cuerpo["codigo"] == "cap_excedido"
    assert cuerpo["cap"] == "subcuencas"
    assert cuerpo["valor"] == 61


def test_preview_seleccion_vacia_422(ficha_db, monkeypatch):
    """Neither zona_ids nor cuencas → 422 geometria_invalida, not an empty 200."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [], cuencas=[])

    assert rs.status_code == 422
    assert rs.json()["codigo"] == "geometria_invalida"


def test_preview_zona_duplicada_422(ficha_db, monkeypatch):
    """Duplicates are rejected, not silently deduped (same discipline as parcelas)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    zona = _seed_zona(ficha_db, "dup", "cuenca-d", LON0, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = _preview(cliente, [zona, zona])

    assert rs.status_code == 422
    assert rs.json()["codigo"] == "geometria_invalida"


# ── ficha tipo=zonas: compute + stored-data desglose ────────────────────────


def test_ficha_zonas_desglose_desde_datos_guardados(ficha_db, monkeypatch, tmp_path):
    """S8: desglose from composite_zonal_stats + suelos + CHIRPS annual, no recompute."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    ids = _sembrar_mundo(ficha_db, tmp_path)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH,
            json={"tipo": "zonas", "zona_ids": [str(ids["a1"]), str(ids["a2"]), str(ids["b1"])]},
        )

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    assert cuerpo["tipo"] == "zonas"
    # the union of A1 + A2 adjacent and B1 overlapping A2 — not the sum
    assert cuerpo["area_ha"] == pytest.approx(
        _union_esperada_ha(ficha_db, list(ids.values())), rel=1e-4
    )

    desglose = cuerpo["desglose_por_subcuenca"]
    assert [fila["nombre"] for fila in desglose] == ["A1", "A2", "B1"]
    por_nombre = {fila["nombre"]: fila for fila in desglose}

    # A1: stored composite row (42 ha of ~105) → ~40 %, tagged with the legacy
    # threshold (#738 moves it to the class-breaks edge in PR 5 — not this PR)
    assert por_nombre["A1"]["pct_alto_critico"] == pytest.approx(40.0, abs=1.0)
    assert por_nombre["A1"]["clase_suelo_dominante"] == "IV"
    assert por_nombre["A1"]["lluvia_anual_mm"] == pytest.approx(100.0, abs=0.5)

    # no stored composite row for A2/B1 → None, never a fabricated 0 %
    assert por_nombre["A2"]["pct_alto_critico"] is None
    assert por_nombre["B1"]["pct_alto_critico"] is None
    assert por_nombre["A2"]["clase_suelo_dominante"] == "VII"
    assert por_nombre["B1"]["clase_suelo_dominante"] == "VII"

    # the threshold tag travels with the desglose (S8: mark it until #738)
    assert cuerpo["umbral_alto_critico"] == "leyenda-55"


def test_ficha_zonas_desglose_mas_fuera_es_total(ficha_db, monkeypatch, tmp_path):
    """S4 on the ficha numbers: desglose hectares + fuera = area_ha (±0,1 %)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    ids = _sembrar_mundo(ficha_db, tmp_path)
    adyacentes = [ids["a1"], ids["a2"]]  # same cuenca, no overlap

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            FICHA_PATH, json={"tipo": "zonas", "zona_ids": [str(z) for z in adyacentes]}
        )

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    suma = sum(fila["ha"] for fila in cuerpo["desglose_por_subcuenca"])
    assert suma == pytest.approx(cuerpo["area_ha"], rel=0.001)


def test_ficha_zonas_sobre_el_cap_422(ficha_db, monkeypatch):
    """L2/S3: >35 000 ha → the ficha compute rejects with the ``assert_within_caps`` shape.

    S3's "413 o 422" resolves to 422 ``cap_excedido`` — exactly what
    ``assert_within_caps`` produces for every other tipo, on ``area_ha``, with
    the zonas cap (35 000, not the inherited 20 000).
    """
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    grande = _seed_zona(ficha_db, "zona-gigante", "cuenca-g", LON0, LAT0, lado=LADO_ZONA_GRANDE)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "zonas", "zona_ids": [str(grande)]})

    assert rs.status_code == 422
    cuerpo = rs.json()
    assert cuerpo["codigo"] == "cap_excedido"
    assert cuerpo["cap"] == "area_ha"
    assert cuerpo["limite"] == 35_000.0
    assert cuerpo["valor"] > 35_000.0


def test_ficha_zonas_desconocidas_404(ficha_db, monkeypatch):
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    fantasma = uuid.uuid4()

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "zonas", "zona_ids": [str(fantasma)]})

    assert rs.status_code == 404
    assert rs.json()["codigo"] == "zona_no_encontrada"


def test_ficha_zonas_zona_duplicada_422(ficha_db, monkeypatch):
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    zona = _seed_zona(ficha_db, "dup", "cuenca-d", LON0, LAT0)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(FICHA_PATH, json={"tipo": "zonas", "zona_ids": [str(zona), str(zona)]})

    assert rs.status_code == 422
    assert rs.json()["codigo"] == "geometria_invalida"


def test_ficha_y_preview_dejan_auditoria(ficha_db, monkeypatch, tmp_path):
    """Both endpoints commit their Ley 25.326 row, under distinguishable actions."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    ids = _sembrar_mundo(ficha_db, tmp_path)

    with TestClient(_app(ficha_db)) as cliente:
        rs_preview = _preview(cliente, [ids["a1"]])
        rs_ficha = cliente.post(FICHA_PATH, json={"tipo": "zonas", "zona_ids": [str(ids["a1"])]})
    assert rs_preview.status_code == 200
    assert rs_ficha.status_code == 200, rs_ficha.text

    filas = ficha_db.execute(
        text(
            "SELECT action, resource FROM audit_log "
            "WHERE action IN ('zona.preview', 'zona.analisis') ORDER BY action"
        )
    ).all()
    acciones = {fila.action for fila in filas}
    assert acciones == {"zona.preview", "zona.analisis"}
    for fila in filas:
        assert fila.resource.startswith("tipo=zonas,n=1,ref=")


def test_overlay_acepta_tipo_zonas(ficha_db, monkeypatch, tmp_path):
    """The overlay resolves the SAME server-side union for tipo=zonas (uniform tipos)."""
    from fastapi.testclient import TestClient

    _enable(monkeypatch)
    ids = _sembrar_mundo(ficha_db, tmp_path)

    with TestClient(_app(ficha_db)) as cliente:
        rs = cliente.post(
            f"{FICHA_PATH}/overlay",
            json={"tipo": "zonas", "zona_ids": [str(ids["a1"])], "dataset": "suelos"},
        )

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    assert cuerpo["dataset"] == "suelos"
    clases = {feature["properties"]["clase"] for feature in cuerpo["features"]}
    assert clases == {"IV"}


# ── L2 acceptance condition: rough local p95 of the preview with 60 zonas ────


def test_preview_p95_60_zonas_local(ficha_db, monkeypatch):
    """Time the preview SERVICE call with 60 zonas; print the local p95.

    L2's acceptance condition for the 35 000 ha cap: T1 measures the preview's
    cost with a maximum selection. The assert is deliberately loose (5 s) so it
    only catches pathological regressions — the printed p95 is the number the
    decision is revised against, and this box is not prod.
    """
    from app.domains.geo import ficha_service
    from app.domains.geo.schemas_ficha import FichaZonasPreviewRequest

    _enable(monkeypatch)
    zona_ids = [
        _seed_zona(ficha_db, f"p95-{i:02d}", "cuenca-p95", LON0 + (i % 6) * D, LAT0 + (i // 6) * D)
        for i in range(60)
    ]
    payload = FichaZonasPreviewRequest(zona_ids=zona_ids)

    # one untimed warm-up (first call pays the plan cache + connection setup)
    ficha_service.preview_zonas(ficha_db, payload, client_ip="test")
    duraciones = []
    for _ in range(20):
        inicio = time.perf_counter()
        respuesta = ficha_service.preview_zonas(ficha_db, payload, client_ip="test")
        duraciones.append(time.perf_counter() - inicio)
        assert respuesta.modo == "online"

    p95 = statistics.quantiles(duraciones, n=20)[-1]
    print(f"\n[preview p95, 60 zonas, {len(duraciones)} runs] p95={p95 * 1000:.1f} ms")
    assert p95 < 5.0
