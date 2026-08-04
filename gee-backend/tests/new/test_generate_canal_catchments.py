"""Batch tests for the canal_cuenca precompute engine (A7, curated retarget).

Real PostgreSQL for the ``canal_catchment`` registration and the resumability
key; WhiteboxTools and the raster I/O (open/rasterize/shapes) are injected fakes —
no GDAL, no WBT binary, no scratch files. The tests pin the contract the design
fixed:

* the batch iterates the curated ``canal_consorcio`` registry (60 canals in prod),
  keyed by the string ``canal_ref`` — NOT the old ``canal_network`` int graph;
* the watershed is seeded with the D8 POINTER (flow_dir), never the DEM
  (the A7 "D8 blocker" regression);
* v1 computes every catchment against the natural ``natural_flow_dir_{area}`` raster
  and stamps ``variante = 'natural'``;
* a normal canal yields a MultiPolygon catchment with the right ``area_ha``;
* an oversized basin (> ``ficha_max_area_ha``) is stored ``oversized`` with a NULL
  geometry — the multi-MB polygon is dropped;
* re-running with the same ``flow_dir`` version SKIPS done canals (idempotent /
  resumable) and RECOMPUTES when the pointer version changes;
* ``--estado`` scopes which canals are processed without changing the raster.
"""

from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pytest
from shapely.geometry import Point, Polygon, mapping
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.etl import generate_canal_catchments as gcc
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, TipoGeoLayer
from app.domains.geo.repository import GeoRepository

# Eagerly register intelligence models so ``create_all`` builds every geo table.
import app.domains.geo.intelligence.models  # noqa: F401, E402

_MIGRATION = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")

AREA = "cc_test_area"
FLOW_DIR_PATH = "/data/geo/cc_test_area/output/flow_dir.tif"
_GRID = (100, 100)  # (height, width)

# A 300 m × 400 m rectangle in EPSG:32720 (UTM 20S) → 120 000 m² → exactly 12 ha.
_NORMAL_POLY = Polygon([(500000, 6000000), (500300, 6000000), (500300, 6000400), (500000, 6000400)])
# A 30 km × 10 km rectangle → 3e8 m² → 30 000 ha, over the 20 000 ha cap.
_OVERSIZED_POLY = Polygon(
    [(500000, 6000000), (530000, 6000000), (530000, 6010000), (500000, 6010000)]
)
# A 400 m-radius disc approximated with 1200 segments (>1000 raw vertices) →
# ~50 ha, area/envelope-valid but WAY over the vertices cap as raw pixel geometry.
# After the batch's topology-preserving simplify it collapses to a handful of
# vertices, so it is stored servably (the "stored ⟹ under read caps" invariant).
_HIGH_VERTEX_POLY = Point(500000, 6000000).buffer(400.0, quad_segs=300)


# ── injected raster/WBT fakes ────────────────────────────────────────────────


class _Ctx:
    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def __enter__(self) -> Any:
        return self._obj

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeCRS:
    def to_epsg(self) -> int:
        return 32720


class _GeographicCRS:
    """A geographic (degrees) CRS — the misconfiguration the CRS guard refuses."""

    def to_epsg(self) -> int:
        return 4326  # WGS84 lat/lon — NOT metric


class _FakeFlowDirSrc:
    crs = _FakeCRS()
    transform = "AFFINE"
    width = _GRID[1]
    height = _GRID[0]
    meta = {"driver": "GTiff", "dtype": "float32", "count": 1, "nodata": None}

    def read(self, _index: int) -> np.ndarray:
        return np.ones(_GRID, dtype=np.int16)


class _FakeBasinsSrc:
    transform = "AFFINE"

    def read(self, _index: int) -> np.ndarray:
        return np.ones(_GRID, dtype=np.int16)


class _FakeWriter:
    def write(self, _arr: np.ndarray, _index: int) -> None:
        pass


class _FakeRasterio:
    def open(self, path: str, mode: str = "r", **_profile: Any) -> _Ctx:
        if mode == "w":
            return _Ctx(_FakeWriter())
        if "basins" in path:
            return _Ctx(_FakeBasinsSrc())
        return _Ctx(_FakeFlowDirSrc())


class _FakeGeographicFlowDirSrc(_FakeFlowDirSrc):
    crs = _GeographicCRS()


class _FakeGeographicRasterio(_FakeRasterio):
    def open(self, path: str, mode: str = "r", **_profile: Any) -> _Ctx:
        if mode == "w":
            return _Ctx(_FakeWriter())
        if "basins" in path:
            return _Ctx(_FakeBasinsSrc())
        return _Ctx(_FakeGeographicFlowDirSrc())


def _fake_rasterize(_shapes, *, out_shape, transform, fill, dtype, all_touched):
    return np.ones(out_shape, dtype="int16")


class _RecordingWbt:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def watershed(self, *args: Any) -> None:
        self.calls.append(args)


def _shapes_returning(*polygons: Polygon):
    payload = [(mapping(poly), 1) for poly in polygons]

    def _shapes(*_a: Any, **_k: Any):
        return list(payload)

    return _shapes


# ── real-PG fixture (the batch commits per canal → restarting savepoints) ─────


@pytest.fixture
def catchment_db(test_engine) -> Session:
    # ``join_transaction_mode="create_savepoint"`` (SQLAlchemy 2.0) keeps every
    # session.commit()/rollback() the batch issues inside a SAVEPOINT nested in the
    # outer transaction — so the per-canal commit AND the per-canal failure
    # rollback both work without escaping to (or dropping) the fixture DDL.
    connection = test_engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    # canal_consorcio + canal_catchment are migration-only (no ORM model); build
    # them from 0020's real DDL. geo_layers already exists (ORM model) as the FK
    # target of flow_dir_layer_id.
    for statement in _MIGRATION.UPGRADE_STATEMENTS:
        session.execute(text(statement))
    session.commit()  # release the DDL savepoint → committed floor a rollback can't undo

    yield session

    session.close()
    trans.rollback()
    connection.close()


def _register_flow_dir(db: Session, nombre: str = f"natural_flow_dir_{AREA}") -> str:
    layer = GeoRepository().create_layer(
        db,
        nombre=nombre,
        tipo=TipoGeoLayer.FLOW_DIR.value,
        fuente=FuenteGeoLayer.DEM_PIPELINE.value,
        archivo_path=FLOW_DIR_PATH,
        formato=FormatoGeoLayer.GEOTIFF.value,
        srid=32720,
        area_id=AREA,
    )
    db.flush()
    return str(layer.id)


def _seed_canal(
    db: Session,
    canal_ref: str,
    *,
    estado: str = "relevado",
    wkt: str = "LINESTRING(-62.0 -33.0, -62.01 -33.01)",
) -> None:
    db.execute(
        text(
            "INSERT INTO canal_consorcio (id, nombre, estado, geom) "
            "VALUES (:id, :n, :estado, ST_GeomFromText(:wkt, 4326))"
        ),
        {"id": canal_ref, "n": f"canal {canal_ref}", "estado": estado, "wkt": wkt},
    )


def _row(db: Session, canal_ref: str, variante: str = "natural"):
    return db.execute(
        text(
            "SELECT area_ha, oversized, version, flow_dir_layer_id, "
            "geometria IS NULL AS geom_null, "
            "GeometryType(geometria) AS geom_type "
            "FROM canal_catchment WHERE canal_ref = :ref AND variante = :v"
        ),
        {"ref": canal_ref, "v": variante},
    ).one_or_none()


def _run(db: Session, wbt: _RecordingWbt, shapes_fn, **kwargs) -> gcc.BatchResult:
    return gcc.generate_catchments(
        db,
        area_id=AREA,
        rasterio_module=_FakeRasterio(),
        rasterize_fn=_fake_rasterize,
        shapes_fn=shapes_fn,
        get_wbt=lambda: wbt,
        **kwargs,
    )


class _SessionLocalStub:
    """Stand in for ``app.db.session.SessionLocal`` so ``main()`` reuses the test
    session (a real-PG connection) instead of opening its own engine."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def __call__(self) -> "_SessionLocalStub":
        return self

    def __enter__(self) -> Session:
        return self._session

    def __exit__(self, *_exc: Any) -> bool:
        return False  # never close/rollback — the fixture owns the session


def _run_main(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    wbt: _RecordingWbt,
    shapes_fn,
    *,
    argv: list[str] | None = None,
) -> int:
    """Drive the CLI ``main(argv=...)`` so the exit-code mapping itself is
    exercised, injecting the raster/WBT fakes through ``_resolve_io``."""
    monkeypatch.setattr("app.db.session.SessionLocal", _SessionLocalStub(db))
    monkeypatch.setattr(
        gcc,
        "_resolve_io",
        lambda *_a, **_k: (_FakeRasterio(), _fake_rasterize, shapes_fn, lambda: wbt),
    )
    return gcc.main(argv=argv if argv is not None else ["--area-id", AREA])


# ── tests ────────────────────────────────────────────────────────────────────


def test_normal_canal_yields_catchment_with_correct_area(catchment_db: Session) -> None:
    version = _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    wbt = _RecordingWbt()
    result = _run(catchment_db, wbt, _shapes_returning(_NORMAL_POLY))

    assert result.total == 1
    assert result.computed == 1
    assert result.oversized == 0
    assert result.failed == 0

    row = _row(catchment_db, "canal-a")
    assert row is not None
    assert row.area_ha == pytest.approx(12.0)
    assert row.oversized is False
    assert row.geom_null is False
    assert row.geom_type == "MULTIPOLYGON"  # stored as MultiPolygon in 4326
    assert row.version == version
    assert str(row.flow_dir_layer_id) == version


def test_variante_stamped_is_v1_natural(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    # Even a PROPUESTO canal is stored with variante='natural' in v1 (computed
    # against the natural flow_dir, not a per-canal escenario).
    _seed_canal(catchment_db, "canal-prop", estado="propuesto")

    _run(catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))

    stored_variante = catchment_db.execute(
        text("SELECT variante FROM canal_catchment WHERE canal_ref = 'canal-prop'")
    ).scalar_one()
    assert stored_variante == gcc.V1_VARIANTE == "natural"


def test_watershed_is_seeded_with_flow_dir_not_dem(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    wbt = _RecordingWbt()
    _run(catchment_db, wbt, _shapes_returning(_NORMAL_POLY))

    assert wbt.calls, "watershed was never called"
    assert wbt.calls[0][0] == FLOW_DIR_PATH, "watershed arg 1 must be the flow_dir pointer"


def test_oversized_basin_stored_without_geometry(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    wbt = _RecordingWbt()
    result = _run(catchment_db, wbt, _shapes_returning(_OVERSIZED_POLY))

    assert result.computed == 1
    assert result.oversized == 1

    row = _row(catchment_db, "canal-a")
    assert row is not None
    assert row.area_ha == pytest.approx(30000.0)
    assert row.oversized is True
    assert row.geom_null is True  # multi-MB geometry dropped


def test_high_vertex_basin_is_simplified_and_stored_under_read_caps(
    catchment_db: Session,
) -> None:
    """A realistic high-vertex basin (raw pixel staircase) must be simplified so the
    STORED catchment stays under ``ficha_max_vertices`` — the core producer/consumer
    invariant: a non-oversized stored catchment is guaranteed servable by the
    ``canal_cuenca`` ficha (``assert_within_caps``). Without the batch simplify this
    stores a >1000-vertex geometry the read path would 422 on."""
    from app.config import settings
    from app.domains.geo.ficha_service import _contar_vertices_shapely

    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    # Sanity: the raw basin really is over the read-path vertices cap.
    assert _contar_vertices_shapely(_HIGH_VERTEX_POLY) > settings.ficha_max_vertices

    result = _run(catchment_db, _RecordingWbt(), _shapes_returning(_HIGH_VERTEX_POLY))
    assert result.computed == 1
    assert result.oversized == 0

    row = catchment_db.execute(
        text(
            "SELECT oversized, geometria IS NULL AS geom_null, "
            "ST_NPoints(geometria) AS npoints "
            "FROM canal_catchment WHERE canal_ref = 'canal-a' AND variante = 'natural'"
        )
    ).one()
    assert row.oversized is False
    assert row.geom_null is False  # simplified → servable, geometry kept
    # The stored geometry passes the read-path vertices cap (stored ⟹ servable).
    assert row.npoints <= settings.ficha_max_vertices


# ── B4d: the simplify tolerance is the lever that rescues the vertex-capped ──
#
# The per-motivo breakdown of the prod re-run measured
# ``{area: 16, envelope: 0, vertices: 35}``: EVERY oversized catchment fails the
# vertex cap, the envelope cap rejects nothing at all, and 19 of the 35 have a
# perfectly sane area. Those 19 are rescuable by simplifying harder — WITHOUT
# moving any cap, so the "stored ⟹ servable" invariant is untouched.

#: Cell size of the flow_dir grid (COPERNICUS/DEM/GLO30), in metres.
_FLOW_DIR_CELL_M = 30.0
#: The tolerance this ETL used before B4d, still used by the soils on-map overlay.
_LEGACY_SOILS_TOLERANCE_M = 8.0


def _pixel_staircase_basin(radius_m: float = 3000.0):
    """A REALISTIC raw catchment: a lobed basin traced as a pixel staircase.

    ``_HIGH_VERTEX_POLY`` is a smooth disc, and a smooth disc simplifies the same
    at 8 m and at 20 m — it cannot show what the tolerance change buys. A real
    watershed boundary is the outline of a set of ``_FLOW_DIR_CELL_M`` cells: an
    orthogonal staircase whose every corner sits ~half a cell off the underlying
    curve. That is the shape the vertex cap actually rejects.
    """
    import math

    from shapely.geometry import Polygon as _Polygon

    ring: list[tuple[float, float]] = []
    prev: tuple[float, float] | None = None
    samples = 12_000
    for k in range(samples + 1):
        theta = 2 * math.pi * k / samples
        r = radius_m * (1 + 0.35 * math.sin(9 * theta))
        x = round(r * math.cos(theta) / _FLOW_DIR_CELL_M) * _FLOW_DIR_CELL_M
        y = round(r * math.sin(theta) / _FLOW_DIR_CELL_M) * _FLOW_DIR_CELL_M
        if prev == (x, y):
            continue
        if prev is not None and x != prev[0] and y != prev[1]:
            # Diagonal moves do not exist on a pixel boundary: insert the corner.
            ring.append((500_000 + x, 6_000_000 + prev[1]))
        ring.append((500_000 + x, 6_000_000 + y))
        prev = (x, y)
    return _Polygon(ring).buffer(0)


def test_catchment_simplify_tolerance_is_20m_and_is_catchment_only() -> None:
    """Pins the B4d decision so a future "unify the tolerances" refactor has to
    read the rationale first: 20 m is NOT the soils overlay's 8 m, on purpose."""
    assert gcc.CATCHMENT_SIMPLIFY_TOLERANCE_M == 20.0
    assert gcc.CATCHMENT_SIMPLIFY_TOLERANCE_M > _LEGACY_SOILS_TOLERANCE_M
    # Still under one flow_dir cell: we shave rasterization noise, not real shape.
    assert gcc.CATCHMENT_SIMPLIFY_TOLERANCE_M < _FLOW_DIR_CELL_M


def test_simplify_clears_a_staircase_the_old_8m_left_over_the_vertex_cap() -> None:
    """The measured "vertices: 35" case, reproduced: at 8 m the staircase stays
    over ``ficha_max_vertices`` (⇒ oversized, geometry dropped); at the current
    tolerance it drops under the cap and the basin becomes servable — with the
    cap untouched and the area preserved."""
    from app.config import settings
    from app.domains.geo.ficha_service import _contar_vertices_shapely

    raw = _pixel_staircase_basin()
    raw_area_ha = raw.area / gcc.M2_PER_HA

    at_8m = raw.simplify(_LEGACY_SOILS_TOLERANCE_M, preserve_topology=True).buffer(0)
    assert _contar_vertices_shapely(at_8m) > settings.ficha_max_vertices

    simplified, area_ha = gcc._simplify_catchment(raw)
    assert _contar_vertices_shapely(simplified) <= settings.ficha_max_vertices
    # Boundary displacement only: the basin keeps its size (well under 1 %).
    assert area_ha == pytest.approx(raw_area_ha, rel=0.01)


def test_a_small_basin_keeps_its_area_within_the_measured_drift_bound() -> None:
    """The big-basin fidelity assertion is not enough on its own.

    ``area_ha`` is SHOWN in the ficha, and a 20 m shave costs proportionally more
    on a small basin than on a 3 000 ha one: the same boundary displacement is a
    larger fraction of a smaller area. A test that only checks a 3 000 ha basin
    would let a small-catchment area regression through unseen.

    The bound is MEASURED, not invented. Drift at 20 m across staircase basins of
    the same shape (Shapely, 30 m cells): 2 ha → 2.27 %, 7 ha → 1.83 %,
    13.5 ha → 1.33 %, 29 ha → 0.31 %, 120 ha → 0.63 %, 3 000 ha → 0.00 %. It stays
    single-digit-percent all the way down and never degenerates, which is why the
    tolerance is a single constant and not staggered by basin size.
    """
    raw = _pixel_staircase_basin(radius_m=200.0)
    raw_area_ha = raw.area / gcc.M2_PER_HA
    # Guard the fixture itself: this must stay a SMALL basin for the test to mean
    # anything (the measured case is ~13.5 ha).
    assert 10.0 < raw_area_ha < 15.0

    simplified, area_ha = gcc._simplify_catchment(raw)

    assert not simplified.is_empty
    assert simplified.is_valid
    drift = abs(area_ha - raw_area_ha) / raw_area_ha
    assert drift < 0.02, f"small-basin area drift {drift:.2%} over the 2 % measured bound"


def test_staircase_basin_is_stored_servable_and_reported_with_no_motivo(
    catchment_db: Session,
) -> None:
    """End to end: one of the rescued 19. It is computed, NOT oversized, keeps its
    geometry under the read-path caps, and the per-motivo breakdown stays all-zero
    (the reporting added in T6 keeps working with the new tolerance)."""
    from app.config import settings

    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-staircase")

    basin = _pixel_staircase_basin()
    result = _run(catchment_db, _RecordingWbt(), _shapes_returning(basin))

    assert result.computed == 1
    assert result.oversized == 0
    assert set(result.oversized_por_motivo) == set(gcc.CAP_MOTIVOS)
    assert sum(result.oversized_por_motivo.values()) == 0

    row = catchment_db.execute(
        text(
            "SELECT oversized, geometria IS NULL AS geom_null, "
            "ST_NPoints(geometria) AS npoints, area_ha "
            "FROM canal_catchment WHERE canal_ref = 'canal-staircase' AND variante = 'natural'"
        )
    ).one()
    assert row.oversized is False
    assert row.geom_null is False
    assert row.npoints <= settings.ficha_max_vertices
    assert float(row.area_ha) == pytest.approx(basin.area / gcc.M2_PER_HA, rel=0.01)


def test_rerun_same_version_skips_done_canal(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    first = _run(catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))
    assert first.computed == 1
    assert first.skipped == 0

    second_wbt = _RecordingWbt()
    second = _run(catchment_db, second_wbt, _shapes_returning(_NORMAL_POLY))
    assert second.computed == 0
    assert second.skipped == 1
    assert second_wbt.calls == [], "a skipped canal must not touch WBT"

    count = catchment_db.execute(
        text("SELECT count(*) FROM canal_catchment WHERE canal_ref = 'canal-a'")
    ).scalar_one()
    assert count == 1  # still one current row, not duplicated


def test_force_recomputes_even_when_the_version_is_unchanged(catchment_db: Session) -> None:
    """Caps live outside the version key.

    The resume key is the flow_dir POINTER, so after a cap change (batch 4 widened
    the catchment envelope cap) a plain re-run skips every stored row and keeps the
    old ``oversized`` verdicts. ``--force`` is what makes a re-gate possible.
    """
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    first = _run(catchment_db, _RecordingWbt(), _shapes_returning(_OVERSIZED_POLY))
    assert first.oversized == 1
    assert _row(catchment_db, "canal-a").oversized is True

    # Same pointer, wider cap: without --force this is a no-op.
    forced_wbt = _RecordingWbt()
    forced = _run(
        catchment_db,
        forced_wbt,
        _shapes_returning(_OVERSIZED_POLY),
        force=True,
        max_area_ha=1_000_000.0,
    )

    assert forced.skipped == 0
    assert forced.computed == 1
    assert forced_wbt.calls, "a forced canal must be recomputed"
    row = _row(catchment_db, "canal-a")
    assert row.oversized is False
    assert row.geom_null is False


def test_new_flow_dir_version_recomputes(catchment_db: Session) -> None:
    v1 = _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")
    _run(catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))
    assert _row(catchment_db, "canal-a").version == v1

    # A fresh terrain run mints a NEW flow_dir layer (new id → new version).
    catchment_db.execute(
        text("DELETE FROM geo_layers WHERE nombre = :n"), {"n": f"natural_flow_dir_{AREA}"}
    )
    v2 = _register_flow_dir(catchment_db)
    assert v2 != v1

    result = _run(catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))
    assert result.computed == 1
    assert result.skipped == 0
    assert _row(catchment_db, "canal-a").version == v2


def test_missing_flow_dir_layer_raises(catchment_db: Session) -> None:
    _seed_canal(catchment_db, "canal-a")  # no flow_dir layer registered
    with pytest.raises(RuntimeError, match="no flow_dir layer"):
        _run(catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))


def test_limit_scopes_the_run(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")
    _seed_canal(catchment_db, "canal-b")
    _seed_canal(catchment_db, "canal-c")

    result = _run(catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY), limit=2)
    assert result.total == 2
    assert result.computed == 2


def test_estado_scopes_the_run(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-rel-1", estado="relevado")
    _seed_canal(catchment_db, "canal-rel-2", estado="relevado")
    _seed_canal(catchment_db, "canal-prop-1", estado="propuesto")

    result = _run(
        catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY), estado="propuesto"
    )
    assert result.total == 1  # only the propuesto canal is in scope
    assert result.computed == 1
    assert _row(catchment_db, "canal-prop-1") is not None
    assert _row(catchment_db, "canal-rel-1") is None


def test_canal_ref_scopes_a_single_canal(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")
    _seed_canal(catchment_db, "canal-b")

    result = _run(
        catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY), canal_ref="canal-b"
    )
    assert result.total == 1
    assert result.computed == 1
    assert _row(catchment_db, "canal-b") is not None
    assert _row(catchment_db, "canal-a") is None


# ── CRS guard (R3-003): a geographic flow_dir CRS must fail loud ─────────────


def test_geographic_flow_dir_crs_raises_before_the_loop(catchment_db: Session) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    wbt = _RecordingWbt()
    with pytest.raises(RuntimeError, match="geographic, not projected"):
        gcc.generate_catchments(
            catchment_db,
            area_id=AREA,
            rasterio_module=_FakeGeographicRasterio(),
            rasterize_fn=_fake_rasterize,
            shapes_fn=_shapes_returning(_NORMAL_POLY),
            get_wbt=lambda: wbt,
        )
    # Failed loud BEFORE any per-canal work: WBT never ran, no row written.
    assert wbt.calls == []
    assert _row(catchment_db, "canal-a") is None


# ── failure-continue + exit-code contract (R4-002 + R3-002) ──────────────────


def test_one_canal_failure_is_isolated_and_batch_continues(
    catchment_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single canal blowing up is caught, rolled back, counted in ``failed``,
    and the OTHER canals are still computed and committed."""
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")
    _seed_canal(catchment_db, "canal-b")
    _seed_canal(catchment_db, "canal-c")

    original_compute = gcc._compute_one

    def _flaky_compute(db: Session, *, canal_ref: str, **kwargs: Any) -> None:
        if canal_ref == "canal-b":
            raise RuntimeError("boom computing canal-b")
        return original_compute(db, canal_ref=canal_ref, **kwargs)

    monkeypatch.setattr(gcc, "_compute_one", _flaky_compute)

    result = _run(catchment_db, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))

    assert result.total == 3
    assert result.computed == 2  # canals a and c processed despite canal-b failing
    assert result.failed == 1
    assert result.failed_canal_refs == ["canal-b"]

    # The good canals persisted; the failed one was rolled back (no row).
    assert _row(catchment_db, "canal-a") is not None
    assert _row(catchment_db, "canal-c") is not None
    assert _row(catchment_db, "canal-b") is None


def test_main_success_returns_exit_ok(
    catchment_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    code = _run_main(catchment_db, monkeypatch, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))
    assert code == gcc.EXIT_OK  # 0
    assert _row(catchment_db, "canal-a") is not None


def test_main_per_canal_failure_returns_exit_failed(
    catchment_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    def _always_fail(db: Session, *, canal_ref: str, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(gcc, "_compute_one", _always_fail)

    code = _run_main(catchment_db, monkeypatch, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))
    assert code == gcc.EXIT_FAILED  # 3 — per-canal failures map to a nonzero exit


def test_main_missing_flow_dir_returns_exit_prereq_failed(
    catchment_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_canal(catchment_db, "canal-a")  # no flow_dir layer registered → RuntimeError

    code = _run_main(catchment_db, monkeypatch, _RecordingWbt(), _shapes_returning(_NORMAL_POLY))
    assert code == gcc.EXIT_PREREQ_FAILED  # 1 — prerequisite missing


# ── empty-basin / null-line edges (R3-001) ───────────────────────────────────


def test_empty_basin_upserts_null_geometry_and_counts_empty(catchment_db: Session) -> None:
    """A watershed that polygonizes to nothing (``dissolved is None``) stores a
    NULL geometry with area_ha=0, is counted as empty, and does not crash."""
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a")

    wbt = _RecordingWbt()
    result = _run(catchment_db, wbt, _shapes_returning())  # no polygons → empty basin

    assert result.empty == 1
    assert result.computed == 0
    assert result.failed == 0

    row = _row(catchment_db, "canal-a")
    assert row is not None
    assert row.geom_null is True
    assert row.area_ha == pytest.approx(0.0)
    assert row.oversized is False


def test_null_line_canal_upserts_null_geometry_without_running_wbt(
    catchment_db: Session,
) -> None:
    """A canal whose trace is empty (``_canal_line_in_grid_crs`` yields an empty
    geometry) takes the same NULL/0 path, never touching WBT, without crashing."""
    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-a", wkt="LINESTRING EMPTY")

    wbt = _RecordingWbt()
    result = _run(catchment_db, wbt, _shapes_returning(_NORMAL_POLY))

    assert result.empty == 1
    assert result.computed == 0
    assert result.failed == 0
    assert wbt.calls == [], "an empty trace must not touch WBT"

    row = _row(catchment_db, "canal-a")
    assert row is not None
    assert row.geom_null is True
    assert row.area_ha == pytest.approx(0.0)


# ── read-path cap mirror: per-``tipo`` envelope (batch 4) ────────────────────


def test_exceeds_read_path_caps_uses_the_catchment_envelope_cap() -> None:
    """ "stored ⟹ servable": the batch gate must read the SAME envelope cap the
    ficha applies to ``tipo=canal_cuenca``, not the caller-polygon one."""
    import math

    from shapely.geometry import LineString

    from app.config import settings
    from app.domains.geo.ficha_service import envelope_cap_ha

    entre_ha = (settings.ficha_max_envelope_ha + settings.ficha_max_envelope_ha_cuenca) / 2.0
    lado = math.sqrt(entre_ha * gcc.M2_PER_HA)
    diagonal = LineString([(500_000, 6_000_000), (500_000 + lado, 6_000_000 + lado)])
    geom = diagonal.buffer((5_000.0 * gcc.M2_PER_HA) / (2.0 * diagonal.length), cap_style=2)
    area_ha = geom.area / gcc.M2_PER_HA

    assert envelope_cap_ha("canal_cuenca") > settings.ficha_max_envelope_ha
    assert not gcc._exceeds_read_path_caps(geom, area_ha, settings.ficha_max_area_ha)


def test_exceeds_read_path_caps_still_rejects_a_huge_envelope() -> None:
    import math

    from shapely.geometry import LineString

    from app.config import settings

    lado = math.sqrt(settings.ficha_max_envelope_ha_cuenca * 2.0 * gcc.M2_PER_HA)
    diagonal = LineString([(500_000, 6_000_000), (500_000 + lado, 6_000_000 + lado)])
    geom = diagonal.buffer((5_000.0 * gcc.M2_PER_HA) / (2.0 * diagonal.length), cap_style=2)

    assert gcc._exceeds_read_path_caps(geom, geom.area / gcc.M2_PER_HA, settings.ficha_max_area_ha)


# ── T6: WHY a catchment was rejected, per canal ───────────────────────────────
#
# The prod re-run reported "35 oversized" and nothing else: 16 were over the
# area cap (by design) and 19 were UNDER it, rejected by the envelope or the
# vertex cap with no way to tell which. `_read_path_cap_report` measures every
# cap and names every failure, and `_compute_one` logs one
# `canal_catchment.oversized` event per rejected canal.


def _envelope_only_basin():
    """Area well under the cap, envelope over the ``canal_cuenca`` cap.

    A long thin diagonal strip: 5 000 ha of surface stretched across a bounding
    box twice the envelope cap. This is the shape the read path rejects for a
    reason a bare "oversized" flag can never explain.
    """
    import math

    from shapely.geometry import LineString

    from app.config import settings

    lado = math.sqrt(settings.ficha_max_envelope_ha_cuenca * 2.0 * gcc.M2_PER_HA)
    diagonal = LineString([(500_000, 6_000_000), (500_000 + lado, 6_000_000 + lado)])
    return diagonal.buffer((5_000.0 * gcc.M2_PER_HA) / (2.0 * diagonal.length), cap_style=2)


def test_cap_report_names_the_envelope_when_the_area_is_fine() -> None:
    from app.config import settings

    geom = _envelope_only_basin()
    report = gcc._read_path_cap_report(geom, geom.area / gcc.M2_PER_HA, settings.ficha_max_area_ha)

    assert report.oversized is True
    assert report.motivos == (gcc.CAP_MOTIVO_ENVELOPE,)
    assert report.motivo == gcc.CAP_MOTIVO_ENVELOPE
    # The area really is fine — this is the "19 under the cap" case.
    assert report.area_ha < report.max_area_ha
    assert report.envelope_ha > report.max_envelope_ha
    assert report.vertices <= report.max_vertices


def test_cap_report_names_the_vertices_when_area_and_envelope_are_fine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings

    # A compact basin: small area, small envelope, a handful of vertices. Only
    # the vertex cap is moved, so `vertices` is the ONLY thing that can fail.
    geom = Point(500_000, 6_000_000).buffer(300.0)
    monkeypatch.setattr(settings, "ficha_max_vertices", 4)

    report = gcc._read_path_cap_report(geom, geom.area / gcc.M2_PER_HA, settings.ficha_max_area_ha)

    assert report.motivos == (gcc.CAP_MOTIVO_VERTICES,)
    assert report.area_ha < report.max_area_ha
    assert report.envelope_ha < report.max_envelope_ha
    assert report.vertices > 4


def test_cap_report_lists_EVERY_failing_cap_not_just_the_first() -> None:
    """No short-circuit: a basin that is both too big and too wide must say so,
    otherwise "relax the vertex cap" reads as a fix for a canal the area cap
    would still reject."""
    from app.config import settings

    geom = _envelope_only_basin()
    # Same geometry, but now the area cap is below its 5 000 ha.
    report = gcc._read_path_cap_report(geom, geom.area / gcc.M2_PER_HA, 100.0)

    assert report.motivos == (gcc.CAP_MOTIVO_AREA, gcc.CAP_MOTIVO_ENVELOPE)
    assert report.motivo == gcc.CAP_MOTIVO_AREA
    assert report.max_vertices == settings.ficha_max_vertices


def test_cap_report_is_empty_for_a_servable_catchment() -> None:
    from app.config import settings

    geom = Point(500_000, 6_000_000).buffer(300.0)
    report = gcc._read_path_cap_report(geom, geom.area / gcc.M2_PER_HA, settings.ficha_max_area_ha)

    assert report.motivos == ()
    assert report.motivo is None
    assert report.oversized is False


def test_oversized_by_envelope_logs_the_reason_per_canal(catchment_db: Session) -> None:
    """The event the operator greps for: one line per rejected canal, carrying
    the measured area/envelope/vertices AND the cap that rejected it."""
    from structlog.testing import capture_logs

    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-envelope")

    with capture_logs() as logs:
        result = _run(catchment_db, _RecordingWbt(), _shapes_returning(_envelope_only_basin()))

    assert result.oversized == 1
    assert result.oversized_por_motivo[gcc.CAP_MOTIVO_ENVELOPE] == 1
    assert result.oversized_por_motivo[gcc.CAP_MOTIVO_AREA] == 0

    eventos = [entry for entry in logs if entry["event"] == "canal_catchment.oversized"]
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento["canal_ref"] == "canal-envelope"
    assert evento["motivo"] == gcc.CAP_MOTIVO_ENVELOPE
    assert evento["motivos"] == [gcc.CAP_MOTIVO_ENVELOPE]
    # Area is REPORTED even though it passed — that is the whole point: the
    # operator needs to see that these 19 were nowhere near the area cap.
    assert evento["area_ha"] < evento["max_area_ha"]
    assert evento["envelope_ha"] > evento["max_envelope_ha"]
    assert evento["vertices"] <= evento["max_vertices"]


def test_oversized_by_vertices_logs_the_vertex_reason(
    catchment_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same event, other cap: a compact basin whose only sin is its vertex count
    (area and envelope both fine)."""
    from structlog.testing import capture_logs

    from app.config import settings

    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-vertices")

    # The simplified basin keeps ~a dozen vertices; the cap moves below that so
    # the geometry stays realistic and only ONE rule can fire.
    monkeypatch.setattr(settings, "ficha_max_vertices", 4)

    with capture_logs() as logs:
        result = _run(
            catchment_db,
            _RecordingWbt(),
            _shapes_returning(Point(500_000, 6_000_000).buffer(300.0)),
        )

    assert result.oversized == 1
    assert result.oversized_por_motivo[gcc.CAP_MOTIVO_VERTICES] == 1
    assert result.oversized_por_motivo[gcc.CAP_MOTIVO_ENVELOPE] == 0

    evento = next(entry for entry in logs if entry["event"] == "canal_catchment.oversized")
    assert evento["canal_ref"] == "canal-vertices"
    assert evento["motivo"] == gcc.CAP_MOTIVO_VERTICES
    assert evento["vertices"] > evento["max_vertices"]
    assert evento["area_ha"] < evento["max_area_ha"]

    # And the row is still stored WITHOUT geometry, exactly as before.
    row = _row(catchment_db, "canal-vertices")
    assert row is not None
    assert row.oversized is True
    assert row.geom_null is True


def test_a_servable_catchment_logs_no_oversized_event(catchment_db: Session) -> None:
    from structlog.testing import capture_logs

    _register_flow_dir(catchment_db)
    _seed_canal(catchment_db, "canal-ok")

    with capture_logs() as logs:
        result = _run(
            catchment_db,
            _RecordingWbt(),
            _shapes_returning(Point(500_000, 6_000_000).buffer(300.0)),
        )

    assert result.oversized == 0
    assert [entry for entry in logs if entry["event"] == "canal_catchment.oversized"] == []
    # The run summary still carries the (all-zero) breakdown.
    assert set(result.oversized_por_motivo) == set(gcc.CAP_MOTIVOS)
    assert sum(result.oversized_por_motivo.values()) == 0
