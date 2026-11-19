"""Real-PostGIS integration tests for the informe de área backend (PR 2, T1).

``odd/tasks/informe-area-pr2.md`` S3-S5 + S8 (backend parts) + S11. Covers:

* create → task runs (invoked DIRECTLY, like ``test_geo_outbox_dispatch`` and
  every geo task test) → ``completed`` with the stored ``resultado`` totals;
* the S4 cache: a second identical create returns the SAME row with
  ``desde_cache=True`` and enqueues nothing, and a ``version_clave`` change
  (template bump — the cheapest honest invalidation) produces a NEW row;
* the S5 caps through the HTTP surface: 150 001+ ha → 422 ``cap_excedido``,
  121 zona_ids → 422, a 4th informe with 3 in course → 429;
* S11 privacy: creator sees own, another operator gets the missing-id 404,
  admin sees all;
* S8 failure path: an injected compute failure leaves ``failed`` with a
  readable ``error``;
* S11 retention: the sweep deletes expired rows and keeps live ones.

Two DB disciplines, both house patterns:

* **savepoint sessions (TestClient tests)** — the service COMMITs inside the
  endpoint, so the fixture joins the external transaction with a restarting
  SAVEPOINT (same as ``test_ficha_zonas.ficha_db``); teardown rolls everything
  back.
* **real commits (task tests)** — the Celery task opens its OWN
  ``SessionLocal`` and cannot see another transaction's rows, so those tests
  commit for real through a factory session and clean up in ``finally``
  (same as ``test_geo_outbox_dispatch``). Committed seed data lives at a
  dedicated longitude so it can never intersect another fixture's world, and
  NO ``geo_layers`` row is ever committed (a leaked newest raster would
  change which file other ficha tests read).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import delete, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import User, UserRole
from app.domains.geo.models import EstadoGeoJob
from app.domains.geo.informe_area import service, tasks
from app.domains.geo.informe_area.models import InformeArea
from app.domains.geo.informe_area.repository import InformeAreaRepository
from app.domains.geo.informe_area.schemas import InformeAreaCreate
from app.shared.celery_outbox import CeleryTaskOutbox

INFORME_PATH = "/api/v2/geo/informes-area"

# A dedicated world for REAL-COMMIT tests: no other fixture seeds anything
# near lon -61.5, so committed zonas/composites can never leak into them.
LON0, LAT0, D = -61.5, -32.0, 0.01

# 0.4° square ≈ 168 000 ha — past the 150 000 ha informe cap (S5), which is
# the bound under test (the area cap must fire before anything is queued).
LADO_SOBRE_CAP = 0.4

repo = InformeAreaRepository()


# ── fixtures ─────────────────────────────────────────────────────────────────


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
    """Fresh app with ONLY the geo router mounted, authenticated as ``usuario``."""
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


def _usuario(db: Session, role: UserRole = UserRole.OPERADOR) -> SimpleNamespace:
    """Auth override whose id satisfies the ``informes_area.usuario_id`` FK.

    The override object never hits fastapi-users; the SERVICE reads ``.id`` /
    ``.role`` off it — and the row insert needs a real ``users`` row behind
    that id.
    """
    row = _seed_usuario(db, f"informe-t1-{uuid.uuid4().hex[:10]}@test.local", role)
    return SimpleNamespace(id=row.id, role=role)


# ── seeding ─────────────────────────────────────────────────────────────────


def _seed_usuario(db: Session, email: str, role: UserRole = UserRole.OPERADOR) -> User:
    usuario = User(
        email=email,
        hashed_password="test",
        role=role,
        nombre="T1",
        apellido="Informe",
        telefono="",
    )
    db.add(usuario)
    db.flush()
    return usuario


def _seed_zona(
    db: Session,
    nombre: str,
    cuenca: str,
    x0: float,
    y0: float,
    *,
    lado: float = D,
) -> uuid.UUID:
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


def _seed_informe(
    db: Session,
    *,
    usuario_id: uuid.UUID,
    nombre: str,
    vence_at: datetime,
    estado: EstadoGeoJob = EstadoGeoJob.PENDING,
) -> InformeArea:
    return repo.crear(
        db,
        usuario_id=usuario_id,
        nombre=nombre,
        hash_seleccion="test-" + uuid.uuid4().hex,
        version_clave="test-" + uuid.uuid4().hex,
        parametros={"zona_ids": [], "desglose": True},
        vence_at=vence_at,
        celery_task_id=str(uuid.uuid4()),
    )


def _crear_suelos_si_falta(db: Session) -> None:
    """``_desglose_zonas`` joins ``suelos_catastro``; ensure the table exists.

    The ficha tests create it inside ROLLED-BACK transactions, so a task test
    that commits for real must create (and leave empty) it itself.
    """
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
        db.execute(
            text("DELETE FROM composite_zonal_stats WHERE zona_id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(z) for z in zona_ids]},
        )
        if zona_ids:
            db.execute(
                text("DELETE FROM zonas_operativas WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(z) for z in zona_ids]},
            )
        db.execute(delete(User).where(User.id == usuario_id))
        db.commit()


# ── task flow: create → run → completed → cache (S4/S8, real commits) ───────


def test_crear_tarea_completa_y_segunda_create_da_cache(factory, monkeypatch):
    """S8: the task completes with totals; the same create reuses the row."""
    from app.domains.geo import service as service_mod

    monkeypatch.setattr(service_mod, "try_publish_celery_task", lambda _id: False)

    usuario_id = zona_id = None
    informe_ids: list[uuid.UUID] = []
    try:
        with factory() as db:
            _crear_suelos_si_falta(db)
            usuario = _seed_usuario(db, "informe-t1-cache@test.local")
            zona_id = _seed_zona(db, "norte-1", "cuenca-t1", LON0, LAT0)
            db.commit()
            usuario_id = usuario.id

            payload = InformeAreaCreate(nombre="Informe norte", zona_ids=[zona_id])
            row, desde_cache = service.crear_informe(db, payload, usuario_id=usuario_id)
            informe_ids.append(row.id)
            assert desde_cache is False
            assert row.estado == EstadoGeoJob.PENDING
            assert row.progreso == 0
            assert row.vence_at > datetime.now(timezone.utc) + timedelta(days=89)

        resultado_task = tasks.generar_informe_area(str(informe_ids[0]))
        assert resultado_task["estado"] == "completed"

        with factory() as db:
            row = db.get(InformeArea, informe_ids[0])
            assert row.estado == EstadoGeoJob.COMPLETED
            assert row.progreso == 100
            assert row.error is None
            res = row.resultado
            assert res["area_ha"] > 0.0
            assert res["zonas"] == 1
            assert res["cuencas"] == ["cuenca-t1"]
            assert res["umbral_alto_critico"] == "leyenda-55"  # PR 5 (#738)
            assert res["degradado"] == []
            # stored-data desglose: no composite row seeded → None, never 0 %
            desglose = res["desglose"]
            assert desglose and desglose[0]["nombre"] == "norte-1"
            assert desglose[0]["pct_alto_critico"] is None
            assert desglose[0]["clase_suelo_dominante"] is None

        # Second IDENTICAL create: same user, same selection, same layer
        # versions → the completed row comes back, nothing is enqueued.
        with factory() as db:
            row2, desde_cache2 = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe norte", zona_ids=[zona_id]),
                usuario_id=usuario_id,
            )
            assert desde_cache2 is True
            assert row2.id == informe_ids[0]

            total_filas = db.execute(
                text("SELECT count(*) FROM informes_area WHERE usuario_id = :u"),
                {"u": str(usuario_id)},
            ).scalar_one()
            encolados = db.execute(
                text(
                    "SELECT count(*) FROM celery_task_outbox "
                    "WHERE task_key = 'geo.informe_area.generar'"
                ),
            ).scalar_one()
            assert total_filas == 1
            assert encolados == 1
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=[zona_id] if zona_id else [],
            informe_ids=informe_ids,
        )


def test_version_clave_cambiada_invalida_cache(factory, monkeypatch):
    """S8: a template-version bump changes the clave → a NEW informe runs."""
    from app.config import settings
    from app.domains.geo import service as service_mod

    monkeypatch.setattr(service_mod, "try_publish_celery_task", lambda _id: False)

    usuario_id = zona_id = None
    informe_ids: list[uuid.UUID] = []
    try:
        with factory() as db:
            _crear_suelos_si_falta(db)
            usuario = _seed_usuario(db, "informe-t1-version@test.local")
            zona_id = _seed_zona(db, "sur-1", "cuenca-v", LON0 + D, LAT0)
            db.commit()
            usuario_id = usuario.id
            row, _ = service.crear_informe(
                db,
                InformeAreaCreate(nombre="v1", zona_ids=[zona_id]),
                usuario_id=usuario_id,
            )
            informe_ids.append(row.id)

        tasks.generar_informe_area(str(row.id))

        with factory() as db:
            # Simulate the layout/layer refresh the clave exists for: same
            # selection, NEW version_plantilla → probe misses → new row.
            # ("3": the default is "2" since PR 4 added sections — the
            # monkeypatch value must differ from the running default.)
            monkeypatch.setattr(settings, "informe_area_version_plantilla", "3")
            row2, desde_cache = service.crear_informe(
                db,
                InformeAreaCreate(nombre="v1", zona_ids=[zona_id]),
                usuario_id=usuario_id,
            )
            informe_ids.append(row2.id)
            assert desde_cache is False
            assert row2.id != row.id
            assert row2.version_clave != row.version_clave
            assert row2.version_clave.startswith(row.hash_seleccion)
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=[zona_id] if zona_id else [],
            informe_ids=informe_ids,
        )


def test_falla_inyectada_deja_failed_con_error_legible(factory, monkeypatch):
    """S8: an injected compute failure → estado failed + error legible."""
    from app.domains.geo import ficha_service
    from app.domains.geo import service as service_mod

    monkeypatch.setattr(service_mod, "try_publish_celery_task", lambda _id: False)

    def _explota(db: Any, zonas: Any) -> Any:
        raise RuntimeError("GEE no disponible")

    monkeypatch.setattr(ficha_service, "_desglose_zonas", _explota)

    usuario_id = zona_id = None
    informe_ids: list[uuid.UUID] = []
    try:
        with factory() as db:
            _crear_suelos_si_falta(db)
            usuario = _seed_usuario(db, "informe-t1-falla@test.local")
            zona_id = _seed_zona(db, "falla-1", "cuenca-f", LON0 + 2 * D, LAT0)
            db.commit()
            usuario_id = usuario.id
            row, _ = service.crear_informe(
                db,
                InformeAreaCreate(nombre="falla", zona_ids=[zona_id]),
                usuario_id=usuario_id,
            )
            informe_ids.append(row.id)

        salida = tasks.generar_informe_area(str(row.id))
        assert salida["estado"] == "failed"

        with factory() as db:
            row = db.get(InformeArea, row.id)
            assert row.estado == EstadoGeoJob.FAILED
            assert "GEE no disponible" in (row.error or "")
            assert row.resultado is None
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=[zona_id] if zona_id else [],
            informe_ids=informe_ids,
        )


# ── caps + ceiling through the HTTP surface (S5, savepoint sessions) ────────


def test_create_sobre_150_mil_ha_422(informe_db, monkeypatch):
    """S5: a ~168 000 ha selection is rejected with the house cap shape."""
    from fastapi.testclient import TestClient

    grande = _seed_zona(informe_db, "zona-gigante", "cuenca-g", LON0, LAT0, lado=LADO_SOBRE_CAP)
    informe_db.flush()
    usuario = _usuario(informe_db, UserRole.OPERADOR)

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(
            INFORME_PATH, json={"nombre": "Demasiado grande", "zona_ids": [str(grande)]}
        )

    assert rs.status_code == 422, rs.text
    cuerpo = rs.json()
    assert cuerpo["codigo"] == "cap_excedido"
    assert cuerpo["cap"] == "area_ha"
    assert cuerpo["limite"] == 150_000.0
    assert cuerpo["valor"] > 150_000.0


def test_create_121_zonas_422(informe_db):
    """S5: 121 zona_ids die in the schema, before any geometry work."""
    from fastapi.testclient import TestClient

    usuario = _usuario(informe_db, UserRole.OPERADOR)
    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(
            INFORME_PATH,
            json={"nombre": "Muchas", "zona_ids": [str(uuid.uuid4()) for _ in range(121)]},
        )

    assert rs.status_code == 422


def test_create_cuarto_informe_en_curso_429(informe_db):
    """S5: 3 in-progress is the ceiling — the 4th create is a 429."""
    from fastapi.testclient import TestClient

    usuario = _usuario(informe_db, UserRole.OPERADOR)
    zona = _seed_zona(informe_db, "ceiling-1", "cuenca-c", LON0, LAT0)
    _seed_usuario(informe_db, "informe-t1-ceiling@test.local")
    dentro = datetime.now(timezone.utc) + timedelta(days=90)
    for i in range(3):
        _seed_informe(
            informe_db,
            usuario_id=usuario.id,
            nombre=f"en-curso-{i}",
            vence_at=dentro,
        )
    informe_db.flush()

    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(INFORME_PATH, json={"nombre": "El cuarto", "zona_ids": [str(zona)]})

    assert rs.status_code == 429, rs.text
    cuerpo = rs.json()
    assert cuerpo["codigo"] == "limite_informes_en_curso"


def test_create_zona_desconocida_404(informe_db):
    """All-or-nothing resolution, same code as the ficha (PR 1 reuse)."""
    from fastapi.testclient import TestClient

    usuario = _usuario(informe_db, UserRole.OPERADOR)
    with TestClient(_app(informe_db, usuario)) as cliente:
        rs = cliente.post(
            INFORME_PATH, json={"nombre": "Fantasma", "zona_ids": [str(uuid.uuid4())]}
        )

    assert rs.status_code == 404
    assert rs.json()["codigo"] == "zona_no_encontrada"


# ── privacy (S11, savepoint sessions) ───────────────────────────────────────


def test_privacidad_creador_ve_lo_suyo_otro_operador_404_admin_ve_todo(informe_db):
    """S11: creator OK; a different operator gets the missing-id 404; admin all."""
    from fastapi.testclient import TestClient

    creador = _usuario(informe_db)
    otro = _usuario(informe_db)
    admin = _usuario(informe_db, UserRole.ADMIN)
    zona = _seed_zona(informe_db, "priv-1", "cuenca-p", LON0, LAT0)
    informe_db.flush()

    with TestClient(_app(informe_db, creador)) as cliente:
        rs = cliente.post(INFORME_PATH, json={"nombre": "Privado", "zona_ids": [str(zona)]})
    assert rs.status_code == 202, rs.text
    informe_id = rs.json()["id"]
    assert rs.json()["estado"] == "pending"
    assert rs.json()["desde_cache"] is False

    # creator: own detail + own list
    with TestClient(_app(informe_db, creador)) as cliente:
        assert cliente.get(f"{INFORME_PATH}/{informe_id}").status_code == 200
        lista = cliente.get(INFORME_PATH).json()
    assert lista["total"] == 1
    assert lista["items"][0]["id"] == str(informe_id)

    # another operator: DETAIL is the same 404 as a missing id (no disclosure)
    with TestClient(_app(informe_db, otro)) as cliente:
        rs_otro = cliente.get(f"{INFORME_PATH}/{informe_id}")
        lista_otro = cliente.get(INFORME_PATH).json()
    assert rs_otro.status_code == 404
    assert rs_otro.json()["codigo"] == "informe_no_encontrado"
    assert lista_otro["total"] == 0

    # admin: sees it without being the creator
    with TestClient(_app(informe_db, admin)) as cliente:
        assert cliente.get(f"{INFORME_PATH}/{informe_id}").status_code == 200
        lista_admin = cliente.get(INFORME_PATH).json()
    assert lista_admin["total"] >= 1
    assert str(informe_id) in {item["id"] for item in lista_admin["items"]}


def test_pdf_pendiente_409_y_completado_503_hasta_t2(informe_db):
    """T1 download placeholder: pending → 409; completed → typed 503 (no T2 yet)."""
    from fastapi.testclient import TestClient

    creador = _usuario(informe_db)
    zona = _seed_zona(informe_db, "pdf-1", "cuenca-pdf", LON0, LAT0)
    informe_db.flush()

    with TestClient(_app(informe_db, creador)) as cliente:
        rs = cliente.post(INFORME_PATH, json={"nombre": "Con PDF", "zona_ids": [str(zona)]})
        informe_id = rs.json()["id"]

        rs_pendiente = cliente.get(f"{INFORME_PATH}/{informe_id}/pdf")
        assert rs_pendiente.status_code == 409
        assert rs_pendiente.json()["codigo"] == "informe_en_progreso"

    # force-complete the row inside the savepoint, then ask again: the bytes
    # arrive with T2, so a completed informe answers the TYPED 503 meanwhile
    fila = repo.obtener(informe_db, uuid.UUID(informe_id))
    repo.actualizar_estado_if_actual(
        informe_db,
        fila.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.COMPLETED,
        progreso=100,
        resultado={"area_ha": 1.0, "zonas": 1},
    )
    informe_db.expire_all()
    with TestClient(_app(informe_db, creador)) as cliente:
        rs_completado = cliente.get(f"{INFORME_PATH}/{informe_id}/pdf")
    assert rs_completado.status_code == 503
    assert rs_completado.json()["codigo"] == "pdf_aun_no_disponible"


# ── retention sweep (S11, real commits) ─────────────────────────────────────


def test_limpieza_borra_vencidos_y_conserva_vivos(factory):
    """S11: the daily sweep deletes past-``vence_at`` rows and keeps live ones."""
    usuario_id = None
    informe_ids: list[uuid.UUID] = []
    try:
        with factory() as db:
            usuario = _seed_usuario(db, "informe-t1-retencion@test.local")
            db.commit()
            usuario_id = usuario.id
            ahora = datetime.now(timezone.utc)
            vencido = _seed_informe(
                db,
                usuario_id=usuario_id,
                nombre="vencido",
                vence_at=ahora - timedelta(days=1),
            )
            vivo = _seed_informe(
                db,
                usuario_id=usuario_id,
                nombre="vivo",
                vence_at=ahora + timedelta(days=89),
            )
            db.commit()
            informe_ids = [vencido.id, vivo.id]

        salida = tasks.limpiar_informes_vencidos()
        assert salida["borrados"] >= 1

        with factory() as db:
            assert db.get(InformeArea, vencido.id) is None
            assert db.get(InformeArea, vivo.id) is not None
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=[],
            informe_ids=informe_ids,
        )
