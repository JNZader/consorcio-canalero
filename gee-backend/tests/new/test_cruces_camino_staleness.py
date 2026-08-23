"""Real-PG: ``desactualizado``, and the JSON predicate it hangs on.

``GeoJob`` has **no area column** — the area lives inside its ``parametros``
JSON, written as ``{"area_id": area_id, ...}`` by both pipelines. That makes the
whole flag depend on a JSON accessor, and a silently non-matching JSON predicate
returns "never stale" and looks perfectly fine. So the first test here is not
about staleness at all: it asserts the predicate actually matches rows written
the way the pipelines write them.

Two deliberate design choices are pinned here rather than assumed:

* the estado set is "has reached RUNNING", **not** COMPLETED-only. The full
  pipeline wipes the layer rows and the output directory immediately after
  claiming, so a run that later FAILS has already destroyed the rasters the
  crossings came from. Under a COMPLETED-only rule the operator would keep
  reading a rank list derived from files that no longer exist.
* the timestamp is **``created_at``**, not ``updated_at``. Neither is "the moment
  this job became RUNNING": ``created_at`` is stamped at INSERT and
  ``updated_at`` is bumped by every compare-and-set, including every progress
  write. On the real dispatch path ``created_at`` is at or before the RUNNING
  transition, so comparing against it can only produce **false positives** — a
  dismissible notice — and never a false negative, which would be a silently
  wrong ranking presented as current.
"""

from __future__ import annotations

import importlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.domains.geo.intelligence.cruces_camino_support import calcular_desactualizado
from app.domains.geo.intelligence.repository import IntelligenceRepository

AREA = "zona_stale"
OTHER_AREA = "zona_ajena"


@pytest.fixture
def repo() -> IntelligenceRepository:
    return IntelligenceRepository()


@pytest.fixture
def seeded(db):
    canal_migration = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")
    db.execute(text(canal_migration.CREATE_CANAL_CONSORCIO))
    db.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash, ultima_carga_en) VALUES "
            "('stale-1', 'stale-1', ST_GeomFromText("
            "'LINESTRING(-62.8 -33.0, -62.79 -32.99)', 4326), 'h', :t)"
        ),
        {"t": datetime.now(timezone.utc) - timedelta(days=7)},
    )
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
            " created_at, updated_at) VALUES "
            "(:id, 'road_flow_crossings', 'completed', 100, CAST(:p AS json), now(), now())"
        ),
        {"id": str(job_id), "p": f'{{"area_id": "{AREA}"}}'},
    )
    db.flush()
    return job_id


def _dem_job(
    db,
    *,
    estado: str,
    created_at: datetime,
    area_id: str = AREA,
    tipo: str = "dem_pipeline",
    updated_at: datetime | None = None,
) -> uuid.UUID:
    """A DEM job written EXACTLY as the pipelines write it: area inside JSON."""
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
            " created_at, updated_at) "
            "VALUES (:id, :tipo, :estado, 0, CAST(:p AS json), :c, :u)"
        ),
        {
            "id": str(job_id),
            "tipo": tipo,
            "estado": estado,
            "p": f'{{"area_id": "{area_id}", "dem_path": "/data/dem.tif"}}',
            "c": created_at,
            "u": updated_at or created_at,
        },
    )
    db.flush()
    return job_id


def _crossings(db, repo, job_id, calculada_en: datetime) -> None:
    repo.replace_cruces_for_area(
        db,
        area_id=AREA,
        rows=[
            {
                "tramo_ref": "stale-1",
                "tipo": "flujo_natural",
                "lon": -62.8,
                "lat": -33.0,
                "direccion_flujo_deg": 0.0,
                "rumbo_camino_deg": 90.0,
                "lado_cruce": "izq_a_der",
                "area_aporte_ha": 540.0,
                "orden_ranking": 1,
                "confianza": "alta",
                "nota": None,
                "canal_ref": None,
            }
        ],
        geo_job_id=job_id,
        calculada_en=calculada_en,
    )
    db.flush()


class TestTheJsonPredicateActuallyMatches:
    """The failure mode this test exists for is a flag that is always False.

    ``parametros`` is a SQLAlchemy ``JSON`` column, so ``->>`` needs a ``::jsonb``
    cast; get it wrong and the predicate matches nothing, the flag reads "never
    stale", and everything LOOKS fine.
    """

    def test_a_dem_job_written_by_the_pipeline_shape_is_found(self, db, repo, seeded):
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        _dem_job(db, estado="running", created_at=now)

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is True

    def test_the_comparison_is_plain_text_with_no_uuid_cast(self, db, repo, seeded):
        """A non-UUID area identifier must not make the query RAISE.

        ``zona_principal`` is the real one. A ``::uuid`` cast on either side would
        turn this into ``invalid input syntax for type uuid``.
        """
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        _dem_job(db, estado="running", created_at=now, area_id="zona_principal")

        # No exception is the assertion; the area does not match, so False.
        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is False

    @pytest.mark.parametrize("tipo", ["dem_pipeline", "dem_full_pipeline"])
    def test_both_dem_job_tipos_are_matched(self, db, repo, seeded, tipo: str):
        """BOTH are destructive — the "plain pipeline is non-destructive" claim is false.

        ``run_dem_pipeline_impl`` calls ``archive_previous_output`` right after
        claiming, and that renames the whole output directory away.
        """
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        _dem_job(db, estado="running", created_at=now, tipo=tipo)

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is True


class TestFiresOnRunningNotOnCompleted:
    def test_true_once_a_dem_job_merely_reaches_running(self, db, repo, seeded):
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        _dem_job(db, estado="running", created_at=now)

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is True

    def test_stays_true_when_that_job_later_FAILS(self, db, repo, seeded):
        """The case that matters most.

        A failed full pipeline has ALREADY wiped the layers and the output
        directory — it destroyed them immediately after claiming. Treating
        "failed" as "nothing happened" is how an operator ends up reading a rank
        list derived from files that no longer exist.
        """
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        _dem_job(db, estado="failed", created_at=now)

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is True

    def test_a_pending_dem_job_alone_does_not_flag(self, db, repo, seeded):
        """PENDING has destroyed nothing yet. The PRE-CHECK is what refuses on it."""
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        _dem_job(db, estado="pending", created_at=now)

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is False

    def test_a_dem_job_for_another_area_does_not_flag(self, db, repo, seeded):
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        _dem_job(db, estado="running", created_at=now, area_id=OTHER_AREA)

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is False

    def test_a_dem_job_older_than_the_crossings_does_not_flag(self, db, repo, seeded):
        now = datetime.now(timezone.utc)
        _dem_job(db, estado="completed", created_at=now - timedelta(days=1))
        _crossings(db, repo, seeded, now)

        assert calcular_desactualizado(db, AREA, now) is False


class TestItIsCreatedAtNotUpdatedAt:
    def test_a_long_running_job_whose_updated_at_moved_forward_does_not_change_the_verdict(
        self, db, repo, seeded
    ):
        """``updated_at`` is bumped by EVERY compare-and-set, progress writes included.

        A DEM job created before the crossings but still writing progress
        afterwards would flip the flag under an ``updated_at`` rule — for a job
        that changed nothing since. The comparison reads ``created_at``, so the
        verdict is stable.
        """
        now = datetime.now(timezone.utc)
        _dem_job(
            db,
            estado="running",
            created_at=now - timedelta(hours=6),
            updated_at=now + timedelta(minutes=5),
        )
        _crossings(db, repo, seeded, now)

        assert calcular_desactualizado(db, AREA, now) is False


class TestARedVialReloadAloneFlipsIt:
    """Terrain is not the only input.

    ``lado_cruce`` and ``rumbo_camino_deg`` are defined relative to the segment's
    STORED digitization direction, so a reload that changes only the vertex order
    — leaving the trace identical, Hausdorff 0, so the loader correctly keeps the
    id and the whole history — silently reverses the meaning of both. The loader
    writes no ``geo_jobs`` row, so ``ultima_carga_en`` is the event to compare
    against; inventing a synthetic job for a script would be worse than storing
    the fact.
    """

    def test_a_reload_with_no_dem_job_at_all_flips_the_flag(self, db, repo, seeded):
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is False

        db.execute(
            text("UPDATE red_vial SET ultima_carga_en = :t WHERE id = 'stale-1'"),
            {"t": now},
        )
        db.flush()

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is True, (
            "a road reload alone, with no DEM job anywhere, must flip the flag"
        )

    def test_a_vertex_order_only_reload_flips_it_too(self, db, repo, seeded):
        """The trace is IDENTICAL and the stored side is now backwards.

        Nothing about the geometry changed, so nothing but ``ultima_carga_en``
        can tell the operator that ``lado_cruce`` no longer means what it says.
        """
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))

        before = db.execute(
            text("SELECT ST_AsText(geom) FROM red_vial WHERE id = 'stale-1'")
        ).scalar_one()
        db.execute(
            text(
                "UPDATE red_vial SET geom = ST_Reverse(geom), ultima_carga_en = :t "
                "WHERE id = 'stale-1'"
            ),
            {"t": now},
        )
        db.flush()
        after = db.execute(
            text("SELECT ST_AsText(geom) FROM red_vial WHERE id = 'stale-1'")
        ).scalar_one()

        assert before != after, "the vertex order really did change"
        assert db.execute(
            text(
                "SELECT ST_Equals(geom, ST_GeomFromText(:w, 4326)) FROM red_vial WHERE id='stale-1'"
            ),
            {"w": before},
        ).scalar_one(), "yet the trace is geometrically identical"

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is True

    def test_a_reload_of_a_segment_this_area_does_not_use_does_not_flag(self, db, repo, seeded):
        """Scoped to the segments actually in scope for this area's crossings."""
        now = datetime.now(timezone.utc)
        _crossings(db, repo, seeded, now - timedelta(hours=2))
        db.execute(
            text(
                "INSERT INTO red_vial (id, source_id, geom, geom_hash, ultima_carga_en) "
                "VALUES ('otro-1', 'otro-1', ST_GeomFromText("
                "'LINESTRING(-60 -30, -60.01 -30.01)', 4326), 'h2', :t)"
            ),
            {"t": now},
        )
        db.flush()

        assert calcular_desactualizado(db, AREA, now - timedelta(hours=2)) is False


class TestNoCrossingsMeansNoVerdict:
    def test_an_area_with_no_crossings_is_not_stale(self, db, repo):
        assert calcular_desactualizado(db, "zona_vacia", None) is False
