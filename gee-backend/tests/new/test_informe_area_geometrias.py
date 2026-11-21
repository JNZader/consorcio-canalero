"""Real-PostGIS integration tests for the informe de área geometrías (PR 3, T1).

``odd/tasks/informe-area-pr3.md`` S3/S4 + S6 (backend parts). Covers:

* the S6 repair: an AUTINTERSECTING polygon is repaired by ``ST_MakeValid``
  and measures its true area (no failure, no sign flip);
* mixed zonas + geometría create → task runs → ``completed`` with PDF and the
  geometrias/fuera_zona figures in ``resultado``;
* geometry-ONLY create (no zonas) → ``completed``; the desglose is empty and
  the totals/PDF still work;
* ``fuera_zona_ha`` for a polygon half inside / half outside the consorcio
  extent (the union of ``zonas_operativas``, the honest PostGIS stand-in for
  the GEE-only ``zona_cc_ampliada``);
* the preview endpoint: mixed measurement, disjoint-parts aviso, caps as
  answers (``aviso_cap``) instead of rejections;
* schema-level rejections: empty selection, non-polygonal geometry, unclosed
  ring, combined zonas-equivalents cap.

Same two DB disciplines as ``test_informe_area.py``: savepoint sessions for
the HTTP surface, a real-commit factory for the task flow (committed seed
data lives at the same dedicated longitude, lon ≈ -61.9, so it can never
intersect another fixture's world and no ``geo_layers`` row is committed).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import delete, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import User, UserRole
from app.domains.geo.models import EstadoGeoJob
from app.domains.geo.informe_area import service, tasks
from app.domains.geo.informe_area.models import InformeArea
from app.domains.geo.informe_area.repository import InformeAreaRepository
from app.shared.celery_outbox import CeleryTaskOutbox

INFORME_PATH = "/api/v2/geo/informes-area"

# Dedicated world for the PR 3 real-commit tests (far from test_informe_area's
# -61.5 and from any ficha fixture).
LON0, LAT0, D = -61.9, -33.0, 0.02

repo = InformeAreaRepository()


@pytest.fixture
def informe_db(test_engine) -> Session:
    """Session whose COMMITs are savepoint-scoped, so endpoints cannot leak."""
    connection = test_engine.connect()
    trans = connection.begin()
    session = Session(bind=connection)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart(sess: Any, transaction: Any) -> None:  # pragma: no cover - glue
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    yield session

    session.close()
    trans.rollback()
    connection.close()


@pytest.fixture
def factory(test_engine):
    """Committing session factory for the task-flow tests + their cleanup."""
    return sessionmaker(bind=test_engine, expire_on_commit=False)


def _app(db: Session, usuario: Any) -> Any:
    from fastapi import FastAPI

    from app.auth.dependencies import current_active_user
    from app.db.session import get_db
    from app.domains.geo.ficha_errors import install_ficha_error_handler
    from app.domains.geo.informe_area.errors import install_informe_area_error_handler
    from app.domains.geo.router import router as geo_router

    app = FastAPI()
    app.include_router(geo_router, prefix="/api/v2/geo")
    install_ficha_error_handler(app)
    install_informe_area_error_handler(app)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_active_user] = lambda: usuario
    return app


def _usuario(db: Session, correo: str) -> Any:
    from types import SimpleNamespace

    row = User(
        email=f"{correo.rsplit('@', 1)[0]}-{uuid.uuid4().hex[:8]}@{correo.rsplit('@', 1)[1]}",
        hashed_password="test",
        role=UserRole.OPERADOR,
        nombre="PR3",
        apellido="Informe",
        telefono="",
    )
    db.add(row)
    db.flush()
    return SimpleNamespace(id=row.id, role=UserRole.OPERADOR)


# ── seeding ─────────────────────────────────────────────────────────────────


def _seed_zona(db: Session, nombre: str, cuenca: str, x0: float, y0: float) -> uuid.UUID:
    zona_id = uuid.uuid4()
    wkt = f"POLYGON(({x0} {y0}, {x0 + D} {y0}, {x0 + D} {y0 + D}, {x0} {y0 + D}, {x0} {y0}))"
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, :nombre, :cuenca, ST_GeomFromText(:wkt, 4326), 0.0)"
        ),
        {"id": zona_id, "nombre": nombre, "cuenca": cuenca, "wkt": wkt},
    )
    return zona_id


def _cuadro(x0: float, y0: float, lado: float = D) -> dict[str, Any]:
    """A closed WGS84 square as GeoJSON — the wire shape the front sends."""
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [x0, y0],
                [x0 + lado, y0],
                [x0 + lado, y0 + lado],
                [x0, y0 + lado],
                [x0, y0],
            ]
        ],
    }


def _corbatin(x0: float, y0: float, lado: float = D) -> dict[str, Any]:
    """An AUTINTERSECTING bowtie polygon (S6): (0,0)(2,0)(0,2)(2,2)(0,0)."""
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [x0, y0],
                [x0 + lado, y0],
                [x0, y0 + lado],
                [x0 + lado, y0 + lado],
                [x0, y0],
            ]
        ],
    }


def _crear_suelos_si_falta(db: Session) -> None:
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
    db.commit()


def _limpiar(factory, *, usuario_id, zona_ids, informe_ids) -> None:
    with factory() as db:
        db.execute(
            delete(CeleryTaskOutbox).where(CeleryTaskOutbox.task_key == "geo.informe_area.generar")
        )
        db.execute(
            delete(InformeArea).where(
                InformeArea.id.in_(informe_ids) | (InformeArea.usuario_id == usuario_id)
            )
        )
        if zona_ids:
            db.execute(
                text("DELETE FROM zonas_operativas WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(z) for z in zona_ids]},
            )
        if usuario_id:
            db.execute(delete(User).where(User.id == usuario_id))
        db.commit()


# ── S6: autointersecting polygon repaired and measured ──────────────────────


def test_poligono_autointersectado_se_repara_y_mide(informe_db):
    """S6: a bowtie repairs via ST_MakeValid and measures the two triangles.

    The bowtie (0,0)(d,0)(0,d)(d,d) closes as two triangles of total area
    d²/2 — half the envelope. ST_MakeValid splits it; the EPSG:32720 measure
    must land within 1 % of the planar expectation (projection distortion
    over a 0.02° square is far below that).
    """
    corbatin = _corbatin(LON0, LAT0)
    resuelta = service.resolver_seleccion(informe_db, [], [corbatin])

    assert resuelta.area_ha > 0.0
    # Planar expectation over WGS84 degrees → metres at this latitude (the
    # cos factor is what makes this a real check — without it the expectation
    # is ~19 % too large at 33°S).
    import math

    metros_por_grado_lon = 111_320.0 * math.cos(math.radians(abs(LAT0)))
    metros_por_grado_lat = 110_574.0
    d_lon, d_lat = D * metros_por_grado_lon, D * metros_por_grado_lat
    esperado_ha = (d_lon * d_lat / 2.0) / 10_000.0
    assert abs(resuelta.area_ha - esperado_ha) / esperado_ha < 0.01
    # The repair keeps it polygonal and single (the two triangles form ONE
    # multipolygon → separados is True, but the area is the SUM).
    assert resuelta.poligonos_separados is True


def test_resolver_mezcla_zonas_y_geometria(informe_db):
    """S3: zonas + geometria union measures MORE than the zona alone."""
    zona = _seed_zona(informe_db, "base-1", "cuenca-pr3", LON0, LAT0)
    informe_db.flush()

    sola = service.resolver_seleccion(informe_db, [zona])
    # One square to the EAST, with a GAP: an adjacent square would DISSOLVE
    # into the zona's rectangle and the union would be a single polygon.
    pegada = service.resolver_seleccion(informe_db, [zona], [_cuadro(LON0 + 2 * D, LAT0)])
    assert pegada.area_ha > sola.area_ha * 1.9  # roughly doubles
    assert pegada.poligonos_separados is True
    # The geometria sits inside the world but OUTSIDE the zonas extent: half
    # of it overlaps the zona's column? No — it is fully outside every zona
    # row here, so the whole square counts as fuera.
    assert pegada.fuera_zona_ha > 0.0


def test_fuera_zona_mitad_afuera(informe_db):
    """S6: a polygon half inside the consorcio extent reports half outside."""
    zona = _seed_zona(informe_db, "mitad-1", "cuenca-mitad", LON0, LAT0)
    informe_db.flush()

    # Square straddling the zona's EAST edge: west half inside, east half out.
    a_caballo = _cuadro(LON0 + D / 2, LAT0, lado=D)
    resuelta = service.resolver_seleccion(informe_db, [], [a_caballo])

    total = resuelta.area_ha
    fuera = resuelta.fuera_zona_ha
    assert total > 0.0
    assert 0.40 < fuera / total < 0.60, (total, fuera)


def test_s7_area_kml_vs_preview(informe_db):
    """S7 (accuracy half): the preview's EPSG:32720 area agrees with the KML's
    @turf/area figure (the frontend's parse of the same square) within 0.5 %.

    The turf constant comes from the frontend fixture
    ``tests/unit/geo/leerKmlS7.medicion.test.ts`` — 412.4657 ha for the
    closed square (-62.5,-33.5) + 0.02°. If either side changes its fixture,
    BOTH tests are re-based together.
    """
    cuadro = {
        "type": "Polygon",
        "coordinates": [
            [
                [-62.5, -33.5],
                [-62.48, -33.5],
                [-62.48, -33.48],
                [-62.5, -33.48],
                [-62.5, -33.5],
            ]
        ],
    }
    resuelta = service.resolver_seleccion(informe_db, [], [cuadro])

    turf_ha = 412.4657
    assert abs(resuelta.area_ha - turf_ha) / turf_ha < 0.005, resuelta.area_ha


# ── create + task: mixed and geometry-only (S3, real commits) ───────────────


def test_create_mezclado_completa_con_pdf(factory, monkeypatch):
    """S6: mixed zonas+geometría create → task → completed with PDF."""
    from app.domains.geo import service as service_mod

    monkeypatch.setattr(service_mod, "try_publish_celery_task", lambda _id: False)

    usuario_id = None
    zona_ids: list[uuid.UUID] = []
    informe_ids: list[uuid.UUID] = []
    try:
        with factory() as db:
            _crear_suelos_si_falta(db)
            usuario = User(
                email=f"informe-pr3-mix-{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="test",
                role=UserRole.OPERADOR,
                nombre="PR3",
                apellido="Mix",
                telefono="",
            )
            db.add(usuario)
            db.flush()
            zona = _seed_zona(db, "mix-1", "cuenca-mix", LON0, LAT0)
            db.commit()
            usuario_id, zona_ids = usuario.id, [zona]

            from app.domains.geo.informe_area.schemas import InformeAreaCreate

            payload = InformeAreaCreate(
                nombre="Mixto",
                zona_ids=[zona],
                geometrias=[_cuadro(LON0 + 2 * D, LAT0)],
            )
            row, desde_cache = service.crear_informe(db, payload, usuario_id=usuario_id)
            informe_ids.append(row.id)
            assert desde_cache is False
            assert row.parametros["geometrias"] == payload.geometrias

        assert tasks.generar_informe_area(str(informe_ids[0]))["estado"] == "completed"

        with factory() as db:
            row = db.get(InformeArea, informe_ids[0])
            assert row.estado == EstadoGeoJob.COMPLETED
            assert row.pdf_bytes, "the mixed informe must carry its PDF"
            res = row.resultado
            assert res["zonas"] == 1
            assert res["geometrias"] == 1
            assert res["fuera_zona_ha"] > 0.0
            assert res["desglose"], "the zona keeps its desglose row"
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=zona_ids,
            informe_ids=informe_ids,
        )


def test_create_solo_geometria_completa_desglose_vacio(factory, monkeypatch):
    """S3: geometry-only selection → completed; empty desglose, totals alive."""
    from app.domains.geo import service as service_mod

    monkeypatch.setattr(service_mod, "try_publish_celery_task", lambda _id: False)

    usuario_id = None
    informe_ids: list[uuid.UUID] = []
    try:
        with factory() as db:
            _crear_suelos_si_falta(db)
            usuario = User(
                email=f"informe-pr3-geo-{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="test",
                role=UserRole.OPERADOR,
                nombre="PR3",
                apellido="Geo",
                telefono="",
            )
            db.add(usuario)
            db.flush()
            db.commit()
            usuario_id = usuario.id

            from app.domains.geo.informe_area.schemas import InformeAreaCreate

            payload = InformeAreaCreate(
                nombre="Solo geometría", zona_ids=[], geometrias=[_cuadro(LON0, LAT0)]
            )
            row, _ = service.crear_informe(db, payload, usuario_id=usuario_id)
            informe_ids.append(row.id)

        assert tasks.generar_informe_area(str(informe_ids[0]))["estado"] == "completed"

        with factory() as db:
            row = db.get(InformeArea, informe_ids[0])
            res = row.resultado
            assert res["zonas"] == 0
            assert res["geometrias"] == 1
            assert res["area_ha"] > 0.0
            # No zonas → no per-zone rows (None, the same "not computed" the
            # "Solo total" depth stores — never a fabricated empty table).
            assert not res["desglose"]
            assert row.pdf_bytes, "a geometry-only informe still renders its PDF"
    finally:
        _limpiar(factory, usuario_id=usuario_id, zona_ids=[], informe_ids=informe_ids)


# ── preview endpoint (S2/S4, savepoint sessions) ────────────────────────────


def test_preview_mezclado_responde_area_y_avisos(informe_db):
    """S2/S4: the preview answers the mixed measurement with both avisos."""
    from fastapi.testclient import TestClient

    zona = _seed_zona(informe_db, "prev-1", "cuenca-prev", LON0, LAT0)
    informe_db.flush()
    usuario = _usuario(informe_db, "informe-pr3-prev@test.local")

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(
            f"{INFORME_PATH}/preview",
            json={"zona_ids": [str(zona)], "geometrias": [_cuadro(LON0 + 3 * D, LAT0)]},
        )

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    assert cuerpo["area_total_ha"] > 0.0
    assert cuerpo["cantidad_geometrias"] == 1
    assert len(cuerpo["subcuencas"]) == 1
    assert cuerpo["subcuencas"][0]["nombre"] == "prev-1"
    # zona + distant square → the union is disjoint and the square is outside
    # the consorcio extent.
    assert cuerpo["poligonos_separados"] is True
    assert cuerpo["fuera_zona_ha"] > 0.0
    assert cuerpo["aviso_cap"] is False


def test_preview_zonas_only_mantiene_contrato(informe_db):
    """PR 2 compat: zonas-only previews still answer (no geometrias key)."""
    from fastapi.testclient import TestClient

    zona = _seed_zona(informe_db, "prev-z", "cuenca-z", LON0, LAT0)
    informe_db.flush()
    usuario = _usuario(informe_db, "informe-pr3-prevz@test.local")

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(f"{INFORME_PATH}/preview", json={"zona_ids": [str(zona)]})

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    assert cuerpo["cantidad_geometrias"] == 0
    assert cuerpo["fuera_zona_ha"] == 0.0
    assert cuerpo["poligonos_separados"] is False


def test_preview_vacio_422(informe_db):
    """Neither zonas nor geometrias → the flat 422, not an empty measure."""
    from fastapi.testclient import TestClient

    usuario = _usuario(informe_db, "informe-pr3-vacio@test.local")
    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(f"{INFORME_PATH}/preview", json={})

    assert rs.status_code == 422
    assert rs.json()["codigo"] == "geometria_invalida"


def test_preview_geometria_rechazada_422(informe_db):
    """Non-polygonal geometry and unclosed ring die with the ficha's codes."""
    from fastapi.testclient import TestClient

    usuario = _usuario(informe_db, "informe-pr3-bad@test.local")
    with TestClient(_app(informe_db, usuario)) as cliente:
        rs_punto = cliente.post(
            f"{INFORME_PATH}/preview",
            json={"geometrias": [{"type": "Point", "coordinates": [-62, -32]}]},
        )
        rs_abierto = cliente.post(
            f"{INFORME_PATH}/preview",
            json={
                "geometrias": [
                    {
                        "type": "Polygon",
                        "coordinates": [[[-62, -32], [-61, -32], [-61, -31], [-62, -31]]],
                    }
                ]
            },
        )

    assert rs_punto.status_code == 422
    assert rs_punto.json()["codigo"] == "geometria_invalida"
    assert rs_abierto.status_code == 422
    assert rs_abierto.json()["codigo"] == "geometria_invalida"


def test_preview_cap_se_responde_no_se_rechaza(informe_db):
    """S4 answer-don't-reject: an over-35k selection previews with aviso_cap."""
    from fastapi.testclient import TestClient

    # ~0.4° square ≈ 168 000 ha — over the 35 000 ha online cap, under the
    # 150 000 ha informe cap? No: 168k > 150k too, but the PREVIEW never
    # rejects (aplicar_caps=False) — it answers with aviso_cap=True.
    grande = _cuadro(LON0, LAT0, lado=0.4)
    usuario = _usuario(informe_db, "informe-pr3-cap@test.local")

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(f"{INFORME_PATH}/preview", json={"geometrias": [grande]})

    assert rs.status_code == 200, rs.text
    cuerpo = rs.json()
    assert cuerpo["aviso_cap"] is True
    assert cuerpo["area_total_ha"] > 35_000.0


def test_create_mezclado_sobre_cap_ha_422(informe_db):
    """The CREATE still enforces the hard 150 000 ha cap over the mixed union."""
    from fastapi.testclient import TestClient

    grande = _cuadro(LON0, LAT0, lado=0.4)
    usuario = _usuario(informe_db, "informe-pr3-cap-create@test.local")

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(INFORME_PATH, json={"nombre": "Demasiado grande", "geometrias": [grande]})

    assert rs.status_code == 422, rs.text
    cuerpo = rs.json()
    assert cuerpo["codigo"] == "cap_excedido"
    assert cuerpo["cap"] == "area_ha"


def test_create_cap_zonas_equivalentes_422(informe_db):
    """S5: 120 combined is the bound — 60 zonas + 61 geometrias is a 422."""
    from fastapi.testclient import TestClient

    ids = []
    for i in range(60):
        ids.append(str(_seed_zona(informe_db, f"cap-{i}", "cuenca-cap", LON0 + i * D, LAT0)))
    informe_db.flush()
    usuario = _usuario(informe_db, "informe-pr3-cap-mix@test.local")
    geometrias = [_cuadro(LON0 + 100 * D + i * D, LAT0) for i in range(61)]

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(
            INFORME_PATH,
            json={"nombre": "Muchos", "zona_ids": ids, "geometrias": geometrias},
        )

    assert rs.status_code == 422, rs.text
    assert rs.json()["codigo"] == "cap_excedido"


def test_create_cuerpo_sobre_limite_413_content_length_y_chunked(informe_db, monkeypatch):
    """C3: bodies over informe_area_max_body_bytes fail with 413 on Content-Length and chunked."""
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "informe_area_max_body_bytes", 1024)
    usuario = _usuario(informe_db, "informe-c3-body@test.local")
    oversized = b'{"nombre":"x","geometrias":[]}' + b" " * 2048

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs_len = cliente.post(
            INFORME_PATH,
            content=oversized,
            headers={"Content-Type": "application/json"},
        )
        assert rs_len.status_code == 413

        def _chunks():
            yield oversized[:512]
            yield oversized[512:]

        rs_chunked = cliente.post(
            INFORME_PATH,
            content=_chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert rs_chunked.status_code == 413


def test_create_y_preview_poligonos_muy_lejanos_sobre_cap_envelope_ha_422(informe_db):
    """C3: small disjoint polygons spanning >500,000 ha envelope fail 422 instead of OOMing."""
    from fastapi.testclient import TestClient

    cuadro_a = _cuadro(LON0, LAT0, lado=0.01)
    cuadro_b = _cuadro(LON0 + 4.0, LAT0 + 4.0, lado=0.01)
    usuario = _usuario(informe_db, "informe-c3-env@test.local")

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs_prev = cliente.post(
            f"{INFORME_PATH}/preview",
            json={"geometrias": [cuadro_a, cuadro_b]},
        )
        assert rs_prev.status_code == 422, rs_prev.text
        assert rs_prev.json()["codigo"] == "cap_excedido"
        assert rs_prev.json()["cap"] == "envelope_ha"

        rs_create = cliente.post(
            INFORME_PATH,
            json={"nombre": "Lejanos", "geometrias": [cuadro_a, cuadro_b]},
        )
        assert rs_create.status_code == 422, rs_create.text
        assert rs_create.json()["codigo"] == "cap_excedido"
        assert rs_create.json()["cap"] == "envelope_ha"
