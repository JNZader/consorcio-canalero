"""Real-PG: the write path, the four CHECKs and the CRS contract at rest.

The write is a **delete-then-insert scoped to ``area_id``** in ONE transaction.
That sentence is only expressible because ``cruce_camino`` has an area column; on
``puntos_conflicto`` the only implementable reading of the same rule would have
been "scope by ``tipo`` alone", which is cross-area destructive — a run for area
A wiping area B's crossings. So the first test here is the one the reuse could
never have passed.

The SRID assertion is deliberately paired with a bounding-box assertion:
``ST_SRID(geometria) = 4326`` passes perfectly on a mislabelled UTM point, which
is exactly the ``crs="EPSG:4326"`` trap the derivation exists to avoid. The bbox
check is what actually catches it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.geo.intelligence.repository import IntelligenceRepository

AREA_A = "zona_principal"
AREA_B = "zona_secundaria"

#: Somewhere in the consorcio's actual territory, so the bbox assertion means
#: something rather than merely being satisfiable.
AREA_BBOX = (-63.0, -33.2, -62.5, -32.8)


@pytest.fixture
def repo() -> IntelligenceRepository:
    return IntelligenceRepository()


@pytest.fixture
def seeded(db):
    """Two road segments and a job, the minimum a crossing row must point at."""
    for segment_id in ("28188", "28189"):
        db.execute(
            text(
                "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
                "(:id, :id, ST_GeomFromText("
                "'LINESTRING(-62.8 -33.0, -62.79 -32.99)', 4326), :h)"
            ),
            {"id": segment_id, "h": f"hash-{segment_id}"},
        )
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, created_at, updated_at) "
            "VALUES (:id, 'road_flow_crossings', 'running', 0, now(), now())"
        ),
        {"id": str(job_id)},
    )
    db.flush()
    return job_id


def _natural_row(tramo_ref: str = "28188", *, rank: int = 1, lon=-62.8, lat=-33.0) -> dict:
    return {
        "tramo_ref": tramo_ref,
        "tipo": "flujo_natural",
        "lon": lon,
        "lat": lat,
        "direccion_flujo_deg": 0.0,
        "rumbo_camino_deg": 90.0,
        "lado_cruce": "izq_a_der",
        "area_aporte_ha": 540.0,
        "orden_ranking": rank,
        "confianza": "alta",
        "nota": None,
        "canal_ref": None,
    }


def _canal_row(tramo_ref: str = "28188", *, lon=-62.79, lat=-32.99) -> dict:
    return {
        "tramo_ref": tramo_ref,
        "tipo": "canal",
        "lon": lon,
        "lat": lat,
        "direccion_flujo_deg": None,
        "rumbo_camino_deg": None,
        "lado_cruce": None,
        "area_aporte_ha": None,
        "orden_ranking": None,
        "confianza": None,
        "nota": None,
        "canal_ref": "canal-1",
    }


class TestScopedReplace:
    def test_a_rerun_for_one_area_leaves_another_areas_rows_intact(self, db, repo, seeded):
        """The property ``puntos_conflicto`` could not have provided.

        With no area column the write rule was unimplementable as written, and
        the only implementable reading of it wiped every area at once.
        """
        now = datetime.now(timezone.utc)
        repo.replace_cruces_for_area(
            db, area_id=AREA_A, rows=[_natural_row()], geo_job_id=seeded, calculada_en=now
        )
        repo.replace_cruces_for_area(
            db,
            area_id=AREA_B,
            rows=[_natural_row("28189")],
            geo_job_id=seeded,
            calculada_en=now,
        )
        db.flush()

        repo.replace_cruces_for_area(
            db,
            area_id=AREA_A,
            rows=[_natural_row(), _canal_row()],
            geo_job_id=seeded,
            calculada_en=now,
        )
        db.flush()

        assert len(repo.get_cruces_for_area(db, AREA_A)) == 2
        assert len(repo.get_cruces_for_area(db, AREA_B)) == 1, (
            "a re-run for one area must not touch another area's rows"
        )

    def test_a_rerun_replaces_rather_than_accumulating(self, db, repo, seeded):
        now = datetime.now(timezone.utc)
        for _ in range(3):
            repo.replace_cruces_for_area(
                db,
                area_id=AREA_A,
                rows=[_natural_row()],
                geo_job_id=seeded,
                calculada_en=now,
            )
            db.flush()

        assert len(repo.get_cruces_for_area(db, AREA_A)) == 1

    def test_a_rerun_over_unchanged_inputs_reproduces_identical_ranks(self, db, repo, seeded):
        now = datetime.now(timezone.utc)
        rows = [
            _natural_row("28188", rank=1, lon=-62.80, lat=-33.00),
            _natural_row("28189", rank=2, lon=-62.70, lat=-32.90),
        ]

        ranks = []
        for _ in range(2):
            repo.replace_cruces_for_area(
                db, area_id=AREA_A, rows=rows, geo_job_id=seeded, calculada_en=now
            )
            db.flush()
            ranks.append(
                [(r["tramo_ref"], r["orden_ranking"]) for r in repo.get_cruces_for_area(db, AREA_A)]
            )

        assert ranks[0] == ranks[1]


class TestTheFourChecks:
    """Every per-``tipo`` rule is enforced by the DATABASE, not by hope."""

    def _insert(self, db, seeded, row: dict):
        repo = IntelligenceRepository()
        repo.replace_cruces_for_area(
            db,
            area_id=AREA_A,
            rows=[row],
            geo_job_id=seeded,
            calculada_en=datetime.now(timezone.utc),
        )
        db.flush()

    def test_ck_cruce_flujo_completo_rejects_a_directionless_natural_row(self, db, seeded):
        row = _natural_row()
        row["direccion_flujo_deg"] = None
        with pytest.raises(IntegrityError) as exc:
            self._insert(db, seeded, row)
        assert "ck_cruce_flujo_completo" in str(exc.value)

    def test_ck_cruce_flujo_completo_rejects_an_unranked_natural_row(self, db, seeded):
        row = _natural_row()
        row["orden_ranking"] = None
        with pytest.raises(IntegrityError) as exc:
            self._insert(db, seeded, row)
        assert "ck_cruce_flujo_completo" in str(exc.value)

    def test_ck_cruce_canal_sin_rank_rejects_a_ranked_canal_row(self, db, seeded):
        row = _canal_row()
        row["orden_ranking"] = 1
        with pytest.raises(IntegrityError) as exc:
            self._insert(db, seeded, row)
        assert "ck_cruce_canal_sin_rank" in str(exc.value)

    def test_ck_cruce_flujo_sin_canal_rejects_a_natural_row_carrying_a_canal(self, db, seeded):
        """A row that is two things at once is a row nobody can read."""
        row = _natural_row()
        row["canal_ref"] = "canal-1"
        with pytest.raises(IntegrityError) as exc:
            self._insert(db, seeded, row)
        assert "ck_cruce_flujo_sin_canal" in str(exc.value)

    def test_ck_cruce_flujo_confianza_rejects_a_natural_row_without_a_band(self, db, seeded):
        """The three-band predicate ALWAYS assigns one, so a NULL means a bug."""
        row = _natural_row()
        row["confianza"] = None
        with pytest.raises(IntegrityError) as exc:
            self._insert(db, seeded, row)
        assert "ck_cruce_flujo_confianza" in str(exc.value)


class TestCrsAtRest:
    def test_stored_geometry_is_4326_AND_lands_inside_the_area(self, db, repo, seeded):
        """The SRID check alone passes on a mislabelled UTM point.

        Stamping ``4326`` on a UTM easting of ~400 000 and northing of ~6 400 000
        yields a "coordinate" in the Gulf of Guinea that ``ST_SRID`` is perfectly
        happy with. The bbox check is the one that catches it.
        """
        repo.replace_cruces_for_area(
            db,
            area_id=AREA_A,
            rows=[_natural_row(lon=-62.8, lat=-33.0)],
            geo_job_id=seeded,
            calculada_en=datetime.now(timezone.utc),
        )
        db.flush()

        srid, lon, lat = db.execute(
            text(
                "SELECT ST_SRID(geometria), ST_X(geometria), ST_Y(geometria) "
                "FROM cruce_camino WHERE area_id = :a"
            ),
            {"a": AREA_A},
        ).one()

        assert srid == 4326
        minx, miny, maxx, maxy = AREA_BBOX
        assert minx <= lon <= maxx, f"longitude {lon} is outside the area bbox"
        assert miny <= lat <= maxy, f"latitude {lat} is outside the area bbox"

    def test_a_mislabelled_utm_point_would_fail_the_bbox_assertion(self, db, repo, seeded):
        """The negative control: prove the assertion above can actually fail."""
        repo.replace_cruces_for_area(
            db,
            area_id=AREA_B,
            rows=[_natural_row("28189", lon=0.0, lat=0.0)],
            geo_job_id=seeded,
            calculada_en=datetime.now(timezone.utc),
        )
        db.flush()

        lon, lat = db.execute(
            text("SELECT ST_X(geometria), ST_Y(geometria) FROM cruce_camino WHERE area_id = :a"),
            {"a": AREA_B},
        ).one()

        minx, miny, maxx, maxy = AREA_BBOX
        assert not (minx <= lon <= maxx and miny <= lat <= maxy)


class TestRestrictRefusesToOrphan:
    def test_deleting_a_referenced_red_vial_row_is_refused(self, db, repo, seeded):
        """The S1 assertion deferred to here, now that a dependent exists.

        ``ON DELETE RESTRICT`` is a **backstop**, not the mechanism: the loader
        never deletes, it retires with ``activo = false``. But if some future
        path tries, the database refuses instead of quietly mutilating data.
        """
        repo.replace_cruces_for_area(
            db,
            area_id=AREA_A,
            rows=[_natural_row("28188")],
            geo_job_id=seeded,
            calculada_en=datetime.now(timezone.utc),
        )
        db.flush()

        with pytest.raises(IntegrityError):
            db.execute(text("DELETE FROM red_vial WHERE id = '28188'"))
            db.flush()

    def test_retiring_a_referenced_segment_is_allowed(self, db, repo, seeded):
        """Retirement is the mechanism, and it keeps the crossings pointing at it."""
        repo.replace_cruces_for_area(
            db,
            area_id=AREA_A,
            rows=[_natural_row("28188")],
            geo_job_id=seeded,
            calculada_en=datetime.now(timezone.utc),
        )
        db.flush()

        db.execute(text("UPDATE red_vial SET activo = false WHERE id = '28188'"))
        db.flush()

        assert len(repo.get_cruces_for_area(db, AREA_A)) == 1


class TestProvenance:
    def test_every_row_carries_its_job_and_its_generation_timestamp(self, db, repo, seeded):
        """ "These crossings predate the current terrain data" must be COMPARABLE."""
        stamped = datetime.now(timezone.utc) - timedelta(hours=3)
        repo.replace_cruces_for_area(
            db,
            area_id=AREA_A,
            rows=[_natural_row(), _canal_row()],
            geo_job_id=seeded,
            calculada_en=stamped,
        )
        db.flush()

        rows = repo.get_cruces_for_area(db, AREA_A)
        assert len(rows) == 2
        for row in rows:
            assert row["geo_job_id"] == seeded
            assert row["calculada_en"] == stamped

        assert repo.get_calculada_en(db, AREA_A) == stamped
