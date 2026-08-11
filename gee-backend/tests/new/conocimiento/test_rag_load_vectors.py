"""Vector artifact round-trip + the staging load (tasks 3.3, 3.4).

Two layers, deliberately split so the important one runs everywhere:

* the COPY-literal round-trip and the **pre-flight** (which units are exempt from
  embedding, are those the ones actually missing, and is this artifact even from
  the model this snapshot already holds?) need no `vector` column at all, so they
  run on the DEFAULT vector-less image alongside the rest of CI;
* the staging `COPY` + `UPDATE … FROM` needs pgvector and is marked accordingly.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.conocimiento.embedding import (
    DEFAULT_MODEL_ID,
    DETERMINISTIC_MODEL_ID,
    EMBEDDING_DIMENSIONS,
    VectorsManifest,
    copy_line,
    parse_vector_literal,
    sha256_file,
    vector_literal,
)
from app.domains.conocimiento.repository import leer_procedencia, registrar_procedencia

#: `intfloat/multilingual-e5-large` is the artifact that makes RAG3-001 concrete
#: rather than theoretical: 1024 dimensions exactly like BGE-M3, so every
#: dimension check passes, and prefix-asymmetric (`query:` / `passage:`), so
#: loading it over a BGE-M3 corpus destroys retrieval without a single error.
#: It is also already in `requirements-rag.txt` as the O.5 baseline leg, so it is
#: a dump this repository can really produce by accident.
E5_MODEL_ID = "intfloat/multilingual-e5-large"

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "rag_load_vectors.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("rag_load_vectors", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


rag_load_vectors = _load_script()

SHA = "b" * 40


def _vector(seed: float) -> list[float]:
    return [seed + i * 1e-3 for i in range(EMBEDDING_DIMENSIONS)]


def seed_snapshot(db, claves: list[str], *, activo: bool = True) -> None:
    """A minimal snapshot: one corpus row, one document, N units."""
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', :n, :activo)"
        ),
        {"sha": SHA, "n": len(claves), "activo": activo},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES "
            "(:sha, 'ley-x', 'ley-provincial', false, 'provincial', 'vigente', 'privado')"
        ),
        {"sha": SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "epigrafe, texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, :key, 'ley-x', 'articulo', 'e', :texto, :texto, 'l.md', 0)"
        ),
        [{"sha": SHA, "key": key, "texto": f"texto de {key}"} for key in claves],
    )
    db.flush()


def registrar(db, *, modelo: str = DEFAULT_MODEL_ID, sintetico: bool = False) -> None:
    """Pretend a previous load already stamped this snapshot's provenance."""
    registrar_procedencia(
        db,
        SHA,
        modelo=modelo,
        revision_hf=None if sintetico else "c" * 40,
        sintetico=sintetico,
        artifact_sha256="9" * 64,
    )
    db.flush()


#: Token count stamped on exemptions this helper builds from a bare key. An
#: arbitrary but PLAUSIBLE over-ceiling measurement: every test that passes bare
#: keys is about the identity of the exempt key SET, where the count only has to
#: survive the round-trip. The tests that care about the number itself pass
#: explicit `(key, tokens)` pairs.
TOKENS_EXENTA_FIXTURE = 9001


def make_manifest(*, n_vectors: int, over_ceiling: tuple = (), **overrides):
    over_ceiling = tuple(
        (entrada, TOKENS_EXENTA_FIXTURE) if isinstance(entrada, str) else tuple(entrada)
        for entrada in over_ceiling
    )
    campos = {
        "corpus_sha": SHA,
        "modelo": "BAAI/bge-m3",
        "revision_hf": "c" * 40,
        "dims": EMBEDDING_DIMENSIONS,
        "normalized": True,
        "sintetico": False,
        "n_vectors": n_vectors,
        "sha256": "0" * 64,
        "over_ceiling": over_ceiling,
        "token_ceiling": 8192,
        "torch": "2.9.0",
        "transformers": "4.60.0",
        "device": "cuda:0",
        "generado_en": "2026-08-10T00:00:00+00:00",
    }
    campos.update(overrides)
    return VectorsManifest(**campos)


class TestCopyLiteralRoundTrip:
    """3.3: the pgvector COPY-text literal round-trips a synthetic vector unchanged."""

    def test_copy_literal_roundtrip(self):
        original = [0.1, -0.25, 1.0, 0.0, 3.4028235e38, 1.1754944e-38]
        recuperado = parse_vector_literal(vector_literal(original))

        assert len(recuperado) == len(original)
        for esperado, real in zip(original, recuperado):
            # float32 is the storage type (pgvector stores float4), so the
            # round-trip is exact at float32 precision, not at float64.
            assert real == pytest.approx(esperado, rel=1e-7, abs=1e-45)

    def test_literal_shape_is_what_pgvector_parses(self):
        assert vector_literal([1.0, 2.0]) == "[1,2]"

    def test_float32_narrowing_is_deliberate_and_lossless_on_reload(self):
        """0.1 has no float32 representation; the literal must still reload equal.

        `%.9g` is FLT_DECIMAL_DIG: the shortest decimal form guaranteed to
        recover the same float32. Writing the float64 repr instead would be
        larger and buy nothing, because PostgreSQL narrows it on the way in.
        """
        literal = vector_literal([0.1])
        assert literal == "[0.100000001]"
        assert parse_vector_literal(literal) == parse_vector_literal(
            vector_literal(parse_vector_literal(literal))
        )

    def test_copy_line_is_tab_separated_and_newline_terminated(self):
        linea = copy_line(SHA, "9750#3", [1.0, 2.0], dims=2)
        assert linea == f"{SHA}\t9750#3\t[1,2]\n"

    def test_copy_line_escapes_the_copy_text_metacharacters(self):
        """A tab or a backslash in a key would silently shift every column."""
        linea = copy_line(SHA, "raro\tclave\\x", [1.0], dims=1)
        assert linea.split("\t")[1] == "raro\\tclave\\\\x"

    def test_wrong_dimension_is_refused_at_write_time(self):
        with pytest.raises(ValueError, match="1024"):
            copy_line(SHA, "9750#3", [1.0, 2.0], dims=EMBEDDING_DIMENSIONS)

    def test_sha256_file_matches_hashlib(self, tmp_path):
        path = tmp_path / "v.copy"
        path.write_bytes(b"abc\n")
        assert sha256_file(path) == hashlib.sha256(b"abc\n").hexdigest()


class TestManifestSerialization:
    def test_manifest_round_trips_through_json(self, tmp_path):
        manifest = make_manifest(n_vectors=3, over_ceiling=("10593#1",))
        path = tmp_path / "vectors-abcdef12.json"
        manifest.write(path)
        assert VectorsManifest.load(path) == manifest

    def test_over_ceiling_is_a_required_key_not_an_optional_one(self, tmp_path):
        """A manifest without it is from before the exemption existed — refuse it.

        Defaulting the field to `()` would read a pre-exemption artifact as
        "nothing is exempt" and then reject the load for a count mismatch with a
        message about arithmetic instead of about provenance.
        """
        path = tmp_path / "vectors-abcdef12.json"
        raw = json.loads(make_manifest(n_vectors=3).to_json())
        del raw["over_ceiling"]
        path.write_text(json.dumps(raw), encoding="utf-8")

        with pytest.raises(ValueError, match="over_ceiling"):
            VectorsManifest.load(path)


class TestPreflightExemptionIdentity:
    """A1 / ledger R3-104: the pre-check pins WHICH units are exempt, not how many."""

    def test_happy_path_with_no_exemption(self, db):
        seed_snapshot(db, ["9750#1", "9750#2", "9750#3"])
        rag_load_vectors.preflight(db, make_manifest(n_vectors=3), {"9750#1", "9750#2", "9750#3"})

    def test_happy_path_with_a_declared_exemption(self, db):
        seed_snapshot(db, ["9750#1", "9750#2", "10593#1"])
        rag_load_vectors.preflight(
            db,
            make_manifest(n_vectors=2, over_ceiling=("10593#1",)),
            {"9750#1", "9750#2"},
        )

    def test_bare_count_check_would_reject_the_ratified_over_ceiling_dump(self, db):
        """The check the design USED to specify, shown failing on a correct dump.

        `n_vectors == count(rag_unidad)` contradicts the ratified V0 decision
        that over-ceiling units are ingested whole and never embedded: a correct
        artifact is always short by exactly the exempt units.
        """
        seed_snapshot(db, ["9750#1", "9750#2", "10593#1"])
        total = db.execute(
            text("SELECT count(*) FROM rag_unidad WHERE corpus_sha = :sha"), {"sha": SHA}
        ).scalar_one()
        assert total == 3
        manifest = make_manifest(n_vectors=2, over_ceiling=("10593#1",))
        assert manifest.n_vectors != total
        assert manifest.n_vectors == total - len(manifest.over_ceiling)

    def test_arbitrary_missing_vector_is_rejected_where_a_count_would_pass(self, db):
        """The exact hole a count-only exemption leaves, shown closed.

        The arithmetic is IDENTICAL to a correct load — 3 units, 1 declared
        exempt, 2 vectors — so `n_vectors == count − |over_ceiling|` passes. But
        the exempt unit was embedded and a real one was dropped: a batch that
        lost a shard, resumed wrong, or mis-sliced. Under a count-only check this
        loads clean and `9750#2` is silently unreachable through the vector leg
        while every number in the report looks right.
        """
        seed_snapshot(db, ["9750#1", "9750#2", "10593#1"])
        manifest = make_manifest(n_vectors=2, over_ceiling=("10593#1",))
        claves_dump = {"9750#1", "10593#1"}  # embedded the exempt one, dropped a real one

        # The check the design used to specify would have accepted this.
        total = db.execute(
            text("SELECT count(*) FROM rag_unidad WHERE corpus_sha = :sha"), {"sha": SHA}
        ).scalar_one()
        assert manifest.n_vectors == total - len(manifest.over_ceiling)

        with pytest.raises(rag_load_vectors.PreflightFailure) as abort:
            rag_load_vectors.preflight(db, manifest, claves_dump)
        assert "10593#1" in str(abort.value)

    def test_uncovered_unit_is_rejected_even_with_a_consistent_dump(self, db):
        """The other half of the identity check: a unit in neither list.

        The dump is internally consistent (its key count matches `n_vectors`) and
        the exempt key really is absent from it — everything a per-artifact check
        can see is fine. Only the comparison against the SNAPSHOT reveals that
        `9750#2` was never embedded and never exempted.
        """
        seed_snapshot(db, ["9750#1", "9750#2", "10593#1"])

        with pytest.raises(rag_load_vectors.PreflightFailure, match="9750#2"):
            rag_load_vectors.preflight(
                db,
                make_manifest(n_vectors=1, over_ceiling=("10593#1",)),
                {"9750#1"},
            )

    def test_exempt_key_that_is_not_a_unit_is_rejected(self, db):
        seed_snapshot(db, ["9750#1", "9750#2"])

        with pytest.raises(rag_load_vectors.PreflightFailure, match="no-existe#1"):
            rag_load_vectors.preflight(
                db,
                make_manifest(n_vectors=2, over_ceiling=("no-existe#1",)),
                {"9750#1", "9750#2"},
            )

    def test_exempt_key_present_in_the_dump_is_rejected(self, db):
        seed_snapshot(db, ["9750#1", "10593#1"])

        with pytest.raises(rag_load_vectors.PreflightFailure, match="10593#1"):
            rag_load_vectors.preflight(
                db,
                make_manifest(n_vectors=2, over_ceiling=("10593#1",)),
                {"9750#1", "10593#1"},
            )

    def test_orphan_key_in_the_dump_is_rejected(self, db):
        seed_snapshot(db, ["9750#1"])

        with pytest.raises(rag_load_vectors.PreflightFailure, match="fantasma#1"):
            rag_load_vectors.preflight(db, make_manifest(n_vectors=2), {"9750#1", "fantasma#1"})

    def test_n_vectors_disagreeing_with_the_dump_is_rejected(self, db):
        seed_snapshot(db, ["9750#1", "9750#2"])

        with pytest.raises(rag_load_vectors.PreflightFailure, match="n_vectors"):
            rag_load_vectors.preflight(db, make_manifest(n_vectors=99), {"9750#1", "9750#2"})

    def test_wrong_dims_is_rejected(self, db):
        seed_snapshot(db, ["9750#1"])

        with pytest.raises(rag_load_vectors.PreflightFailure, match="dims"):
            rag_load_vectors.preflight(db, make_manifest(n_vectors=1, dims=768), {"9750#1"})

    def test_unknown_snapshot_is_rejected(self, db):
        with pytest.raises(rag_load_vectors.PreflightFailure, match="snapshot"):
            rag_load_vectors.preflight(db, make_manifest(n_vectors=0), set())

    def test_inactive_snapshot_is_rejected(self, db):
        seed_snapshot(db, ["9750#1"], activo=False)

        with pytest.raises(rag_load_vectors.PreflightFailure, match="activo"):
            rag_load_vectors.preflight(db, make_manifest(n_vectors=1), {"9750#1"})

    def test_synthetic_artifact_is_refused_by_default(self, db):
        seed_snapshot(db, ["9750#1"])

        with pytest.raises(rag_load_vectors.PreflightFailure, match="SINTÉTICO"):
            rag_load_vectors.preflight(db, make_manifest(n_vectors=1, sintetico=True), {"9750#1"})

    def test_synthetic_artifact_loads_only_when_explicitly_allowed(self, db):
        seed_snapshot(db, ["9750#1"])
        rag_load_vectors.preflight(
            db,
            make_manifest(n_vectors=1, sintetico=True),
            {"9750#1"},
            permitir_sintetico=True,
        )


class TestEmbeddingProvenanceRecord:
    """conocimiento_004: the sidecar stops being read-and-discarded.

    No `vector` column is involved — provenance lives on `rag_corpus` — so these
    run in the shape CI actually executes.
    """

    def test_a_never_embedded_snapshot_reports_no_provenance(self, db):
        seed_snapshot(db, ["9750#1"])
        procedencia = leer_procedencia(db, SHA)

        assert procedencia is not None
        assert procedencia.modelo is None
        assert procedencia.cargado is False

    def test_unknown_snapshot_and_unembedded_snapshot_are_different_answers(self, db):
        """A typo in a corpus SHA must not read as "ingested but not embedded"."""
        seed_snapshot(db, ["9750#1"])
        assert leer_procedencia(db, "0" * 40) is None
        assert leer_procedencia(db, SHA) is not None

    def test_registering_provenance_records_every_field(self, db):
        seed_snapshot(db, ["9750#1"])

        filas = registrar_procedencia(
            db,
            SHA,
            modelo=DEFAULT_MODEL_ID,
            revision_hf="c" * 40,
            sintetico=False,
            artifact_sha256="a" * 64,
        )
        db.flush()
        procedencia = leer_procedencia(db, SHA)

        assert filas == 1
        assert procedencia is not None
        assert procedencia.modelo == DEFAULT_MODEL_ID
        assert procedencia.revision_hf == "c" * 40
        assert procedencia.sintetico is False
        assert procedencia.artifact_sha256 == "a" * 64
        assert procedencia.loaded_at is not None
        assert procedencia.cargado is True

    def test_registering_an_unknown_snapshot_touches_nothing(self, db):
        """The loader turns this into an abort; here it must simply be 0 rows."""
        seed_snapshot(db, ["9750#1"])
        assert (
            registrar_procedencia(
                db,
                "0" * 40,
                modelo=DEFAULT_MODEL_ID,
                revision_hf=None,
                sintetico=False,
                artifact_sha256="a" * 64,
            )
            == 0
        )


class TestDiagnosticSample:
    """The key samples in every abort message are bounded and say so."""

    def test_a_short_set_is_printed_whole(self):
        assert rag_load_vectors._muestra(["9750#1", "9750#2"]) == "['9750#1', '9750#2']"

    def test_a_long_set_is_capped_and_declares_the_remainder(self):
        muestra = rag_load_vectors._muestra([f"k{i:02d}" for i in range(25)])

        assert "k09" in muestra
        assert "k10" not in muestra, "the cap is 10 keys"
        assert "(+15 more)" in muestra, "…and a truncated list must never look complete"


class TestModelReplacementGate:
    """RAG3-001: which model wrote these vectors, and did anyone authorise a swap?

    The gate the loader used to have was `dims == 1024`, which is not a check on
    the model. Every case below passes that check.
    """

    def test_first_load_into_a_never_embedded_snapshot_is_allowed(self, db):
        seed_snapshot(db, ["9750#1"])
        rag_load_vectors.preflight(db, make_manifest(n_vectors=1), {"9750#1"})

    def test_replace_model_on_a_never_embedded_snapshot_is_refused(self, db):
        """There is no model to replace, so the flag is a misunderstanding."""
        seed_snapshot(db, ["9750#1"])

        with pytest.raises(rag_load_vectors.ModelMismatch, match="nothing to replace"):
            rag_load_vectors.preflight(
                db, make_manifest(n_vectors=1), {"9750#1"}, reemplazar_modelo=True
            )

    def test_reloading_the_same_model_needs_no_flag(self, db):
        seed_snapshot(db, ["9750#1"])
        registrar(db)
        rag_load_vectors.preflight(db, make_manifest(n_vectors=1), {"9750#1"})

    def test_replace_model_is_refused_when_the_models_already_match(self, db):
        """The anti-cargo-cult half: a flag accepted when it changes nothing
        stops being a gate and becomes boilerplate in somebody's runbook."""
        seed_snapshot(db, ["9750#1"])
        registrar(db)

        with pytest.raises(rag_load_vectors.ModelMismatch, match="no model change"):
            rag_load_vectors.preflight(
                db, make_manifest(n_vectors=1), {"9750#1"}, reemplazar_modelo=True
            )

    def test_e5_artifact_over_a_bge_snapshot_is_refused(self, db):
        """The concrete RAG3-001 scenario: same dims, different geometry.

        1024 dimensions, so the surviving pre-check passes; asymmetric prefixes,
        so the retrieval it produces is noise. Nothing but the recorded model id
        can tell the two apart.
        """
        seed_snapshot(db, ["9750#1"])
        registrar(db, modelo=DEFAULT_MODEL_ID)
        manifest = make_manifest(n_vectors=1, modelo=E5_MODEL_ID, dims=EMBEDDING_DIMENSIONS)

        with pytest.raises(rag_load_vectors.ModelMismatch) as abort:
            rag_load_vectors.preflight(db, manifest, {"9750#1"})

        mensaje = str(abort.value)
        assert DEFAULT_MODEL_ID in mensaje, "the refusal must name the model in the database"
        assert E5_MODEL_ID in mensaje, "…and the model in the artifact"
        assert manifest.dims == EMBEDDING_DIMENSIONS, "the dims check cannot see this"

    def test_e5_artifact_loads_when_the_replacement_is_explicit(self, db):
        seed_snapshot(db, ["9750#1"])
        registrar(db, modelo=DEFAULT_MODEL_ID)
        rag_load_vectors.preflight(
            db,
            make_manifest(n_vectors=1, modelo=E5_MODEL_ID),
            {"9750#1"},
            reemplazar_modelo=True,
        )

    def test_synthetic_to_real_is_the_heal_path_and_needs_no_flag(self, db):
        """Replacing hash noise with a real model is the one direction that
        needs no permission: friction belongs on the damage, not on the fix."""
        seed_snapshot(db, ["9750#1"])
        registrar(db, modelo=DETERMINISTIC_MODEL_ID, sintetico=True)

        rag_load_vectors.preflight(
            db, make_manifest(n_vectors=1, modelo=DEFAULT_MODEL_ID, sintetico=False), {"9750#1"}
        )

    def test_real_to_synthetic_is_refused_with_allow_synthetic_alone(self, db):
        seed_snapshot(db, ["9750#1"])
        registrar(db, modelo=DEFAULT_MODEL_ID, sintetico=False)
        manifest = make_manifest(n_vectors=1, modelo=DETERMINISTIC_MODEL_ID, sintetico=True)

        with pytest.raises(rag_load_vectors.ModelMismatch, match="--replace-model"):
            rag_load_vectors.preflight(db, manifest, {"9750#1"}, permitir_sintetico=True)

    def test_real_to_synthetic_is_refused_with_replace_model_alone(self, db):
        """`--allow-synthetic` still guards the artifact itself, first."""
        seed_snapshot(db, ["9750#1"])
        registrar(db, modelo=DEFAULT_MODEL_ID, sintetico=False)
        manifest = make_manifest(n_vectors=1, modelo=DETERMINISTIC_MODEL_ID, sintetico=True)

        with pytest.raises(rag_load_vectors.PreflightFailure, match="SINTÉTICO"):
            rag_load_vectors.preflight(db, manifest, {"9750#1"}, reemplazar_modelo=True)

    def test_real_to_synthetic_needs_both_flags(self, db):
        seed_snapshot(db, ["9750#1"])
        registrar(db, modelo=DEFAULT_MODEL_ID, sintetico=False)

        rag_load_vectors.preflight(
            db,
            make_manifest(n_vectors=1, modelo=DETERMINISTIC_MODEL_ID, sintetico=True),
            {"9750#1"},
            permitir_sintetico=True,
            reemplazar_modelo=True,
        )

    def test_the_cli_exposes_replace_model_with_its_own_exit_code(self):
        """A wrapper must be able to tell "broken artifact" from "other model"."""
        args = rag_load_vectors.build_parser().parse_args(
            ["--vectors", "v.copy", "--database-url", "postgresql:///x", "--replace-model"]
        )
        assert args.replace_model is True
        assert issubclass(rag_load_vectors.ModelMismatch, rag_load_vectors.PreflightFailure)


@pytest.mark.pgvector
class TestStagingLoad:
    """3.4: COPY → staging → `UPDATE … FROM`, all-or-nothing."""

    def _artifact(self, tmp_path, claves, *, over_ceiling=(), extra=()):
        copy_path = tmp_path / "vectors-bbbbbbbb.copy"
        with copy_path.open("w", encoding="utf-8") as handle:
            for i, key in enumerate([*claves, *extra]):
                handle.write(copy_line(SHA, key, _vector(0.01 * (i + 1))))
        manifest = make_manifest(
            n_vectors=len(claves) + len(extra),
            over_ceiling=tuple(over_ceiling),
            sha256=sha256_file(copy_path),
        )
        manifest.write(copy_path.with_suffix(".json"))
        return copy_path, manifest

    def test_load_updates_every_row(self, pgvector_db, tmp_path):
        claves = ["9750#1", "9750#2", "9750#3"]
        seed_snapshot(pgvector_db, claves)
        copy_path, _ = self._artifact(tmp_path, claves)

        actualizadas = rag_load_vectors.load_vectors(pgvector_db, copy_path)

        assert actualizadas == 3
        faltantes = pgvector_db.execute(
            text("SELECT count(*) FROM rag_unidad WHERE corpus_sha = :sha AND embedding IS NULL"),
            {"sha": SHA},
        ).scalar_one()
        assert faltantes == 0

    def test_over_ceiling_units_are_left_null_on_purpose(self, pgvector_db, tmp_path):
        seed_snapshot(pgvector_db, ["9750#1", "9750#2", "10593#1"])
        copy_path, _ = self._artifact(tmp_path, ["9750#1", "9750#2"], over_ceiling=("10593#1",))

        assert rag_load_vectors.load_vectors(pgvector_db, copy_path) == 2

        sin_vector = pgvector_db.execute(
            text(
                "SELECT citation_key FROM rag_unidad WHERE corpus_sha = :sha "
                "AND embedding IS NULL ORDER BY citation_key"
            ),
            {"sha": SHA},
        ).scalars()
        assert list(sin_vector) == ["10593#1"]

    def test_load_aborts_on_orphan_key_leaves_embeddings_null(self, pgvector_db, tmp_path):
        """One unknown key in the dump must abort the whole transaction."""
        claves = ["9750#1", "9750#2"]
        seed_snapshot(pgvector_db, claves)
        copy_path, _ = self._artifact(tmp_path, claves, extra=("fantasma#1",))

        with pytest.raises(rag_load_vectors.PreflightFailure, match="fantasma#1"):
            rag_load_vectors.load_vectors(pgvector_db, copy_path)

        faltantes = pgvector_db.execute(
            text(
                "SELECT count(*) FROM rag_unidad WHERE corpus_sha = :sha AND embedding IS NOT NULL"
            ),
            {"sha": SHA},
        ).scalar_one()
        assert faltantes == 0

    def test_tampered_dump_is_refused_before_the_database_is_touched(self, pgvector_db, tmp_path):
        claves = ["9750#1"]
        seed_snapshot(pgvector_db, claves)
        copy_path, _ = self._artifact(tmp_path, claves)
        copy_path.write_text(copy_path.read_text(encoding="utf-8"), encoding="utf-8")
        copy_path.write_text(
            copy_path.read_text(encoding="utf-8").replace("9750#1", "9750#9"),
            encoding="utf-8",
        )

        with pytest.raises(rag_load_vectors.ArtifactMismatch, match="sha256"):
            rag_load_vectors.load_vectors(pgvector_db, copy_path)

    def test_load_records_provenance_in_the_load_transaction(self, pgvector_db, tmp_path):
        """RAG3-001: the sidecar reaches the database instead of being discarded."""
        claves = ["9750#1", "9750#2"]
        seed_snapshot(pgvector_db, claves)
        copy_path, manifest = self._artifact(tmp_path, claves)

        rag_load_vectors.load_vectors(pgvector_db, copy_path)

        procedencia = leer_procedencia(pgvector_db, SHA)
        assert procedencia is not None
        assert procedencia.modelo == manifest.modelo
        assert procedencia.revision_hf == manifest.revision_hf
        assert procedencia.sintetico is False
        assert procedencia.artifact_sha256 == manifest.sha256
        assert procedencia.loaded_at is not None

    def test_a_crash_after_the_writes_rolls_back_vectors_AND_provenance(
        self, pgvector_db, tmp_path, monkeypatch
    ):
        """The two writes are one fact, so they must fail as one.

        Provenance that outlived a rolled-back load would be the worst of both
        states: `rag_corpus` claiming a model for a column that is still NULL,
        and `service.recuperar` cheerfully accepting an embedder for vectors
        that do not exist. Simulated at the last possible moment — after the
        `UPDATE` and after the stamp — because that is where the window is.
        """
        claves = ["9750#1", "9750#2"]
        seed_snapshot(pgvector_db, claves)
        copy_path, _ = self._artifact(tmp_path, claves)

        def estallar(*_args, **_kwargs):
            raise RuntimeError("simulated crash after the UPDATE and the provenance stamp")

        monkeypatch.setattr(rag_load_vectors, "verificar_post_carga", estallar)

        punto = pgvector_db.begin_nested()
        with pytest.raises(RuntimeError, match="simulated crash"):
            rag_load_vectors.load_vectors(pgvector_db, copy_path)
        punto.rollback()

        con_vector = pgvector_db.execute(
            text(
                "SELECT count(*) FROM rag_unidad WHERE corpus_sha = :sha AND embedding IS NOT NULL"
            ),
            {"sha": SHA},
        ).scalar_one()
        procedencia = leer_procedencia(pgvector_db, SHA)

        assert con_vector == 0, "the vectors must not survive the rollback"
        assert procedencia is not None and procedencia.cargado is False, (
            "…and neither must the provenance stamp"
        )

    def test_post_load_mismatch_names_both_directions(self, pgvector_db, tmp_path):
        """RAG3-003: two different accidents share this symptom.

        `sin vector y sin exención` is a dropped shard or a mis-slice;
        `exentas pero embebidas` is a ceiling applied to a different set than the
        one disclosed. The old message printed only the first, so the second
        rendered as an empty list next to prose about a set difference.
        """
        seed_snapshot(pgvector_db, ["9750#1", "9750#2", "10593#1"])
        pgvector_db.execute(
            text(
                "CREATE TEMP TABLE " + rag_load_vectors.STAGING_TABLE + " (corpus_sha CHAR(40), "
                f"citation_key TEXT, embedding vector({EMBEDDING_DIMENSIONS})) ON COMMIT DROP"
            )
        )
        pgvector_db.execute(
            text(
                "UPDATE rag_unidad SET embedding = CAST(:v AS vector) WHERE corpus_sha = :sha "
                "AND citation_key = '9750#1'"
            ),
            {"v": vector_literal(_vector(0.5)), "sha": SHA},
        )
        # Declares 9750#1 exempt (it was embedded anyway) and says nothing about
        # 9750#2 (which came out without a vector).
        manifest = make_manifest(n_vectors=1, over_ceiling=("9750#1", "10593#1"))

        with pytest.raises(rag_load_vectors.PreflightFailure) as abort:
            rag_load_vectors.verificar_post_carga(pgvector_db, manifest, actualizadas=1)

        mensaje = str(abort.value)
        assert "sin vector y sin exención (1): ['9750#2']" in mensaje
        assert "exentas pero embebidas (1): ['9750#1']" in mensaje

    def test_loaded_vector_round_trips_out_of_postgres(self, pgvector_db, tmp_path):
        seed_snapshot(pgvector_db, ["9750#1"])
        copy_path, _ = self._artifact(tmp_path, ["9750#1"])
        rag_load_vectors.load_vectors(pgvector_db, copy_path)

        almacenado = pgvector_db.execute(
            text("SELECT embedding::text FROM rag_unidad WHERE corpus_sha = :sha"),
            {"sha": SHA},
        ).scalar_one()
        valores = parse_vector_literal(almacenado)

        assert len(valores) == EMBEDDING_DIMENSIONS
        assert valores[0] == pytest.approx(0.01, rel=1e-6)
