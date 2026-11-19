"""Real-PostGIS + real-render tests for the informe de área PDF (PR 2, T2).

``odd/tasks/informe-area-pr2.md`` S6 (7 sections), S7 (maps), S8 (PDF
assertions) + S9 measured locally (this box is NOT prod — numbers are
printed for the report, the asserts stay loose on principle).

Covers, on top of T1's backend suite:

* the task end-to-end over a SEEDED world (class rasters, CHIRPS normals,
  soils band, composite rows) → ``completed`` with ``pdf_bytes``;
* pypdf text extraction (house pattern from ``test_pdf_es_ar``): folio
  "Página 1 de", the section titles IN ORDER, es-AR numbers (a
  thousands-separated total with comma decimal present, no English
  "N,NNN.N" anywhere), and the selection total matching ``resultado``
  (the same figure that lands in the tables, ±0,1 ha by construction);
* the KPIs the Resumen promises: constant rasters + full soil band make
  every KPI deterministic (100 % Crítico, 100 % drenaje Alto, 100 % I–III,
  100 mm);
* the download endpoint: ``application/pdf`` for the creator, the missing-id
  404 for another operator, admin sees it too;
* S9 cache hit: the second identical create reuses the row and the PDF
  download answers in < 1 s.

Real commits (the Celery task opens its own ``SessionLocal``) with a
dedicated world at lon -61.5 like T1 — plus, unlike T1, ``geo_layers`` rows
ARE committed here because the renderer cannot read a rolled-back layer.
They live in ``tmp_path`` (unique per test) and the finally block deletes
them by ``archivo_path``, so the "newest flood_risk" lookup other tests rely
on never sees this world's rasters after the test (the suite runs
sequentially — no xdist in addopts).
"""

from __future__ import annotations

import io
import re
import time
import uuid
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import delete, text
from sqlalchemy.orm import Session, sessionmaker

pypdf = pytest.importorskip("pypdf")

from app.auth.models import User, UserRole  # noqa: E402
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401, E402
from app.domains.geo.models import (  # noqa: E402
    FormatoGeoLayer,
    FuenteGeoLayer,
    GeoLayer,
    TipoGeoLayer,
)
from app.domains.geo.models import EstadoGeoJob  # noqa: E402
from app.domains.geo.informe_area import service, tasks  # noqa: E402
from app.domains.geo.informe_area.models import InformeArea  # noqa: E402
from app.domains.geo.informe_area.repository import InformeAreaRepository  # noqa: E402
from app.domains.geo.informe_area.schemas import InformeAreaCreate  # noqa: E402
from app.shared.celery_outbox import CeleryTaskOutbox  # noqa: E402
from app.shared.pdf.format_es import fmt_ha  # noqa: E402

INFORME_PATH = "/api/v2/geo/informes-area"

# Dedicated world (same discipline as test_informe_area.py: nothing else
# seeds near lon -61.5).
LON0, LAT0 = -61.5, -32.0
LADO = 0.05  # ≈ 2.617 ha per zona square → two zonas ≈ 5.2k ha → es-AR "5.2xx,x"
NODATA = -9999.0

SECCIONES = [
    "1. Resumen",
    "2. Riesgo hídrico",
    "3. Necesidad de drenaje",
    "4. Suelos",
    "5. Cobertura y cultivos",
    "6. Lluvia",
    "7. Canales",
    "8. Imágenes de eventos ancla",
    "9. Consideraciones",
    "10. Fuentes",
]

repo = InformeAreaRepository()


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def factory(test_engine):
    """Committing session factory (the task opens its own SessionLocal)."""
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


def _usuario(db: Session, email: str, role: UserRole = UserRole.OPERADOR) -> SimpleNamespace:
    row = User(
        email=email,
        hashed_password="test",
        role=role,
        nombre="T2",
        apellido="Informe",
        telefono="",
    )
    db.add(row)
    db.flush()
    return SimpleNamespace(id=row.id, role=role)


# ── seeding ─────────────────────────────────────────────────────────────────


def _seed_zona(db: Session, nombre: str, cuenca: str, x0: float, y0: float) -> uuid.UUID:
    zona_id = uuid.uuid4()
    wkt = (
        f"POLYGON(({x0} {y0}, {x0 + LADO} {y0}, {x0 + LADO} {y0 + LADO}, "
        f"{x0} {y0 + LADO}, {x0} {y0}))"
    )
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, :nombre, :cuenca, ST_GeomFromText(:wkt, 4326), 0.0)"
        ),
        {"id": zona_id, "nombre": nombre, "cuenca": cuenca, "wkt": wkt},
    )
    return zona_id


def _seed_suelos(db: Session) -> None:
    """Soils table (if the session's world lacks it) + one 'II' band covering the world.

    PR 4 (S3): section 4 reads the IDECOR 1:50.000 cartography, so the
    world ALSO seeds ``idecor_suelos_50mil`` with a class-'II' unit over
    the same extent — the KPI ``pct_suelos_i_iii == 100`` then holds
    through the NEW dataset (the migration's own DDL, applied committed so
    the Celery task's separate session can see it; dropped in ``_limpiar``).
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
    wkt = (
        f"MULTIPOLYGON((({LON0 - 0.02} {LAT0 - 0.02}, {LON0 + 0.2} {LAT0 - 0.02}, "
        f"{LON0 + 0.2} {LAT0 + 0.09}, {LON0 - 0.02} {LAT0 + 0.09}, "
        f"{LON0 - 0.02} {LAT0 - 0.02})))"
    )
    db.execute(
        text(
            "INSERT INTO suelos_catastro (simbolo, cap, geometria) "
            "VALUES (:sim, 'II', ST_GeomFromText(:wkt, 4326))"
        ),
        {"sim": "T2-II", "wkt": wkt},
    )
    from app.db.migrations.versions import zz_idecor_suelos_50mil as migracion_suelos

    for statement in migracion_suelos.UPGRADE_STATEMENTS:
        db.execute(text(statement))
    db.execute(
        text(
            "INSERT INTO idecor_suelos_50mil "
            "(id, simbolo, cu, clase, ip, au_1m, au_2m, serie_1, porc_1, nombre, "
            " tipo_unida, pdf_simbolo, pdf_serie_1, geometria) "
            "VALUES (9001, 'T2U', 'IIc', 'II', 90, 158, 292, 'SERIE T2', 100, "
            "        'Consociación SERIE T2', 'Consociación', 'T2U', 'SERIE_T2', "
            "        ST_GeomFromText(:wkt, 4326))"
        ),
        {"wkt": wkt},
    )


def _seed_composite(db: Session, zona_id: uuid.UUID, tipo: str, ha: float) -> None:
    db.execute(
        text(
            "INSERT INTO composite_zonal_stats "
            "(id, zona_id, tipo, fecha_calculo, mean_score, max_score, p90_score, "
            " area_high_risk_ha) "
            "VALUES (:id, :zona_id, :tipo, CURRENT_DATE, 50.0, 90.0, 70.0, :ha)"
        ),
        {"id": uuid.uuid4(), "zona_id": zona_id, "tipo": tipo, "ha": ha},
    )


def _raster_constante(directorio: Any, nombre: str, valor: float) -> str:
    path = directorio / nombre
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=200,
        width=260,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(LON0 - 0.05, LAT0 + 0.06, 0.001, 0.001),
        nodata=NODATA,
    ) as dst:
        dst.write(np.full((200, 260), valor, dtype="float32"), 1)
    return str(path)


def _registrar(db: Session, tipo: TipoGeoLayer, path: str, **extra: Any) -> None:
    db.add(
        GeoLayer(
            nombre=f"t2-{tipo.value}-{uuid.uuid4().hex[:6]}",
            tipo=tipo,
            fuente=FuenteGeoLayer.MANUAL,
            archivo_path=path,
            formato=FormatoGeoLayer.GEOTIFF,
            srid=4326,
            **extra,
        )
    )


def _seed_precip_normals(db: Session, directorio: Any) -> str:
    """Full 12+anual CHIRPS product (constant 100 mm) over the world."""
    ruta = str(directorio / "precip_t2.tif")
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
        _registrar(
            db,
            TipoGeoLayer.PRECIP_NORMAL,
            ruta,
            metadata_extra={"mes": mes, "version": "2026-01-01T00:00:00+00:00"},
            area_id="consorcio",
        )
    return ruta


def _sembrar_mundo(db: Session, tmp_path: Any) -> dict[str, Any]:
    """The whole T2 world: 2 zonas, class rasters, precip, soils, composites."""
    _seed_suelos(db)
    flood = _raster_constante(tmp_path, "flood.tif", 80.0)  # 80 → Crítico (75-100)
    drain = _raster_constante(tmp_path, "drain.tif", 60.0)  # 60 → Alto (50-70)
    _registrar(db, TipoGeoLayer.FLOOD_RISK, flood)
    _registrar(db, TipoGeoLayer.DRAINAGE_NEED, drain)
    precip = _seed_precip_normals(db, tmp_path)
    zona_a = _seed_zona(db, "alpha", "cuenca-t2", LON0, LAT0)
    zona_b = _seed_zona(db, "beta", "cuenca-t2", LON0 + LADO, LAT0)
    _seed_composite(db, zona_a, "flood_risk", 2600.0)
    _seed_composite(db, zona_a, "drainage_need", 2000.0)
    db.commit()
    return {"zona_a": zona_a, "zona_b": zona_b, "rasters": {flood, drain, precip}}


def _limpiar(factory, *, usuario_id, zona_ids, informe_ids, rasters) -> None:
    with factory() as db:
        db.execute(
            delete(CeleryTaskOutbox).where(CeleryTaskOutbox.task_key == "geo.informe_area.generar")
        )
        db.execute(
            delete(InformeArea).where(
                InformeArea.id.in_(informe_ids) | (InformeArea.usuario_id == usuario_id)
            )
        )
        db.execute(delete(GeoLayer).where(GeoLayer.archivo_path.in_(rasters)))
        db.execute(
            text("DELETE FROM composite_zonal_stats WHERE zona_id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(z) for z in zona_ids]},
        )
        if zona_ids:
            db.execute(
                text("DELETE FROM zonas_operativas WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(z) for z in zona_ids]},
            )
        db.execute(text("DELETE FROM suelos_catastro WHERE simbolo = 'T2-II'"))
        # PR 4 world: the seeded IDECOR carta row and its table leave with
        # the test (the table is created by _seed_suelos on demand).
        db.execute(text("DROP TABLE IF EXISTS idecor_suelos_50mil"))
        db.execute(delete(User).where(User.id == usuario_id))
        db.commit()


def _texto_pdf(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# ── task end-to-end + PDF content (S6/S7/S8) ────────────────────────────────


def test_tarea_completa_con_pdf_secciones_y_numeros_es_ar(factory, tmp_path, monkeypatch):
    """S8: task → completed with PDF; 7 sections in order; es-AR totals."""
    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)

    usuario_id = None
    zona_ids: list[uuid.UUID] = []
    informe_ids: list[uuid.UUID] = []
    rasters: set[str] = set()
    try:
        with factory() as db:
            mundo = _sembrar_mundo(db, tmp_path)
            zona_ids = [mundo["zona_a"], mundo["zona_b"]]
            rasters = mundo["rasters"]
            usuario = _usuario(db, f"informe-t2-{uuid.uuid4().hex[:8]}@test.local")
            db.commit()
            usuario_id = usuario.id

            row, desde_cache = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe cuenca t2", zona_ids=zona_ids),
                usuario_id=usuario_id,
            )
            informe_ids.append(row.id)
            assert desde_cache is False

        # S9 measurement #1: task wall time on this box (NOT prod).
        t0 = time.perf_counter()
        salida = tasks.generar_informe_area(str(informe_ids[0]))
        tarea_s = time.perf_counter() - t0
        assert salida["estado"] == "completed", salida

        with factory() as db:
            row = db.get(InformeArea, informe_ids[0])
            assert row.estado == EstadoGeoJob.COMPLETED
            assert row.error is None
            res = row.resultado
            assert res["kpis"]["pct_riesgo_alto_critico"] == 100.0  # raster cte 80 → Crítico
            assert res["kpis"]["pct_drenaje_alto_critico"] == 100.0  # cte 60 → Alto
            assert res["kpis"]["pct_suelos_i_iii"] == 100.0  # banda 'II' completa
            assert res["kpis"]["lluvia_anual_mm"] == 100.0  # normal cte 100 mm
            assert res["umbral_alto_critico"] == "legacy70"
            drenaje_fila = res["desglose"][0]["pct_drenaje_alto_critico"]
            assert drenaje_fila is not None and drenaje_fila > 0.0

            pdf_bytes = bytes(row.pdf_bytes)
            assert pdf_bytes[:5] == b"%PDF-"
            assert 0 < len(pdf_bytes) < 5_000_000  # S9: < 5 MB

            texto = _texto_pdf(pdf_bytes)
            assert "Página 1 de" in texto
            # The 7 section titles, IN ORDER (S6/S8).
            posiciones = [texto.find(titulo) for titulo in SECCIONES]
            assert all(pos != -1 for pos in posiciones), posiciones
            assert posiciones == sorted(posiciones), posiciones

            # Totals match resultado (±0,1 ha by construction: the same
            # figure the tables render, formatted es-AR).
            total_es_ar = fmt_ha(res["area_ha"])
            assert total_es_ar in texto, total_es_ar
            # es-AR shape present: thousands dot + comma decimal.
            assert re.search(r"\d\.\d{3},\d", total_es_ar), total_es_ar
            # No English "N,NNN.N" anywhere the totals live.
            assert not re.search(r"\d,\d{3}\.\d", texto)
            # The legacy70 note travels with the % Alto+Crítico figures (S12).
            assert "legacy70" in texto
            # Maps embedded: three images across the document.
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            imagenes = sum(len(page.images) for page in reader.pages)
            assert imagenes >= 3, imagenes

        print(
            f"\nS9 (box local, NO prod): tarea={tarea_s:.2f}s "
            f"pdf={len(pdf_bytes) / 1024:.0f} KiB seleccion={len(zona_ids)} zonas"
        )
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=zona_ids,
            informe_ids=informe_ids,
            rasters=rasters,
        )


def test_pdf_endpoint_creator_pdf_otro_operador_404_admin_ok(factory, tmp_path, monkeypatch):
    """S8/S11: application/pdf + filename for the creator; 404 for others."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)

    usuario_id = otro_id = None
    zona_ids: list[uuid.UUID] = []
    informe_ids: list[uuid.UUID] = []
    rasters: set[str] = set()
    try:
        with factory() as db:
            mundo = _sembrar_mundo(db, tmp_path)
            zona_ids = [mundo["zona_a"], mundo["zona_b"]]
            rasters = mundo["rasters"]
            creador = _usuario(db, f"informe-t2-ep-{uuid.uuid4().hex[:8]}@test.local")
            otro = _usuario(db, f"informe-t2-otro-{uuid.uuid4().hex[:8]}@test.local")
            admin = _usuario(
                db, f"informe-t2-adm-{uuid.uuid4().hex[:8]}@test.local", UserRole.ADMIN
            )
            db.commit()
            usuario_id, otro_id = creador.id, otro.id

            row, _ = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe endpoint", zona_ids=zona_ids),
                usuario_id=creador.id,
            )
            informe_ids.append(row.id)

        assert tasks.generar_informe_area(str(row.id))["estado"] == "completed"

        with factory() as db:
            fila = db.get(InformeArea, row.id)
            esperado = bytes(fila.pdf_bytes)

        with factory() as db:
            with TestClient(
                _app(db, SimpleNamespace(id=usuario_id, role=UserRole.OPERADOR))
            ) as cliente:
                rs = cliente.get(f"{INFORME_PATH}/{row.id}/pdf")
            assert rs.status_code == 200, rs.content[:200]
            assert rs.headers["content-type"].startswith("application/pdf")
            assert rs.headers["content-disposition"].startswith("attachment")
            assert "informe-endpoint" in rs.headers["content-disposition"]
            assert rs.content == esperado

        with factory() as db:
            with TestClient(
                _app(db, SimpleNamespace(id=otro_id, role=UserRole.OPERADOR))
            ) as cliente:
                rs_otro = cliente.get(f"{INFORME_PATH}/{row.id}/pdf")
        assert rs_otro.status_code == 404
        assert rs_otro.json()["codigo"] == "informe_no_encontrado"

        with factory() as db:
            with TestClient(_app(db, SimpleNamespace(id=admin.id, role=UserRole.ADMIN))) as cliente:
                rs_admin = cliente.get(f"{INFORME_PATH}/{row.id}/pdf")
        assert rs_admin.status_code == 200
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=zona_ids,
            informe_ids=informe_ids,
            rasters=rasters,
        )
        if otro_id:
            with factory() as db:
                db.execute(delete(User).where(User.id == otro_id))
                db.commit()


def test_cache_hit_descarga_pdf_menos_de_un_segundo(factory, tmp_path, monkeypatch):
    """S4 + S9: identical create → desde_cache, and the PDF answers < 1 s."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)

    usuario_id = None
    zona_ids: list[uuid.UUID] = []
    informe_ids: list[uuid.UUID] = []
    rasters: set[str] = set()
    try:
        with factory() as db:
            mundo = _sembrar_mundo(db, tmp_path)
            zona_ids = [mundo["zona_a"], mundo["zona_b"]]
            rasters = mundo["rasters"]
            usuario = _usuario(db, f"informe-t2-cache-{uuid.uuid4().hex[:8]}@test.local")
            db.commit()
            usuario_id = usuario.id
            row, _ = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe cache", zona_ids=zona_ids),
                usuario_id=usuario_id,
            )
            informe_ids.append(row.id)

        tasks.generar_informe_area(str(row.id))

        with factory() as db:
            row2, desde_cache = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe cache", zona_ids=zona_ids),
                usuario_id=usuario_id,
            )
            assert desde_cache is True
            assert row2.id == row.id

        with factory() as db:
            with TestClient(
                _app(db, SimpleNamespace(id=usuario_id, role=UserRole.OPERADOR))
            ) as cliente:
                t0 = time.perf_counter()
                rs = cliente.get(f"{INFORME_PATH}/{row.id}/pdf")
                descarga_s = time.perf_counter() - t0
        assert rs.status_code == 200
        assert rs.headers["content-type"].startswith("application/pdf")
        print(
            f"\nS9 (box local, NO prod): descarga cache-hit={descarga_s * 1000:.0f} ms "
            f"pdf={len(rs.content) / 1024:.0f} KiB"
        )
        assert descarga_s < 1.0
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=zona_ids,
            informe_ids=informe_ids,
            rasters=rasters,
        )
