"""Vector artifact round-trip + the staging load (tasks 3.3, 3.4).

Two layers, deliberately split so the important one runs everywhere:

* the COPY-literal round-trip and the **pre-flight** (which units are exempt from
  embedding, and are those the ones actually missing?) need no `vector` column at
  all, so they run on the DEFAULT vector-less image alongside the rest of CI;
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
    EMBEDDING_DIMENSIONS,
    VectorsManifest,
    copy_line,
    parse_vector_literal,
    sha256_file,
    vector_literal,
)

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


def make_manifest(*, n_vectors: int, over_ceiling: tuple[str, ...] = (), **overrides):
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
