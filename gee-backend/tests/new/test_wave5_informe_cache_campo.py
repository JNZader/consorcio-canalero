"""Regression tests for Wave 5 W-INF-01, W-INF-02, and S-01 RFC 5987."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole
from app.config import settings
from app.domains.geo.informe_area import service
from app.domains.geo.informe_area.models import InformeArea
from app.domains.geo.informe_area.schemas import InformeAreaCreate
from app.domains.geo.models import EstadoGeoJob


@pytest.fixture
def informe_db(test_engine) -> Session:
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


def _seed_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        hashed_password="test",
        role=UserRole.OPERADOR,
        nombre="Wave5",
        apellido="Test",
        telefono="",
    )
    db.add(user)
    db.flush()
    return user


def _seed_zona(db: Session, nombre: str) -> uuid.UUID:
    zona_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, :nombre, 'cuenca-w5', "
            "ST_GeomFromText('POLYGON((-61.2 -32.2, -61.18 -32.2, -61.18 -32.18, -61.2 -32.18, -61.2 -32.2))', 4326), "
            "400.0)"
        ),
        {"id": str(zona_id), "nombre": nombre},
    )
    return zona_id


def test_default_plantilla_version_bumped_and_desglose_splits_cache_key(
    informe_db: Session, monkeypatch
) -> None:
    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)
    assert int(settings.informe_area_version_plantilla) >= 3

    user = _seed_user(informe_db, f"w5-desglose-{uuid.uuid4().hex[:8]}@test.local")
    zona_id = _seed_zona(informe_db, "w5-zona-desglose")

    row_simple, cache_1 = service.crear_informe(
        informe_db,
        InformeAreaCreate(nombre="Simple", zona_ids=[zona_id], desglose=False),
        usuario_id=user.id,
    )
    assert cache_1 is False
    service.repo.actualizar_estado_if_actual(
        informe_db,
        row_simple.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.COMPLETED,
    )

    row_full, cache_2 = service.crear_informe(
        informe_db,
        InformeAreaCreate(nombre="Con desglose", zona_ids=[zona_id], desglose=True),
        usuario_id=user.id,
    )
    assert cache_2 is False
    assert row_full.id != row_simple.id
    assert row_full.version_clave != row_simple.version_clave
    assert "|desglose=0|" in row_simple.version_clave
    assert "|desglose=1|" in row_full.version_clave


def test_expired_completed_informe_is_ignored_by_cache_probe(
    informe_db: Session, monkeypatch
) -> None:
    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)
    user = _seed_user(informe_db, f"w5-exp-{uuid.uuid4().hex[:8]}@test.local")
    zona_id = _seed_zona(informe_db, "w5-zona-exp")

    row1, _ = service.crear_informe(
        informe_db,
        InformeAreaCreate(nombre="Vencido", zona_ids=[zona_id], desglose=True),
        usuario_id=user.id,
    )
    service.repo.actualizar_estado_if_actual(
        informe_db,
        row1.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.COMPLETED,
    )
    expired = informe_db.get(InformeArea, row1.id)
    assert expired is not None
    expired.vence_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    informe_db.flush()

    row2, desde_cache = service.crear_informe(
        informe_db,
        InformeAreaCreate(nombre="Nuevo", zona_ids=[zona_id], desglose=True),
        usuario_id=user.id,
    )
    assert desde_cache is False
    assert row2.id != row1.id


def test_calcular_version_clave_tracks_validacion_and_canales(informe_db: Session) -> None:
    from app.db.migrations.versions import zz_riesgo_validacion_evento as mig_val

    for stmt in mig_val.UPGRADE_STATEMENTS:
        informe_db.execute(text(stmt))
    informe_db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS canal_consorcio ("
            "id TEXT PRIMARY KEY, nombre TEXT NOT NULL, estado TEXT NOT NULL, "
            "prioridad TEXT, longitud_m DOUBLE PRECISION, "
            "geom geometry(LineString, 4326) NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    )
    informe_db.flush()

    baseline = service.calcular_version_clave(informe_db, "hash-abc", desglose=True)

    canal_id = f"canal-{uuid.uuid4().hex[:8]}"
    informe_db.execute(
        text(
            "INSERT INTO canal_consorcio (id, nombre, estado, geom, updated_at) "
            "VALUES (:id, 'Canal Test', 'relevado', "
            "ST_GeomFromText('LINESTRING(-61.2 -32.2, -61.1 -32.1)', 4326), "
            "TIMESTAMPTZ '2026-11-21 12:00:00+00')"
        ),
        {"id": canal_id},
    )
    after_canal = service.calcular_version_clave(informe_db, "hash-abc", desglose=True)
    assert after_canal != baseline

    informe_db.execute(
        text(
            "INSERT INTO riesgo_validacion_evento "
            "(id, evento_key, fecha, clase, ha_clase, ha_con_agua, pct_con_agua, sensor, "
            " escena_id, version_flood_risk, created_at) "
            "VALUES (gen_random_uuid(), :ek, DATE '2025-09-05', 'Alto', 100.0, 50.0, 50.0, "
            " 'sentinel2', 'SC1', 'v1', TIMESTAMPTZ '2026-11-21 13:00:00+00')"
        ),
        {"ek": f"ev-{uuid.uuid4().hex[:8]}"},
    )
    after_validacion = service.calcular_version_clave(informe_db, "hash-abc", desglose=True)
    assert after_validacion != after_canal


def test_crear_informe_acquires_advisory_lock_before_contar(
    informe_db: Session, monkeypatch
) -> None:
    events: list[str] = []
    real_exec = informe_db.execute
    real_contar = service.repo.contar_en_curso

    def spy_execute(statement, params=None, *args, **kwargs):
        if "pg_advisory_xact_lock" in str(statement):
            events.append("lock")
        return real_exec(statement, params, *args, **kwargs)

    def spy_contar(db, usuario_id):
        events.append("contar")
        return real_contar(db, usuario_id)

    monkeypatch.setattr(informe_db, "execute", spy_execute)
    monkeypatch.setattr(service.repo, "contar_en_curso", spy_contar)
    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)

    user = _seed_user(informe_db, f"w5-lock-{uuid.uuid4().hex[:8]}@test.local")
    zona_id = _seed_zona(informe_db, "w5-zona-lock")
    service.crear_informe(
        informe_db,
        InformeAreaCreate(nombre="Lock", zona_ids=[zona_id]),
        usuario_id=user.id,
    )
    assert events.index("lock") < events.index("contar")


def test_rfc5987_content_disposition_percent_encodes_slash_and_percent() -> None:
    ascii_pdf, utf8_pdf = service._nombre_archivo("Zona A/B 50%")
    ascii_kmz, utf8_kmz = service._nombre_archivo_kmz("Zona A/B 50%")
    assert ascii_pdf.endswith(".pdf")
    assert ascii_kmz.endswith(".kmz")
    assert "/" not in utf8_pdf
    assert "/" not in utf8_kmz
    assert "%2F" in utf8_pdf
    assert "%25" in utf8_pdf
    assert "%2F" in utf8_kmz
    assert "%25" in utf8_kmz


def test_public_campo_route_emits_private_no_cache_etag_304_and_redacts_logs(
    informe_db: Session, capsys, caplog, monkeypatch
) -> None:
    import logging

    from fastapi.testclient import TestClient

    from app.core.logging import redact_sensitive_path, sanitize_sensitive_data
    from app.db.session import get_db
    from app.main import app

    user = _seed_user(informe_db, f"w5-campo-{uuid.uuid4().hex[:8]}@test.local")
    zona_id = _seed_zona(informe_db, "w5-zona-campo")
    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)
    row, _ = service.crear_informe(
        informe_db,
        InformeAreaCreate(nombre="Campo Privado", zona_ids=[zona_id]),
        usuario_id=user.id,
    )
    paquete = b'{"version":1,"nombre":"Campo Privado","temas":{}}'
    service.repo.actualizar_estado_if_actual(
        informe_db,
        row.id,
        expected_estado=EstadoGeoJob.PENDING,
        estado=EstadoGeoJob.COMPLETED,
        campo_paquete=paquete,
    )

    secret_token = row.token_publico
    assert redact_sensitive_path(f"/api/v2/public/campo/{secret_token}") == (
        "/api/v2/public/campo/[REDACTED]"
    )
    assert redact_sensitive_path("/api/v2/geo/informes-area") == "/api/v2/geo/informes-area"
    sanitized = sanitize_sensitive_data(
        {
            "url": f"https://app.example/campo/{secret_token}?v=1",
            "nested": [f"/campo/{secret_token}"],
        }
    )
    assert secret_token not in str(sanitized)

    app.dependency_overrides[get_db] = lambda: informe_db
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    try:
        with caplog.at_level(logging.INFO, logger="app.core.middleware"):
            resp = client.get(f"/api/v2/public/campo/{secret_token}")
            assert resp.status_code == 200
            assert resp.headers["cache-control"] == "private, no-cache"
            etag = resp.headers["etag"]
            assert etag.startswith('"')
            assert "Accept-Encoding" in resp.headers.get("vary", "")

            not_mod = client.get(
                f"/api/v2/public/campo/{secret_token}",
                headers={"If-None-Match": etag},
            )
            assert not_mod.status_code == 304
            assert not_mod.content == b""
            assert not_mod.headers["etag"] == etag
            assert not_mod.headers["cache-control"] == "private, no-cache"

            weak_not_mod = client.get(
                f"/api/v2/public/campo/{secret_token}",
                headers={"If-None-Match": f"W/{etag}"},
            )
            assert weak_not_mod.status_code == 304
    finally:
        app.dependency_overrides.clear()

    server_records = [r for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
    combined_logs = (
        "\n".join(r.getMessage() for r in server_records)
        + "\n"
        + str([r.msg for r in server_records])
        + "\n"
        + capsys.readouterr().out
    )
    assert secret_token not in combined_logs
    assert "/api/v2/public/campo/[REDACTED]" in combined_logs
