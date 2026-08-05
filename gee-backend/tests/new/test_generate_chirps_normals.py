"""CHIRPS normals ETL runner: registration, warp target, regeneration, lookup.

Real PostgreSQL for the ``geo_layers`` registration and the month-scoped lookup;
Earth Engine and the raster download/warp I/O are injected fakes (no credentials,
no network, no GDAL). The tests pin the *contract* the design fixed:

* 13 rows registered as ``tipo = precip_normal`` with the exact ``metadata_extra``
  (JDB-011);
* the warp target is EPSG:32720 at 5 000 m, nearest, nodata ``-9999.0`` (JDB-018);
* regeneration appends a fresh ``version`` and does NOT overwrite the previous run
  (spec › "Regeneration versions the metadata");
* missing GEE credentials fail loudly with no partial layer registered (spec ›
  "Missing credentials fail loudly");
* the month-scoped lookup returns 12 distinct monthly rasters, the regression
  against the single-row "most recent layer of tipo X" idiom (JD-A-008).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.domains.geo import etl
from app.domains.geo.etl import generate_chirps_normals as gcn
from app.domains.geo.models import GeoLayer, TipoGeoLayer
from app.domains.geo.repository import GeoRepository

# Eagerly register the intelligence models (zonas table) so the session-scoped
# ``create_all`` can resolve ``flood_labels.zona_id`` when this file drives it.
import app.domains.geo.intelligence.models  # noqa: F401, E402

MESES = list(range(1, 13)) + ["anual"]


# ── Session whose COMMITs are savepoint-scoped (the runner commits) ──────────


@pytest.fixture
def chirps_db(test_engine) -> Session:
    """``generate_normals`` commits the batch; keep it inside the per-test rollback.

    Same restarting-savepoint recipe as ``test_ficha_compute.ficha_db``: the outer
    transaction stays open no matter how many times the runner commits.
    """
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


# ── Injected fakes ───────────────────────────────────────────────────────────

REGION = {
    "type": "Polygon",
    "coordinates": [[[-59, -35], [-58, -35], [-58, -34], [-59, -34], [-59, -35]]],
}

_RESAMPLING_NEAREST = object()  # sentinel: the runner must forward THIS, unchanged


def _fake_export(region: dict, *, start_year: int, end_year: int) -> list[dict]:
    assert region == REGION
    return [{"mes": mes, "download_url": f"https://earthengine.example/{mes}.tif"} for mes in MESES]


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int = 8192):
        yield b"\x00\x00\x00\x00"


class _FakeRequests:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, stream: bool = False, timeout: int | None = None) -> _FakeResponse:
        self.urls.append(url)
        return _FakeResponse()


class _FakeSrc:
    crs = "EPSG:4326"
    width = 20
    height = 18
    bounds = (-59.0, -35.0, -58.0, -34.0)
    transform = "SRC_TRANSFORM"

    @property
    def profile(self) -> dict:
        return {"driver": "GTiff", "dtype": "float32", "count": 1, "nodata": None}


class _Ctx:
    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def __enter__(self) -> Any:
        return self._obj

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeRasterio:
    def __init__(self, recorder: dict) -> None:
        self._recorder = recorder

    def open(self, path: str, mode: str = "r", **profile: Any) -> _Ctx:
        if mode == "w":
            self._recorder["write_profiles"].append(profile)
            return _Ctx(object())
        return _Ctx(_FakeSrc())

    def band(self, dataset: Any, index: int) -> tuple:
        return ("band", index)


def _make_recorder() -> dict:
    return {"calc": [], "reproject": [], "write_profiles": []}


def _fake_calc_factory(recorder: dict):
    def _calc(src_crs, dst_crs, width, height, *bounds, resolution=None):
        recorder["calc"].append({"src_crs": src_crs, "dst_crs": dst_crs, "resolution": resolution})
        return ("DST_TRANSFORM", 4, 3)

    return _calc


def _fake_reproject_factory(recorder: dict):
    def _reproject(**kwargs):
        recorder["reproject"].append(
            {
                "dst_crs": kwargs.get("dst_crs"),
                "dst_nodata": kwargs.get("dst_nodata"),
                "resampling": kwargs.get("resampling"),
            }
        )

    return _reproject


def _fixed_now(moment: datetime):
    return lambda: moment


def _run(
    db: Session,
    *,
    area_id: str,
    export_fn=_fake_export,
    now: datetime,
    recorder: dict | None = None,
    **anios: int,
) -> tuple[list[Any], _FakeRequests, dict]:
    recorder = recorder if recorder is not None else _make_recorder()
    requests = _FakeRequests()
    layers = gcn.generate_normals(
        db,
        region=REGION,
        area_id=area_id,
        export_fn=export_fn,
        **anios,
        requests_module=requests,
        rasterio_module=_FakeRasterio(recorder),
        calculate_default_transform_fn=_fake_calc_factory(recorder),
        reproject_fn=_fake_reproject_factory(recorder),
        resampling_nearest=_RESAMPLING_NEAREST,
        now_fn=_fixed_now(now),
    )
    return layers, requests, recorder


def _precip_rows(db: Session, area_id: str) -> list[GeoLayer]:
    stmt = select(GeoLayer).where(
        GeoLayer.tipo == TipoGeoLayer.PRECIP_NORMAL.value, GeoLayer.area_id == area_id
    )
    return list(db.execute(stmt).scalars().all())


# ── Registration as geo_layers + Full set generated ──────────────────────────


@pytest.fixture(autouse=True)
def _writable_geo_root(tmp_path, monkeypatch) -> None:
    """Redirect ``/data/geo`` to a tmp dir so the temp download is writable."""
    monkeypatch.setattr(gcn, "GEO_DATA_ROOT", str(tmp_path / "geo"))


def test_registers_thirteen_layers_one_per_month_plus_annual(chirps_db: Session) -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    layers, requests, _ = _run(chirps_db, area_id="area_reg", now=now)

    assert len(layers) == 13
    assert len(requests.urls) == 13  # one download per output, nothing skipped

    rows = _precip_rows(chirps_db, "area_reg")
    assert len(rows) == 13
    meses = sorted((r.metadata_extra["mes"] for r in rows), key=lambda m: (isinstance(m, str), m))
    assert meses == list(range(1, 13)) + ["anual"]

    for row in rows:
        meta = row.metadata_extra
        # DERIVED from the pipeline constants, not re-typed: the ficha serves this
        # very value as ``precipitacion_mensual.periodo`` (RISK-001), so a test
        # that hardcodes the years would stay green while the shipped label drifts.
        assert meta["normal_period"] == gcn.chirps_normal_period(
            gcn.DEFAULT_START_YEAR, gcn.DEFAULT_END_YEAR
        )
        assert meta["fuente"] == gcn.FUENTE_LABEL
        assert meta["resolucion_m"] == 5000
        assert meta["version"] == now.isoformat()
        assert row.srid == 32720
        assert row.tipo == TipoGeoLayer.PRECIP_NORMAL.value


def test_normal_period_records_the_years_this_run_used(chirps_db: Session) -> None:
    """``--start-year/--end-year`` travels with the rasters it produced (RISK-001).

    The stamp must come from the run's arguments, NOT from the module default:
    the ficha serves it verbatim, so a regeneration over a different period is
    exactly how the UI learns to say something else. If this ever falls back to
    the configured period, the browser starts lying about the age of the data
    again — the same defect, one layer down.
    """
    _run(
        chirps_db,
        area_id="area_periodo",
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
        start_year=2001,
        end_year=2030,
    )

    periodos = {r.metadata_extra["normal_period"] for r in _precip_rows(chirps_db, "area_periodo")}
    assert periodos == {"2001-2030"}
    assert "2001-2030" != gcn.chirps_normal_period(gcn.DEFAULT_START_YEAR, gcn.DEFAULT_END_YEAR)


def test_output_filenames_are_zero_padded_months_plus_anual(chirps_db: Session) -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    _run(chirps_db, area_id="area_files", now=now)

    paths = {r.metadata_extra["mes"]: r.archivo_path for r in _precip_rows(chirps_db, "area_files")}
    assert paths[1].endswith("/area_files/output/precip_normal_01.tif")
    assert paths[12].endswith("/area_files/output/precip_normal_12.tif")
    assert paths["anual"].endswith("/area_files/output/precip_normal_anual.tif")


# ── Warp target: EPSG:32720 @ 5 000 m, nearest, nodata -9999 (JDB-018) ────────


def test_warp_target_is_32720_5000m_nearest_nodata_minus_9999(chirps_db: Session) -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    _, _, recorder = _run(chirps_db, area_id="area_warp", now=now)

    assert len(recorder["calc"]) == 13
    assert len(recorder["reproject"]) == 13

    for call in recorder["calc"]:
        assert call["dst_crs"] == "EPSG:32720"
        assert call["resolution"] == 5000  # ~native CHIRPS; no upsampling

    for call in recorder["reproject"]:
        assert call["dst_crs"] == "EPSG:32720"
        assert call["dst_nodata"] == -9999.0
        assert call["resampling"] is _RESAMPLING_NEAREST  # never bilinear

    for profile in recorder["write_profiles"]:
        assert profile["crs"] == "EPSG:32720"
        assert profile["nodata"] == -9999.0
        assert profile["dtype"] == "float32"


# ── Regeneration versions the metadata (JDB-011) ─────────────────────────────


def test_regeneration_appends_a_new_version_without_overwriting(chirps_db: Session) -> None:
    v1 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    v2 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)

    _run(chirps_db, area_id="area_regen", now=v1)
    _run(chirps_db, area_id="area_regen", now=v2)

    rows = _precip_rows(chirps_db, "area_regen")
    # Both runs survive — the old rows are NOT silently overwritten.
    assert len(rows) == 26
    versions = {r.metadata_extra["version"] for r in rows}
    assert versions == {v1.isoformat(), v2.isoformat()}
    assert sum(1 for r in rows if r.metadata_extra["version"] == v1.isoformat()) == 13
    assert sum(1 for r in rows if r.metadata_extra["version"] == v2.isoformat()) == 13


# ── Missing credentials fail loudly, nothing registered ──────────────────────


def test_missing_credentials_fail_loudly_and_register_nothing(chirps_db: Session) -> None:
    def _no_creds(region: dict, *, start_year: int, end_year: int) -> list[dict]:
        # Mirrors gee_service._ensure_initialized: RuntimeError on absent creds.
        raise RuntimeError("GEE no disponible: credenciales ausentes")

    with pytest.raises(RuntimeError, match="GEE no disponible"):
        _run(chirps_db, area_id="area_nocreds", export_fn=_no_creds, now=datetime.now(timezone.utc))

    assert _precip_rows(chirps_db, "area_nocreds") == []


# ── Month-scoped lookup: 12 distinct rasters, not the single-row idiom ────────


def test_lookup_returns_twelve_distinct_monthly_rasters(chirps_db: Session) -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    _run(chirps_db, area_id="area_lookup", now=now)

    repo = GeoRepository()
    latest = repo.get_latest_precip_normals_by_month(chirps_db, "area_lookup")

    monthly_keys = {str(m) for m in range(1, 13)}
    assert monthly_keys.issubset(latest.keys())
    monthly_ids = {latest[str(m)].id for m in range(1, 13)}
    # 12 DISTINCT rasters — the regression against "most recent layer of tipo X",
    # which would return ONE row for all twelve months.
    assert len(monthly_ids) == 12
    assert "anual" in latest


def test_lookup_after_regeneration_returns_the_newest_version(chirps_db: Session) -> None:
    v1 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    v2 = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    _run(chirps_db, area_id="area_lookup2", now=v1)
    _run(chirps_db, area_id="area_lookup2", now=v2)

    repo = GeoRepository()
    latest = repo.get_latest_precip_normals_by_month(chirps_db, "area_lookup2")

    # One row per month even though 2 versions exist, and it is the newer one.
    assert {str(m) for m in range(1, 13)}.issubset(latest.keys())
    assert all(layer.metadata_extra["version"] == v2.isoformat() for layer in latest.values())


def test_etl_package_reexports_the_runner_module() -> None:
    # The runner must be importable as ``python -m …`` — a smoke check that the
    # package path resolves (JDB-002 execution-location contract).
    assert hasattr(etl, "__path__")
    assert gcn.main is not None
