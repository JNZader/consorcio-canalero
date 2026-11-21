"""Wave 5 tests for W-INF-05: calibration unmask/savepoints and IDECOR ETL atomicity/bounds."""

from __future__ import annotations

import importlib
import io
import uuid
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.transform import from_origin
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.domains.geo import calibracion_riesgo as cal
from app.domains.geo.etl import idecor_coberturas as etl_cob
from app.domains.geo.etl import idecor_suelos_50mil as etl_suelos
from app.domains.geo.etl import load_suelos_catastro as loader
from app.domains.geo.class_breaks import RANGE_CONFIGS
from tests.new.fixtures.informe_area_pr4 import wcs_coberturas, wfs_suelos


def _write_tif_file(
    path,
    arr: np.ndarray,
    *,
    crs: str | None = "EPSG:32720",
    transform: Affine | None = None,
    nodata: float | int | None = -9999.0,
) -> str:
    transform = transform or from_origin(500000.0, 6400000.0, 10.0, 10.0)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype=arr.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(arr, 1)
    return str(path)


def _write_tif_bytes(
    arr: np.ndarray,
    *,
    crs: str | None = "EPSG:32720",
    transform: Affine | None = None,
    nodata: int | float | None = cal.AGUA_NODATA,
) -> bytes:
    transform = transform or from_origin(500000.0, 6400000.0, 10.0, 10.0)
    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype=arr.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(arr, 1)
    return buf.getvalue()


def test_clasificar_agua_excludes_agua_nodata_from_denominator(tmp_path):
    """Masked water pixels (AGUA_NODATA=255) must not bias pct_con_agua toward zero."""
    cfgs = RANGE_CONFIGS["flood_risk"]
    bajo = float(cfgs[0]["min"]) + 0.1
    medio = float(cfgs[1]["min"]) + 0.1
    alto = float(cfgs[2]["min"]) + 0.1
    critico = float(cfgs[3]["min"]) + 0.1

    # 2x10 grid: row 0 = 10 Alto pixels; row 1 = Bajo/Medio/Critico (zero/full observed checks).
    flood = np.array(
        [
            [alto] * 10,
            [bajo, bajo, medio, medio, critico, critico, critico, critico, -9999.0, -9999.0],
        ],
        dtype=np.float32,
    )
    # In Alto (row 0): 4 pixels AGUA_NODATA (255), 3 wet (1), 3 dry (0) -> 3/6 = 50.0%.
    # In Bajo: all AGUA_NODATA -> 0.0% without ZeroDivisionError.
    # In Medio: 1 wet (1), 1 AGUA_NODATA -> 100.0%.
    # In Critico: 2 wet, 2 dry -> 50.0%.
    agua = np.array(
        [
            [255, 255, 255, 255, 1, 1, 1, 0, 0, 0],
            [255, 255, 1, 255, 1, 1, 0, 0, 0, 0],
        ],
        dtype=np.uint8,
    )
    flood_path = _write_tif_file(tmp_path / "flood.tif", flood)
    agua_bytes = _write_tif_bytes(agua)

    filas = {f.clase: f for f in cal.clasificar_agua_por_clase(flood_path, agua_bytes)}

    # 10m x 10m = 0.01 ha/px
    assert filas["Alto"].ha_clase == pytest.approx(0.10, abs=1e-4)
    assert filas["Alto"].ha_con_agua == pytest.approx(0.03, abs=1e-4)
    assert filas["Alto"].pct_con_agua == 50.0
    assert filas["Bajo"].pct_con_agua == 0.0
    assert filas["Medio"].pct_con_agua == 100.0
    assert filas["Crítico"].pct_con_agua == 50.0


def test_clasificar_agua_rejects_crs_and_transform_mismatch(tmp_path):
    flood = np.full((4, 4), float(RANGE_CONFIGS["flood_risk"][2]["min"]) + 0.1, dtype=np.float32)
    flood_path = _write_tif_file(tmp_path / "flood.tif", flood)
    agua = np.ones((4, 4), dtype=np.uint8)

    bad_crs_bytes = _write_tif_bytes(agua, crs="EPSG:4326")
    with pytest.raises(ValueError, match="grilla de agua"):
        cal.clasificar_agua_por_clase(flood_path, bad_crs_bytes)

    shifted_transform = from_origin(500050.0, 6400000.0, 10.0, 10.0)
    bad_transform_bytes = _write_tif_bytes(agua, transform=shifted_transform)
    with pytest.raises(ValueError, match="grilla de agua"):
        cal.clasificar_agua_por_clase(flood_path, bad_transform_bytes)


def test_mascara_agua_gee_unmasks_with_sentinel_255_for_s1_and_optical(monkeypatch):
    from app.domains.geo import gee_service

    monkeypatch.setattr(gee_service, "_ensure_initialized", lambda: None)
    unmask_calls: list[int] = []

    class _FakeImg:
        def select(self, _band):
            return self

        def divide(self, _other):
            return self

        def subtract(self, _other):
            return self

        def add(self, _other):
            return self

        def lt(self, _threshold):
            return self

        def gte(self, _threshold):
            return self

        def unmask(self, value: int):
            unmask_calls.append(value)
            return self

        def toByte(self):  # noqa: N802 — mirrors Earth Engine API
            return self

        def rename(self, _name: str):
            return self

        def getDownloadURL(self, _params):  # noqa: N802 — mirrors Earth Engine API
            return "http://gee.invalid/water.tif"

    class _FakeCollection:
        def filter(self, _flt):
            return self

        def size(self):
            return SimpleNamespace(getInfo=lambda: 1)

        def first(self):
            return _FakeImg()

    fake_ee = SimpleNamespace(
        ImageCollection=lambda _name: _FakeCollection(),
        Filter=SimpleNamespace(eq=lambda k, v: (k, v)),
    )
    fake_requests = SimpleNamespace(
        get=lambda _url, timeout=180: SimpleNamespace(
            content=b"II-fake-tif", raise_for_status=lambda: None
        )
    )
    grilla = cal.GrillaRiesgo(
        width=4,
        height=4,
        crs="EPSG:32720",
        transform=(10.0, 0.0, 500000.0, 0.0, -10.0, 6400000.0),
    )

    assert (
        cal.mascara_agua_gee(
            "sentinel1", "S1_A", grilla, ee_module=fake_ee, requests_module=fake_requests
        )
        == b"II-fake-tif"
    )
    assert (
        cal.mascara_agua_gee(
            "landsat8", "LC08_B", grilla, ee_module=fake_ee, requests_module=fake_requests
        )
        == b"II-fake-tif"
    )
    assert cal.AGUA_NODATA == 255
    assert unmask_calls == [cal.AGUA_NODATA, cal.AGUA_NODATA]


def test_run_calibracion_savepoint_isolates_db_failure_per_event(
    db: Session, tmp_path, monkeypatch
):
    """A DB IntegrityError during one event's DELETE+INSERT must roll back ONLY that savepoint."""
    from datetime import date

    from app.db.migrations.versions import zz_riesgo_validacion_evento

    for statement in zz_riesgo_validacion_evento.UPGRADE_STATEMENTS:
        db.execute(text(statement))
    db.flush()

    cfgs = RANGE_CONFIGS["flood_risk"]
    flood = np.array(
        [[float(cfgs[i]["min"]) + 0.1 for i in range(4)] for _ in range(2)],
        dtype=np.float32,
    )
    flood_path = _write_tif_file(tmp_path / "flood.tif", flood)
    grilla = cal.leer_grilla_riesgo(flood_path)
    agua_bytes = _write_tif_bytes(np.ones((2, 4), dtype=np.uint8))

    for idx, key in enumerate(("cal_sp_bad", "cal_sp_ok")):
        fecha = date(2015 + idx, 3, 15)
        db.execute(
            text(
                "INSERT INTO rainfall_extreme_event "
                "(id, source_id, scope_kind, scope_id, scope_version, detector_revision, "
                " provenance, event_key, start_date, end_date, curated_payload) "
                "VALUES (gen_random_uuid(), 'chirps', 'provider_asset', 'z', 'v1', 'curated', "
                "        'curated', :k, :d, :d, '{}')"
            ),
            {"k": key, "d": fecha},
        )
        db.execute(
            text(
                "INSERT INTO rainfall_event_imagery_candidate "
                "(id, event_key, scorer_revision, sensor, scene_id, scene_date, "
                " days_from_peak, cloud_pct, cloud_basis, score, rank, visualization, slot) "
                "VALUES (gen_random_uuid(), :k, 'w5', 'landsat8', :sc, :d, 0, 5.0, "
                "        'scene', 99.0, 1, 'falso_color', 'ranked')"
            ),
            {"k": key, "sc": f"SC_{key}", "d": fecha},
        )
    # Pre-existing row for cal_sp_bad that must survive if its DELETE+INSERT savepoint rolls back.
    db.execute(
        text(
            "INSERT INTO riesgo_validacion_evento "
            "(id, evento_key, fecha, clase, ha_clase, ha_con_agua, pct_con_agua, "
            " lluvia_30d_mm, sensor, escena_id, version_flood_risk) "
            "VALUES (:id, 'cal_sp_bad', CAST('2015-03-15' AS date), 'Crítico', "
            "        1.0, 0.5, 50.0, 100.0, 'landsat8', 'SC_OLD', 'v0')"
        ),
        {"id": uuid.uuid4()},
    )
    db.flush()

    orig_clasificar = cal.clasificar_agua_por_clase
    calls = 0

    def _clasificar_falla_una(fp: str, ab: bytes):
        nonlocal calls
        calls += 1
        filas = orig_clasificar(fp, ab)
        if calls == 1:
            # Force NotNullViolation on flush AFTER BORRAR_EVENTO_SQL already executed.
            filas[0] = cal.FilaClase(
                clase=None,  # type: ignore[arg-type]
                ha_clase=filas[0].ha_clase,
                ha_con_agua=filas[0].ha_con_agua,
                pct_con_agua=filas[0].pct_con_agua,
            )
        return filas

    monkeypatch.setattr(cal, "clasificar_agua_por_clase", _clasificar_falla_una)

    res = cal.run_calibracion(
        db,
        fetch_agua=lambda _s, _sc, _g: agua_bytes,
        fetch_lluvia=lambda _f: 120.0,
        flood_path=flood_path,
        version_flood_risk="v-sp",
    )

    por_key = {e["evento_key"]: e for e in res["eventos"]}
    assert por_key["cal_sp_bad"]["filas"] == 0
    assert "IntegrityError" in str(por_key["cal_sp_bad"]["motivo"])
    assert por_key["cal_sp_ok"]["filas"] == 4

    # Pre-existing row on cal_sp_bad stayed intact (DELETE was inside the rolled-back savepoint).
    old_bad = db.execute(
        text("SELECT escena_id FROM riesgo_validacion_evento WHERE evento_key = 'cal_sp_bad'")
    ).scalar_one()
    assert old_bad == "SC_OLD"
    # Second event committed inside the outer transaction cleanly.
    ok_count = db.execute(
        text("SELECT count(*) FROM riesgo_validacion_evento WHERE evento_key = 'cal_sp_ok'")
    ).scalar_one()
    assert ok_count == 4
    assert grilla.width == 4


def test_idecor_coberturas_bajar_atomic_staging_preserves_existing_files(db: Session, tmp_path):
    """If layer 3 fails, previous .tif files remain untouched and zero .tmp.tif stay on disk."""
    zona_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, 'w5-cob', 'c-w5', ST_GeomFromText('POLYGON((-61.5 -32.0, -61.45 -32.0, "
            "-61.45 -31.95, -61.5 -31.95, -61.5 -32.0))', 4326), 0.0)"
        ),
        {"id": zona_id},
    )
    db.flush()

    data_root = tmp_path / "idecor"
    data_root.mkdir(parents=True, exist_ok=True)
    uso_final = data_root / "uso_2024_2025.tif"
    est_final = data_root / "estival_2223.tif"
    uso_final.write_bytes(b"SENTINEL-USO-PREV")
    est_final.write_bytes(b"SENTINEL-2223-PREV")

    def fetch_bytes(url: str) -> bytes:
        if "coberturas_estivales_2324" in url:
            raise RuntimeError("IDECOR down on 3rd layer")
        return wcs_coberturas.geotiff_de_pintura(
            lambda xs, _ys: np.ones_like(xs, dtype=np.uint8), url, dtype="uint8", nodata=255
        )

    def fetch_json(_url: str) -> dict[str, Any]:
        return wcs_coberturas.leyenda_wms(wcs_coberturas.LEYENDA_ESTIVAL_TARDIA)

    with pytest.raises(RuntimeError, match="IDECOR down on 3rd layer"):
        etl_cob.bajar_coberturas(
            db,
            data_root=data_root,
            fetch_bytes=fetch_bytes,
            fetch_json=fetch_json,
        )

    assert uso_final.read_bytes() == b"SENTINEL-USO-PREV"
    assert est_final.read_bytes() == b"SENTINEL-2223-PREV"
    assert list(data_root.glob("*.tmp.tif")) == []


def test_idecor_suelos_50mil_aborts_on_repeated_wfs_page():
    """A server ignoring startIndex (returning the same page forever) must fail fast."""
    bbox = (-61.51, -32.01, -61.44, -31.94)
    lote = [wfs_suelos.feature_suelo(100 + i, bbox) for i in range(3)]
    llamadas = 0

    def fetch_same_page(_url: str) -> dict[str, Any]:
        nonlocal llamadas
        llamadas += 1
        return wfs_suelos.pagina_wfs(lote)

    with pytest.raises(etl_suelos.EtlAssertionError, match="repetida"):
        etl_suelos.bajar_features(bbox, fetch_json=fetch_same_page, page_size=3, max_features=100)

    assert llamadas == 2

    # Clean empty trailing page terminates normally.
    pages = [wfs_suelos.pagina_wfs(lote), wfs_suelos.pagina_wfs([])]
    features = etl_suelos.bajar_features(
        bbox, fetch_json=lambda _u: pages.pop(0), page_size=3, max_features=100
    )
    assert len(features) == 3


def test_load_suelos_catastro_restores_statement_timeout_on_success_and_error(test_engine):
    """Pooled PG connection must recover its prior statement_timeout after refresh_materialized_view."""
    migration_17 = importlib.import_module("app.db.migrations.versions.0017_ficha_territorial_prep")
    url = test_engine.url.render_as_string(hide_password=False)
    dedicated = create_engine(url, pool_size=1, max_overflow=0)
    zona_id: uuid.UUID | None = None
    try:
        # Establish baseline session timeout on the sole pooled connection.
        with dedicated.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            pid_0 = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
            conn.execute(text("SET statement_timeout = '42s'"))
            conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_suelos_por_zona"))
            conn.execute(text("DROP TABLE IF EXISTS suelos_catastro"))
            conn.execute(
                text(
                    "CREATE TABLE suelos_catastro ("
                    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                    "simbolo VARCHAR(50) NOT NULL, "
                    "cap VARCHAR(10), "
                    "ip VARCHAR(50), "
                    "geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL)"
                )
            )
            zona_id = conn.execute(
                text(
                    "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
                    "VALUES (gen_random_uuid(), 'w5-mv-test', 'c-w5', "
                    "ST_GeomFromText('POLYGON((-63 -33, -62 -33, -62 -32, -63 -32, -63 -33))', 4326), 0) "
                    "RETURNING id"
                )
            ).scalar_one()
            for stmt in migration_17.RECREATE_MV_STATEMENTS:
                conn.execute(text(stmt))

        local_session = sessionmaker(bind=dedicated)
        with local_session() as s:
            assert loader.refresh_materialized_view(s) == 0

        with dedicated.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            assert conn.execute(text("SELECT pg_backend_pid()")).scalar_one() == pid_0
            assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "42s"
            # Drop the MV so both CONCURRENTLY and plain REFRESH fail; timeout still must restore.
            conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_suelos_por_zona"))

        with local_session() as s:
            with pytest.raises(Exception):
                loader.refresh_materialized_view(s)

        with dedicated.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            assert conn.execute(text("SELECT pg_backend_pid()")).scalar_one() == pid_0
            assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "42s"
    finally:
        with dedicated.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("RESET statement_timeout"))
            conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_suelos_por_zona"))
            conn.execute(text("DROP TABLE IF EXISTS suelos_catastro"))
            if zona_id is not None:
                conn.execute(
                    text("DELETE FROM zonas_operativas WHERE id = :id"),
                    {"id": zona_id},
                )
        dedicated.dispose()
