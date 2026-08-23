"""Real-PG: candidates are per RUN, and a run's rasters may be gone.

Why the key is ``(tramo_ref, geo_job_id)`` and not ``(tramo_ref, dem_layer_id)``:

* ``upsert_layer`` looks a layer up **by name** and, when it exists, mutates the
  row in place — path, bbox and metadata are overwritten while the **UUID stays
  the same** (``geo_repository_jobs_layers.py:207-243``). Two DEM runs a month
  apart over different terrain data therefore produce the *same*
  ``dem_layer_id``.
* ``delete_layers_by_area_id`` (``:245-250``) wipes those rows outright, so the
  id is not even guaranteed to survive.

``geo_jobs.id`` is created fresh per run and never reused. The consequence,
asserted below: two runs coexist as two rows, the pre-fill reads the newest, and
a candidate whose job's layers were wiped stays readable and pre-fillable — it is
a recorded past computation, not a live pointer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.domains.geo.relevamiento.repository import RelevamientoRepository

TRAMO = "cand-tramo-1"


@pytest.fixture
def repo() -> RelevamientoRepository:
    return RelevamientoRepository()


@pytest.fixture
def seeded(db):
    db.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
            "(:id, :id, ST_GeomFromText('LINESTRING(-62 -32.5, -62.01 -32.51)', 4326), 'h')"
        ),
        {"id": TRAMO},
    )
    db.flush()


def _crear_job(db) -> uuid.UUID:
    from app.domains.geo.models import EstadoGeoJob, GeoJob, TipoGeoJob

    job = GeoJob(
        tipo=TipoGeoJob.TRAMO_CLASSIFICATION,
        estado=EstadoGeoJob.COMPLETED,
        parametros={"area_id": "zona_principal"},
        progreso=100,
    )
    db.add(job)
    db.flush()
    return job.id


def _crear_layer(db, area_id: str = "zona_principal") -> uuid.UUID:
    from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer, TipoGeoLayer

    layer = GeoLayer(
        nombre=f"dem_filled_{area_id}",
        tipo=TipoGeoLayer.DEM_RAW,
        fuente=FuenteGeoLayer.GEE,
        archivo_path=f"/data/geo/{area_id}/output/dem_filled.tif",
        formato=FormatoGeoLayer.GEOTIFF,
        srid=4326,
        bbox=[-62.1, -32.6, -61.9, -32.4],
        area_id=area_id,
    )
    db.add(layer)
    db.flush()
    return layer.id


class TestTwoRunsCoexist:
    def test_a_second_run_adds_a_row_instead_of_overwriting_the_first(self, db, repo, seeded):
        primer_job, segundo_job = _crear_job(db), _crear_job(db)
        layer_id = _crear_layer(db)

        # The SAME layer id on both, which is exactly what ``upsert_layer``
        # produces — and exactly why it cannot be the key.
        for job_id, clasificacion in ((primer_job, "canal"), (segundo_job, "terraplen")):
            repo.insertar_candidatas(
                db,
                filas=[
                    {
                        "tramo_ref": TRAMO,
                        "clasificacion_candidata": clasificacion,
                        "confianza_m": 1.4 if clasificacion == "terraplen" else -1.4,
                        "dem_layer_id": layer_id,
                    }
                ],
                geo_job_id=job_id,
                calculada_en=datetime.now(timezone.utc),
            )
        db.flush()

        filas = (
            db.execute(
                text(
                    "SELECT clasificacion_candidata FROM tramo_clasificacion_candidata "
                    "WHERE tramo_ref = :t ORDER BY calculada_en"
                ),
                {"t": TRAMO},
            )
            .scalars()
            .all()
        )

        assert len(filas) == 2, (
            "keying on dem_layer_id would have collapsed these into one row and "
            "silently destroyed the first run's candidate"
        )
        assert set(filas) == {"canal", "terraplen"}

    def test_the_same_run_cannot_produce_two_candidates_for_one_segment(self, db, repo, seeded):
        """The primary key still says one verdict per segment per run."""
        from sqlalchemy.exc import IntegrityError

        job_id = _crear_job(db)
        repo.insertar_candidatas(
            db,
            filas=[{"tramo_ref": TRAMO, "clasificacion_candidata": "neutro", "confianza_m": 0.1}],
            geo_job_id=job_id,
            calculada_en=datetime.now(timezone.utc),
        )
        db.flush()

        with pytest.raises(IntegrityError):
            repo.insertar_candidatas(
                db,
                filas=[
                    {
                        "tramo_ref": TRAMO,
                        "clasificacion_candidata": "canal",
                        "confianza_m": -2.0,
                    }
                ],
                geo_job_id=job_id,
                calculada_en=datetime.now(timezone.utc),
            )
            db.flush()


class TestThePreFillReadsTheNewest:
    def test_the_newest_candidate_wins(self, db, repo, seeded):
        ahora = datetime.now(timezone.utc)
        for clasificacion, delta in (("canal", -2), ("terraplen", 0), ("neutro", -1)):
            repo.insertar_candidatas(
                db,
                filas=[
                    {
                        "tramo_ref": TRAMO,
                        "clasificacion_candidata": clasificacion,
                        "confianza_m": 1.0,
                    }
                ],
                geo_job_id=_crear_job(db),
                calculada_en=ahora + timedelta(hours=delta),
            )
        db.flush()

        candidata = repo.get_candidata(db, TRAMO)

        assert candidata["clasificacion_candidata"] == "terraplen"

    def test_older_candidates_are_retained_and_simply_not_shown(self, db, repo, seeded):
        ahora = datetime.now(timezone.utc)
        for clasificacion, delta in (("canal", -2), ("terraplen", 0)):
            repo.insertar_candidatas(
                db,
                filas=[
                    {
                        "tramo_ref": TRAMO,
                        "clasificacion_candidata": clasificacion,
                        "confianza_m": 1.0,
                    }
                ],
                geo_job_id=_crear_job(db),
                calculada_en=ahora + timedelta(hours=delta),
            )
        db.flush()

        total = db.execute(
            text("SELECT count(*) FROM tramo_clasificacion_candidata WHERE tramo_ref = :t"),
            {"t": TRAMO},
        ).scalar()

        assert total == 2
        assert repo.get_candidata(db, TRAMO)["clasificacion_candidata"] == "terraplen"

    def test_a_tie_on_calculada_en_is_broken_deterministically(self, db, repo, seeded):
        """Two rows stamped identically must still resolve to ONE answer."""
        instante = datetime.now(timezone.utc)
        jobs = sorted([_crear_job(db), _crear_job(db)], key=str)
        for job_id, clasificacion in zip(jobs, ("terraplen", "canal")):
            repo.insertar_candidatas(
                db,
                filas=[
                    {
                        "tramo_ref": TRAMO,
                        "clasificacion_candidata": clasificacion,
                        "confianza_m": 1.0,
                    }
                ],
                geo_job_id=job_id,
                calculada_en=instante,
            )
        db.flush()

        primero = repo.get_candidata(db, TRAMO)
        segundo = repo.get_candidata(db, TRAMO)

        assert primero["geo_job_id"] == segundo["geo_job_id"] == jobs[0]


class TestACandidateOutlivesItsRasters:
    def test_a_candidate_whose_layers_were_wiped_is_still_readable(self, db, repo, seeded):
        """``delete_layers_by_area_id`` wipes layer rows; the candidate stays."""
        layer_id = _crear_layer(db)
        repo.insertar_candidatas(
            db,
            filas=[
                {
                    "tramo_ref": TRAMO,
                    "clasificacion_candidata": "terraplen",
                    "confianza_m": 1.4,
                    "dem_layer_id": layer_id,
                }
            ],
            geo_job_id=_crear_job(db),
            calculada_en=datetime.now(timezone.utc),
        )
        db.flush()

        db.execute(text("DELETE FROM geo_layers WHERE id = :id"), {"id": layer_id})
        db.flush()

        candidata = repo.get_candidata(db, TRAMO)

        assert candidata is not None, (
            "a FK here would have deleted or blocked, destroying the only record "
            "of what the DEM once suggested"
        )
        assert candidata["clasificacion_candidata"] == "terraplen"
        assert candidata["dem_layer_id"] == layer_id, (
            "the dangling id is kept: it says WHICH layer produced this, even "
            "though nothing resolves it at read time"
        )

    def test_a_dangling_candidate_still_pre_fills_a_survey(self, db, seeded):
        from app.domains.geo.relevamiento.schemas import RelevamientoTramoCreate
        from app.domains.geo.relevamiento.service import RelevamientoService

        from app.auth.models import User, UserRole

        layer_id = _crear_layer(db)
        RelevamientoRepository().insertar_candidatas(
            db,
            filas=[
                {
                    "tramo_ref": TRAMO,
                    "clasificacion_candidata": "terraplen",
                    "confianza_m": 1.4,
                    "dem_layer_id": layer_id,
                }
            ],
            geo_job_id=_crear_job(db),
            calculada_en=datetime.now(timezone.utc),
        )
        db.execute(text("DELETE FROM geo_layers WHERE id = :id"), {"id": layer_id})
        user = User(
            email=f"operator-cand-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="fakehash",
            nombre="Operador",
            apellido="Candidata",
            role=UserRole.OPERADOR,
        )
        db.add(user)
        db.flush()

        stored = RelevamientoService().registrar(
            db,
            payload=RelevamientoTramoCreate(
                tramo_ref=TRAMO,
                nivel_relativo="mayor",
                tiene_cuneta="no",
                estado_cuneta=None,
                nivel_confirmado_sin_cambios=True,
            ),
            relevado_por=user.id,
        )

        assert stored["nivel_desde_candidata"] is True, (
            "the candidate is labelled a candidate either way; a missing raster "
            "does not make a recorded past computation unusable"
        )
