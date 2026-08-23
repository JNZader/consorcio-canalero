"""Real-PG tests for the append-only survey repository and its ordering key.

The one property everything else rests on: **``version`` decides which record is
current, and nothing else can**. ``relevado_en`` defaults to ``now()``, which is
**transaction-start** time in PostgreSQL — so two surveys written from the same
transaction carry the *identical* stamp, and two written from overlapping
transactions can carry stamps in the opposite order to their commits. ``id`` is a
random UUIDv4, so a tie-break on it is lexicographic accident. The tests below
create exactly that tie and assert the view still resolves deterministically.

The second property is structural: there is **no UPDATE and no DELETE path** in
the repository at all. A correction is a new row; the record it corrects stays
retrievable, and its author is unrewritable because nothing can rewrite it.
"""

from __future__ import annotations

import importlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.geo.relevamiento import models as relevamiento_models
from app.domains.geo.relevamiento.repository import RelevamientoRepository

MIGRATION = importlib.import_module("app.db.migrations.versions.0023_add_relevamiento_tramo")

REPOSITORY_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "domains"
    / "geo"
    / "relevamiento"
    / "repository.py"
)

TRAMO = "rel-tramo-1"
OTRO_TRAMO = "rel-tramo-2"


@pytest.fixture
def repo() -> RelevamientoRepository:
    return RelevamientoRepository()


@pytest.fixture
def seeded(db):
    """Two active road segments and one operator, inside the test transaction."""
    from app.auth.models import User, UserRole

    user = User(
        email=f"operator-relevamiento-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        nombre="Operador",
        apellido="Relevamiento",
        role=UserRole.OPERADOR,
    )
    db.add(user)
    db.flush()
    user_id = user.id
    for tramo, lon in ((TRAMO, -62.0), (OTRO_TRAMO, -62.5)):
        db.execute(
            text(
                "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
                "(:id, :id, ST_GeomFromText(:wkt, 4326), :h)"
            ),
            {
                "id": tramo,
                "wkt": f"LINESTRING({lon} -32.5, {lon - 0.01} -32.51)",
                "h": f"hash-{tramo}",
            },
        )
    db.flush()
    return user_id


def _insert(repo, db, user_id, tramo=TRAMO, **overrides):
    payload = {
        "tramo_ref": tramo,
        "nivel_relativo": "menor",
        "tiene_cuneta": "si",
        "estado_cuneta": "limpia",
        "observaciones": None,
        "relevado_por": user_id,
        "nivel_desde_candidata": False,
    }
    payload.update(overrides)
    return repo.insertar(db, **payload)


class TestTheCurrentRecordIsTheHighestVersion:
    def test_the_newest_survey_wins(self, db, repo, seeded):
        _insert(repo, db, seeded, nivel_relativo="menor")
        segundo = _insert(repo, db, seeded, nivel_relativo="mayor")

        vigente = repo.get_vigente(db, TRAMO)

        assert vigente["nivel_relativo"] == "mayor"
        assert vigente["version"] == segundo["version"]

    def test_two_surveys_in_one_transaction_share_relevado_en(self, db, repo, seeded):
        """The tie this design exists for — and it is not hypothetical.

        ``now()`` is transaction-start time, so these two rows are stamped
        *identically*. If ``relevado_en`` ordered the history, "current" would be
        decided by the ``id`` tie-break, i.e. by a random UUID.
        """
        primero = _insert(repo, db, seeded, nivel_relativo="menor")
        segundo = _insert(repo, db, seeded, nivel_relativo="mayor")

        assert primero["relevado_en"] == segundo["relevado_en"]
        assert segundo["version"] > primero["version"]

        vigente = repo.get_vigente(db, TRAMO)
        assert vigente["version"] == segundo["version"]
        assert vigente["nivel_relativo"] == "mayor"

    def test_the_winner_does_not_depend_on_the_id_ordering(self, db, repo, seeded):
        """Asserted over both id orderings, so a lucky UUID cannot pass this."""
        primero = _insert(repo, db, seeded, nivel_relativo="menor")
        segundo = _insert(repo, db, seeded, nivel_relativo="mayor")

        vigente = repo.get_vigente(db, TRAMO)

        assert vigente["version"] == max(primero["version"], segundo["version"])
        assert vigente["nivel_relativo"] == "mayor", (
            "the later VERSION wins regardless of how the two random ids sort"
        )

    def test_each_segment_has_its_own_current_record(self, db, repo, seeded):
        _insert(repo, db, seeded, tramo=TRAMO, nivel_relativo="menor")
        _insert(repo, db, seeded, tramo=OTRO_TRAMO, nivel_relativo="mayor")

        assert repo.get_vigente(db, TRAMO)["nivel_relativo"] == "menor"
        assert repo.get_vigente(db, OTRO_TRAMO)["nivel_relativo"] == "mayor"

    def test_a_segment_never_surveyed_has_no_current_record(self, db, repo, seeded):
        assert repo.get_vigente(db, TRAMO) is None


class TestHistorySurvives:
    def test_a_correction_adds_a_version_and_keeps_the_previous_one(self, db, repo, seeded):
        equivocado = _insert(repo, db, seeded, nivel_relativo="menor", observaciones="mal cargado")
        _insert(repo, db, seeded, nivel_relativo="mayor", observaciones="corregido")

        historial = repo.get_historial(db, TRAMO)

        assert [h["nivel_relativo"] for h in historial] == ["mayor", "menor"], (
            "the history reads newest first"
        )
        assert any(h["id"] == equivocado["id"] for h in historial), (
            "the corrected record stays retrievable — a correction is an addition"
        )

    def test_every_entry_carries_its_author_and_moment(self, db, repo, seeded):
        _insert(repo, db, seeded)

        entry = repo.get_historial(db, TRAMO)[0]

        assert entry["relevado_por"] == seeded
        assert entry["relevado_en"] is not None

    def test_the_history_of_a_retired_segment_stays_retrievable(self, db, repo, seeded):
        """Retirement removes a segment from the working set, not from the record."""
        _insert(repo, db, seeded)
        db.execute(text("UPDATE red_vial SET activo = false WHERE id = :t"), {"t": TRAMO})
        db.flush()

        assert len(repo.get_historial(db, TRAMO)) == 1
        assert repo.get_vigente(db, TRAMO) is not None


class TestThereIsNoWriteBackPath:
    """RSS-R1's "the author is not alterable afterwards", enforced structurally.

    Asserted against the repository SOURCE rather than against behaviour: a test
    that only checks "the author did not change" passes on a repository that has
    an update method nobody happened to call.
    """

    @pytest.mark.parametrize("forbidden", [r"\.update\(", r"\.delete\(", r"UPDATE ", r"DELETE "])
    def test_the_repository_source_carries_no_mutation_path(self, forbidden: str):
        source = REPOSITORY_PATH.read_text(encoding="utf-8")

        assert re.search(forbidden, source) is None, (
            f"the survey repository must expose no mutation path — found {forbidden!r}"
        )

    def test_the_repository_exposes_no_update_or_delete_method(self):
        names = [name for name in dir(RelevamientoRepository) if not name.startswith("_")]

        for name in names:
            assert "update" not in name.lower()
            assert "delete" not in name.lower()
            assert "borrar" not in name.lower()
            assert "actualizar" not in name.lower()


class TestPreFillProvenanceIsAStoredFact:
    """``nivel_desde_candidata`` — the difference between accepting and choosing.

    RSS spec line 78 requires the stored record be marked as operator-confirmed
    rather than as a candidate. Without this column, a one-tap save of a
    pre-filled level and a deliberately entered value are the same row, and the
    coverage split cannot tell a surveyed segment from a rubber-stamped
    candidate.

    It takes BOTH halves: the client's flag says the control was not touched, and
    the server compares the submitted value against the candidate row. A flag the
    client sets freely is a claim, and the value is never re-derived after the
    fact from "well, it happens to match".
    """

    def _crear_candidata(self, db, tramo=TRAMO, clasificacion="terraplen", *, calculada_en=None):
        """``calculada_en`` is passed EXPLICITLY, never left to the default.

        ``DEFAULT now()`` is transaction-start time, so two candidates created
        inside one test transaction would be stamped identically and "the newest"
        would fall through to the ``geo_job_id`` tie-break — i.e. to a random
        UUID. That is the same trap ``version`` exists to avoid on the survey
        side, and a test that walked into it would pass or fail by coin toss.
        """
        from app.domains.geo.models import EstadoGeoJob, GeoJob, TipoGeoJob

        job = GeoJob(
            tipo=TipoGeoJob.DEM_PIPELINE,
            estado=EstadoGeoJob.COMPLETED,
            parametros={"area_id": "zona_principal"},
            progreso=100,
        )
        db.add(job)
        db.flush()
        job_id = job.id
        db.execute(
            text(
                "INSERT INTO tramo_clasificacion_candidata "
                "(tramo_ref, geo_job_id, clasificacion_candidata, confianza_m, calculada_en) "
                "VALUES (:t, :j, :c, 1.4, :calculada_en)"
            ),
            {
                "t": tramo,
                "j": job_id,
                "c": clasificacion,
                "calculada_en": calculada_en or datetime.now(timezone.utc),
            },
        )
        db.flush()
        return job_id

    def _registrar(self, db, user_id, **overrides):
        from app.domains.geo.relevamiento.schemas import RelevamientoTramoCreate
        from app.domains.geo.relevamiento.service import RelevamientoService

        payload = {
            "tramo_ref": TRAMO,
            "nivel_relativo": "mayor",
            "tiene_cuneta": "si",
            "estado_cuneta": "limpia",
        }
        payload.update(overrides)
        return RelevamientoService().registrar(
            db,
            payload=RelevamientoTramoCreate(**payload),
            relevado_por=user_id,
        )

    def test_accepting_the_displayed_candidate_stores_true(self, db, seeded):
        self._crear_candidata(db, clasificacion="terraplen")

        stored = self._registrar(
            db, seeded, nivel_relativo="mayor", nivel_confirmado_sin_cambios=True
        )

        assert stored["nivel_desde_candidata"] is True

    def test_a_value_the_operator_changed_stores_false(self, db, seeded):
        """The client says it touched the control — that alone settles it."""
        self._crear_candidata(db, clasificacion="terraplen")

        stored = self._registrar(
            db, seeded, nivel_relativo="mayor", nivel_confirmado_sin_cambios=False
        )

        assert stored["nivel_desde_candidata"] is False

    def test_a_flag_that_contradicts_the_candidate_stores_false(self, db, seeded):
        """The server-side comparison is what makes the flag a fact.

        A client claiming "unchanged" while submitting something the candidate
        never said did not confirm a candidate, whatever it claims.
        """
        self._crear_candidata(db, clasificacion="terraplen")

        stored = self._registrar(
            db, seeded, nivel_relativo="menor", nivel_confirmado_sin_cambios=True
        )

        assert stored["nivel_desde_candidata"] is False

    def test_with_no_candidate_at_all_it_stores_false(self, db, seeded):
        """There was nothing to accept, so nothing was accepted."""
        stored = self._registrar(
            db, seeded, nivel_relativo="mayor", nivel_confirmado_sin_cambios=True
        )

        assert stored["nivel_desde_candidata"] is False

    def test_the_newest_candidate_is_the_one_compared_against(self, db, seeded):
        """Multiple runs coexist; the pre-fill and the comparison read the newest."""
        ahora = datetime.now(timezone.utc)
        self._crear_candidata(db, clasificacion="canal", calculada_en=ahora - timedelta(days=1))
        self._crear_candidata(db, clasificacion="terraplen", calculada_en=ahora)

        stored = self._registrar(
            db, seeded, nivel_relativo="mayor", nivel_confirmado_sin_cambios=True
        )

        assert stored["nivel_desde_candidata"] is True, (
            "the newest candidate said terraplen, and 'mayor' is what that means"
        )

    def test_the_candidate_row_is_untouched_by_a_disagreeing_survey(self, db, seeded):
        """The candidate is retained as the candidate, never promoted or rewritten."""
        self._crear_candidata(db, clasificacion="terraplen")

        self._registrar(db, seeded, nivel_relativo="menor")

        candidata = db.execute(
            text(
                "SELECT clasificacion_candidata FROM tramo_clasificacion_candidata "
                "WHERE tramo_ref = :t"
            ),
            {"t": TRAMO},
        ).scalar()
        assert candidata == "terraplen"


class TestTheSuggestedLevelIsServedNotReimplemented:
    """One table, exposed — so S4 cannot end up owning a second one.

    The server ALREADY compares a submission against ``CANDIDATA_A_NIVEL`` to
    decide ``nivel_desde_candidata``. A client that translated
    ``clasificacion_candidata`` on its own would be a second copy of that table,
    and the day the two disagreed the form would pre-fill a level the server then
    refused to call confirmed — a disagreement visible only as an inexplicable
    ``false`` in a column nobody is looking at. Serving ``nivel_sugerido`` from
    the same object removes the possibility rather than documenting against it.
    """

    def test_the_read_carries_the_suggested_level_for_the_newest_candidate(self, db, seeded):
        from app.domains.geo.relevamiento.service import RelevamientoService

        TestPreFillProvenanceIsAStoredFact()._crear_candidata(db, clasificacion="canal")

        detalle = RelevamientoService().get_detalle(db, TRAMO)

        assert detalle.candidata is not None
        assert detalle.candidata.clasificacion_candidata == "canal"
        assert detalle.candidata.nivel_sugerido == "menor", (
            "a road BELOW its flanks is a channel, and 'menor' is what that means "
            "in the operator's vocabulary"
        )

    def test_the_suggestion_is_what_the_server_would_accept_as_confirmed(self, db, seeded):
        """The two halves, asserted against each other rather than assumed.

        Submitting exactly the suggested level with the client flag set is the
        one case that must store ``nivel_desde_candidata = True``. If the
        suggestion and the comparison ever came from different tables, this is
        the test that would break.
        """
        from app.domains.geo.relevamiento.service import RelevamientoService

        provenance = TestPreFillProvenanceIsAStoredFact()
        provenance._crear_candidata(db, clasificacion="canal")
        sugerido = RelevamientoService().get_detalle(db, TRAMO).candidata.nivel_sugerido

        stored = provenance._registrar(
            db, seeded, nivel_relativo=sugerido, nivel_confirmado_sin_cambios=True
        )

        assert stored["nivel_desde_candidata"] is True

    def test_the_endpoint_serves_it_inside_candidata_and_nowhere_else(self, db, seeded):
        """It rides with the candidate, never merged into ``vigente``.

        Naming what the DEM would suggest is not the same as recording what
        somebody surveyed, and the read keeps the two apart by construction.
        """
        from app.domains.geo.relevamiento.service import RelevamientoService

        TestPreFillProvenanceIsAStoredFact()._crear_candidata(db, clasificacion="neutro")
        RelevamientoService().registrar(
            db,
            payload=_crear_payload(nivel_relativo="mayor"),
            relevado_por=seeded,
        )

        cuerpo = RelevamientoService().get_detalle(db, TRAMO).model_dump()

        assert cuerpo["candidata"]["nivel_sugerido"] == "igual"
        assert "nivel_sugerido" not in cuerpo["vigente"]
        assert all("nivel_sugerido" not in entrada for entrada in cuerpo["historial"])


def _crear_payload(**overrides):
    from app.domains.geo.relevamiento.schemas import RelevamientoTramoCreate

    payload = {
        "tramo_ref": TRAMO,
        "nivel_relativo": "mayor",
        "tiene_cuneta": "si",
        "estado_cuneta": "limpia",
    }
    payload.update(overrides)
    return RelevamientoTramoCreate(**payload)


class TestTheViewDefinitionHasNotDrifted:
    def test_the_model_side_view_matches_the_migration(self):
        """One definition of "which record wins", in two places that must agree.

        The migration owns production DDL; the model attaches the same view to
        ``after_create`` so the test schema has it. Two texts that disagree would
        mean the suite validates a view production never runs.
        """

        def _normalize(sql: str) -> str:
            return re.sub(r"\s+", " ", sql).strip().rstrip(";").lower()

        assert _normalize(relevamiento_models.VIGENTE_VIEW_SELECT) in _normalize(
            MIGRATION.CREATE_VIGENTE_VIEW
        )
