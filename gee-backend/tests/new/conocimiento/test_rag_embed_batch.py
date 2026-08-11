"""Embedding batch script (task 3.2).

The real BGE-M3 run happens once, on the owner's RTX 5060 Ti (Ops O.3). What is
tested here is everything AROUND the model — the pre-flight ceiling, the artifact
format, the manifest's exemption list, determinism and ordering — with a
deterministic fake injected through the `Embedder` seam. That is the whole point
of the seam: the pipeline is verifiable without a 2.2 GB download, and the model
swap in V1 changes one constructor call.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.conocimiento.embedding import (
    DEFAULT_MODEL_ID,
    DETERMINISTIC_MODEL_ID,
    EMBEDDING_DIMENSIONS,
    TOKEN_CEILING,
    DeterministicEmbedder,
    VectorsManifest,
    manifest_path_for,
    parse_vector_literal,
    sha256_file,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "rag_embed_batch.py"
LOADER = Path(__file__).resolve().parents[3] / "scripts" / "rag_load_vectors.py"


def _load(path: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


rag_embed_batch = _load(SCRIPT, "rag_embed_batch")
rag_load_vectors = _load(LOADER, "rag_load_vectors")

SHA = "d" * 40


def seed(db, textos: dict[str, str]) -> None:
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', :n, true)"
        ),
        {"sha": SHA, "n": len(textos)},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES "
            "(:sha, 'ley-x', 'ley-provincial', false, 'provincial', 'vigente', 'privado')"
        ),
        {"sha": SHA},
    )
    if textos:
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                "epigrafe, texto, texto_indexado, source_file, source_offset) VALUES "
                "(:sha, :key, 'ley-x', 'articulo', 'e', :texto, :texto, 'l.md', 0)"
            ),
            [{"sha": SHA, "key": key, "texto": texto} for key, texto in textos.items()],
        )
    db.flush()


class _NullEngine:
    """Stands in for a SQLAlchemy Engine in `main()` tests. House pattern.

    `main()` must open its own engine in production, but a second connection
    cannot see rows the rollback-per-test `db` fixture has only flushed. Handing
    `main()` the test session is what makes its argparse wiring, embedder
    resolution, report and exit code testable against real data at all.
    """

    def dispose(self) -> None:
        return None


class _SessionStub:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc) -> bool:
        return False


CORTO = "Los consorcios canaleros tendrán a su cargo el mantenimiento de la red."
LARGO = "palabra " * (TOKEN_CEILING * 3)  # ~3x the ceiling under any tokenizer


class TestPreflight:
    def test_preflight_aborts_over_ceiling(self):
        """3.2, strict mode: an over-ceiling unit stops the batch, never truncates.

        The MANIFEST forbids splitting long articles, so silent truncation is the
        only failure mode that could survive review: the vector would be of a
        FRAGMENT of the law, indexed under the law's citation key.
        """
        unidades = [("9750#1", CORTO), ("10593#1", LARGO)]

        with pytest.raises(rag_embed_batch.CeilingExceeded, match="10593#1"):
            rag_embed_batch.preflight(unidades, DeterministicEmbedder(), strict=True)

    def test_default_mode_exempts_and_reports_instead_of_aborting(self):
        """The ratified V0 behaviour: ingested whole, embedded never, disclosed always.

        The ceiling belongs to BGE-M3, not to FTS. Aborting ingestion of an
        over-ceiling unit would delete it from the lexical leg too — and the
        FTS-only leg is exactly what slices 1-2 exist to keep independently
        useful for the ablation (design.md D3).
        """
        unidades = [("9750#1", CORTO), ("10593#1", LARGO)]

        a_embeber, exentas = rag_embed_batch.preflight(unidades, DeterministicEmbedder())

        assert [key for key, _ in a_embeber] == ["9750#1"]
        assert [key for key, _ in exentas] == ["10593#1"]
        assert exentas[0][1] > TOKEN_CEILING

    def test_nothing_is_truncated_on_the_way_through(self):
        a_embeber, _ = rag_embed_batch.preflight([("9750#1", CORTO)], DeterministicEmbedder())
        assert a_embeber[0][1] == CORTO


class TestArtifactProduction:
    def _run(self, db, tmp_path, textos):
        seed(db, textos)
        return rag_embed_batch.embed_snapshot(
            db,
            SHA,
            DeterministicEmbedder(),
            output_dir=tmp_path,
            batch_size=2,
        )

    def test_writes_dump_and_sidecar_named_after_the_corpus(self, db, tmp_path):
        copy_path, manifest = self._run(db, tmp_path, {"9750#1": CORTO, "9750#2": CORTO + "!"})

        assert copy_path.name == f"vectors-{SHA[:8]}.copy"
        assert (tmp_path / f"vectors-{SHA[:8]}.json").is_file()
        assert manifest.corpus_sha == SHA
        assert manifest.dims == EMBEDDING_DIMENSIONS
        assert manifest.normalized is True
        assert manifest.n_vectors == 2

    def test_sidecar_sha256_matches_the_dump_on_disk(self, db, tmp_path):
        copy_path, manifest = self._run(db, tmp_path, {"9750#1": CORTO})
        assert manifest.sha256 == sha256_file(copy_path)

    def test_over_ceiling_keys_are_pinned_in_the_manifest(self, db, tmp_path):
        """A1 / R3-104: the exemption is a key list, not a number.

        The loader checks identity against this list; a count would let any
        equally-sized shortfall through.
        """
        copy_path, manifest = self._run(db, tmp_path, {"9750#1": CORTO, "10593#1": LARGO})

        assert manifest.claves_over_ceiling == ("10593#1",)
        assert manifest.n_vectors == 1
        assert "10593#1" not in copy_path.read_text(encoding="utf-8")

    def test_the_manifest_records_the_measured_token_count(self, db, tmp_path):
        """RJDA-007: how far over the ceiling, not merely that it is over.

        `preflight` already measured this with the real tokenizer and the
        manifest threw it away, so the only way back to it was a
        `--preflight-only` rerun — while `rag_embed_batch`'s own summary printed
        `TOKEN_CEILING + 1` for every exempt unit, a fabricated 8193 formatted
        exactly like the measured counts one screen earlier. "How far over"
        decides whether a unit is re-chunked upstream or accepted as FTS-only.
        """
        _, manifest = self._run(db, tmp_path, {"9750#1": CORTO, "10593#1": LARGO})
        ((clave, tokens),) = manifest.over_ceiling
        assert clave == "10593#1"
        assert tokens > manifest.token_ceiling
        # NOT the fabricated placeholder, and equal to what the embedder counts.
        assert tokens != manifest.token_ceiling + 1
        assert tokens == DeterministicEmbedder().count_tokens(LARGO)

    def test_the_measured_count_survives_the_sidecar_round_trip(self, db, tmp_path):
        copy_path, manifest = self._run(db, tmp_path, {"9750#1": CORTO, "10593#1": LARGO})
        releido = VectorsManifest.load(manifest_path_for(copy_path))
        assert releido.over_ceiling == manifest.over_ceiling
        assert releido.claves_over_ceiling == ("10593#1",)

    def test_a_sidecar_from_before_the_counts_is_refused_not_defaulted(self, tmp_path):
        """Reading a bare key list as `(key, 0)` — or as `(key, 8193)` — would
        invent the very measurement this field exists to stop inventing, and the
        invented number would be indistinguishable from a real one. The dump is
        a derived artifact of a SHA-pinned corpus, so re-running the batch is
        always available; reading a stale artifact as an answer is not."""
        import json

        viejo = tmp_path / "vectors-deadbeef.json"
        manifest = VectorsManifest(
            corpus_sha="d" * 40,
            modelo="BAAI/bge-m3",
            revision_hf=None,
            dims=EMBEDDING_DIMENSIONS,
            normalized=True,
            sintetico=False,
            n_vectors=1,
            sha256="0" * 64,
            over_ceiling=(("10593#1", 9001),),
            token_ceiling=8192,
            torch=None,
            transformers=None,
            device="cpu",
            generado_en="2026-08-10T00:00:00+00:00",
        )
        crudo = json.loads(manifest.to_json())
        crudo["over_ceiling"] = ["10593#1"]  # the pre-RJDA-007 shape
        viejo.write_text(json.dumps(crudo), encoding="utf-8")

        with pytest.raises(ValueError, match="bare citation keys"):
            VectorsManifest.load(viejo)

    def test_rows_are_ordered_by_citation_key(self, db, tmp_path):
        copy_path, _ = self._run(
            db, tmp_path, {"9750#3": CORTO, "9750#1": CORTO + "a", "9750#2": CORTO + "b"}
        )
        claves = [
            linea.split("\t")[1] for linea in copy_path.read_text(encoding="utf-8").splitlines()
        ]
        assert claves == ["9750#1", "9750#2", "9750#3"]

    def test_dump_is_byte_identical_across_runs(self, db, tmp_path):
        """Same snapshot in, same bytes out — the artifact is reproducible."""
        seed(db, {"9750#1": CORTO, "9750#2": CORTO + "!"})
        primero, _ = rag_embed_batch.embed_snapshot(
            db, SHA, DeterministicEmbedder(), output_dir=tmp_path / "a"
        )
        segundo, _ = rag_embed_batch.embed_snapshot(
            db, SHA, DeterministicEmbedder(), output_dir=tmp_path / "b"
        )
        assert primero.read_bytes() == segundo.read_bytes()

    def test_vectors_are_unit_norm(self, db, tmp_path):
        """Cosine distance is only meaningful on normalized vectors (design.md D3)."""
        copy_path, _ = self._run(db, tmp_path, {"9750#1": CORTO})
        literal = copy_path.read_text(encoding="utf-8").split("\t")[2]
        valores = parse_vector_literal(literal)

        assert len(valores) == EMBEDDING_DIMENSIONS
        assert sum(v * v for v in valores) ** 0.5 == pytest.approx(1.0, abs=1e-4)

    def test_a_fake_embedder_stamps_the_artifact_as_synthetic(self, db, tmp_path):
        """The smoke-test escape hatch must announce itself in the artifact.

        A retrieval eval run over hash noise would produce a report shaped
        exactly like a real one, so the marker travels with the dump, the loader
        refuses it by default, and — since migration `conocimiento_004` — the
        model id it records is what `service.recuperar` compares the query
        embedder against. `modelo` therefore has to be the fake's REAL identity,
        not a warning label: the warning is `sintetico`, which sits beside it in
        the sidecar and in `rag_corpus`.
        """
        _, manifest = self._run(db, tmp_path, {"9750#1": CORTO})
        assert manifest.sintetico is True
        assert manifest.modelo == DETERMINISTIC_MODEL_ID
        assert manifest.modelo != DEFAULT_MODEL_ID

        raw = json.loads((tmp_path / f"vectors-{SHA[:8]}.json").read_text(encoding="utf-8"))
        assert raw["sintetico"] is True

    def test_empty_snapshot_is_refused(self, db, tmp_path):
        seed(db, {})
        with pytest.raises(rag_embed_batch.NothingToEmbed):
            rag_embed_batch.embed_snapshot(db, SHA, DeterministicEmbedder(), output_dir=tmp_path)

    def test_unknown_snapshot_is_refused(self, db, tmp_path):
        with pytest.raises(rag_embed_batch.NothingToEmbed, match="snapshot"):
            rag_embed_batch.embed_snapshot(
                db, "f" * 40, DeterministicEmbedder(), output_dir=tmp_path
            )

    def test_batch_size_does_not_change_the_output(self, db, tmp_path):
        """Batching is a memory strategy, never a semantic one."""
        seed(db, {f"9750#{i}": f"{CORTO} {i}" for i in range(5)})
        uno, _ = rag_embed_batch.embed_snapshot(
            db, SHA, DeterministicEmbedder(), output_dir=tmp_path / "b1", batch_size=1
        )
        cinco, _ = rag_embed_batch.embed_snapshot(
            db, SHA, DeterministicEmbedder(), output_dir=tmp_path / "b5", batch_size=5
        )
        assert uno.read_bytes() == cinco.read_bytes()


class TestMainEntryPoint:
    """`main()` through the real argparse entry — the surface the owner types."""

    def _patch_session(self, monkeypatch, db):
        monkeypatch.setattr(rag_embed_batch, "create_engine", lambda url: _NullEngine())
        monkeypatch.setattr(rag_embed_batch, "Session", lambda engine: _SessionStub(db))

    def test_preflight_only_writes_no_artifact(self, db, tmp_path, capsys, monkeypatch):
        """The GPU rehearsal: measure the ceiling without producing a dump.

        A `--limit N` flag would have been the obvious rehearsal knob and is
        deliberately absent: it would emit a PARTIAL artifact, and a partial
        artifact is exactly the shape the loader's exemption check exists to
        reject. Measuring without writing has no such failure mode.
        """
        seed(db, {"9750#1": CORTO, "10593#1": LARGO})
        self._patch_session(monkeypatch, db)

        code = rag_embed_batch.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://stub/stub",
                "--output-dir",
                str(tmp_path),
                "--embedder",
                "deterministic",
                "--preflight-only",
            ]
        )

        assert code == 0
        assert list(tmp_path.glob("vectors-*")) == []
        salida = capsys.readouterr().out
        assert "10593#1" in salida
        assert "a embeber             : 1" in salida

    def test_full_run_exits_0_and_reports_the_artifact(self, db, tmp_path, capsys, monkeypatch):
        seed(db, {"9750#1": CORTO})
        self._patch_session(monkeypatch, db)

        code = rag_embed_batch.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://stub/stub",
                "--output-dir",
                str(tmp_path),
                "--embedder",
                "deterministic",
            ]
        )

        assert code == 0
        assert (tmp_path / f"vectors-{SHA[:8]}.copy").is_file()
        capturado = capsys.readouterr()
        assert "vectores              : 1" in capturado.out
        assert "ADVERTENCIA" in capturado.err  # the synthetic marker reaches a human

    def test_unknown_snapshot_exits_1(self, db, tmp_path, capsys, monkeypatch):
        self._patch_session(monkeypatch, db)

        code = rag_embed_batch.main(
            [
                "--corpus-sha",
                "e" * 40,
                "--database-url",
                "postgresql://stub/stub",
                "--output-dir",
                str(tmp_path),
                "--embedder",
                "deterministic",
            ]
        )

        assert code == 1
        assert "BATCH ABORTED" in capsys.readouterr().err
        assert list(tmp_path.glob("vectors-*")) == []

    def test_strict_ceiling_exits_1_without_writing_a_partial_dump(
        self, db, tmp_path, capsys, monkeypatch
    ):
        seed(db, {"9750#1": CORTO, "10593#1": LARGO})
        self._patch_session(monkeypatch, db)

        code = rag_embed_batch.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://stub/stub",
                "--output-dir",
                str(tmp_path),
                "--embedder",
                "deterministic",
                "--strict-token-ceiling",
            ]
        )

        assert code == 1
        assert "10593#1" in capsys.readouterr().err
        assert list(tmp_path.glob("vectors-*.json")) == []

    def test_missing_database_url_exits_2(self, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        code = rag_embed_batch.main(["--corpus-sha", SHA, "--embedder", "deterministic"])
        assert code == 2
        assert "--database-url" in capsys.readouterr().err


@pytest.mark.pgvector
class TestEndToEndPlumbing:
    """Batch → artifact → load → queryable vector, with no model involved.

    This is the plumbing proof the owner's GPU run does NOT have to discover:
    every step between "rows in `rag_unidad`" and "a cosine-ordered result" is
    exercised for real against PostgreSQL. Only the numbers inside the vectors
    are fake, and they are stamped as such.
    """

    def test_batch_output_loads_and_becomes_searchable(self, pgvector_db, tmp_path):
        from app.domains.conocimiento import repository

        textos = {f"9750#{i}": f"{CORTO} inciso {i}" for i in range(1, 6)}
        seed(pgvector_db, textos)

        copy_path, manifest = rag_embed_batch.embed_snapshot(
            pgvector_db, SHA, DeterministicEmbedder(), output_dir=tmp_path
        )
        actualizadas = rag_load_vectors.load_vectors(
            pgvector_db, copy_path, permitir_sintetico=True
        )

        assert actualizadas == manifest.n_vectors == 5

        consulta = DeterministicEmbedder().encode([textos["9750#3"]])[0]
        hits = repository.vector_search(pgvector_db, SHA, consulta, limite=5)

        assert len(hits) == 5
        # The vector of the exact text queried is its own nearest neighbour.
        assert hits[0].citation_key == "9750#3"
        assert hits[0].valor == pytest.approx(0.0, abs=1e-6)

    def test_synthetic_artifact_is_refused_without_the_flag(self, pgvector_db, tmp_path):
        seed(pgvector_db, {"9750#1": CORTO})
        copy_path, _ = rag_embed_batch.embed_snapshot(
            pgvector_db, SHA, DeterministicEmbedder(), output_dir=tmp_path
        )

        with pytest.raises(rag_load_vectors.PreflightFailure, match="SINTÉTICO"):
            rag_load_vectors.load_vectors(pgvector_db, copy_path)


def test_manifest_written_by_the_batch_is_loadable(db, tmp_path):
    seed(db, {"9750#1": CORTO})
    copy_path, manifest = rag_embed_batch.embed_snapshot(
        db, SHA, DeterministicEmbedder(), output_dir=tmp_path
    )
    assert VectorsManifest.load(copy_path.with_suffix(".json")) == manifest


class TestE5Embedder:
    """RJDA-005 / RJDB-005: the CLI advertised `e5-large` and it did not exist.

    `rag_eval.py` listed it in `--embedder`'s `choices`, so argparse accepted it
    and `get_embedder` then raised `ValueError: unknown embedder 'e5-large'` —
    an advertised option that crashes. Implementing it is not just wiring: E5 is
    ASYMMETRIC, and the prefixes are the part that cannot be got wrong quietly.
    """

    class _FakeST:
        """A stand-in for `SentenceTransformer` that records what it was asked to encode."""

        def __init__(self, model_name_or_path, device=None, revision=None):
            self.model_name_or_path = model_name_or_path
            self.device = device
            self.revision = revision
            self.max_seq_length = 512
            self.vistos: list[str] = []
            self.kwargs: list[dict] = []
            self.tokenizer = self._FakeTokenizer()

        class _FakeTokenizer:
            def __init__(self):
                self.vistos: list[str] = []

            def encode(self, texto, add_special_tokens=True):
                self.vistos.append(texto)
                return list(range(len(texto.split())))

        def get_sentence_embedding_dimension(self):
            return EMBEDDING_DIMENSIONS

        def encode(self, textos, **kwargs):
            self.vistos.extend(textos)
            self.kwargs.append(kwargs)
            return [[0.0] * (EMBEDDING_DIMENSIONS - 1) + [1.0] for _ in textos]

    @pytest.fixture
    def st(self, monkeypatch):
        """Inject the fake as the `sentence_transformers` module, so the LAZY
        import inside `__init__` picks it up without the 2.2 GB download."""
        import sys
        import types

        modulo = types.ModuleType("sentence_transformers")
        creados: list = []

        def constructor(*args, **kwargs):
            instancia = TestE5Embedder._FakeST(*args, **kwargs)
            creados.append(instancia)
            return instancia

        modulo.SentenceTransformer = constructor
        monkeypatch.setitem(sys.modules, "sentence_transformers", modulo)
        return creados

    def test_the_query_role_applies_the_query_prefix(self, st):
        from app.domains.conocimiento.embedding import E5Embedder

        embedder = E5Embedder(rol="query")
        embedder.encode(["¿cuál es el quórum de la asamblea?"])
        assert st[0].vistos == ["query: ¿cuál es el quórum de la asamblea?"]

    def test_the_passage_role_applies_the_passage_prefix(self, st):
        from app.domains.conocimiento.embedding import E5Embedder

        embedder = E5Embedder(rol="passage")
        embedder.encode(["Artículo 14.- El quórum de la asamblea…"])
        assert st[0].vistos == ["passage: Artículo 14.- El quórum de la asamblea…"]

    def test_the_role_is_required_and_never_guessed(self, st):
        """No default, because the wrong prefix raises nothing, warns nothing and
        changes nothing about the shape — it just ranks worse. Every gate this
        codebase has (dims, model id, loader identity) passes either way."""
        from app.domains.conocimiento.embedding import E5Embedder

        with pytest.raises(TypeError):
            E5Embedder()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="rol"):
            E5Embedder(rol="documento")

    def test_the_token_count_includes_the_prefix(self, st):
        """A unit measured without its prefix can pass the pre-flight and still
        be truncated by the model — the silent truncation the whole exemption
        machinery exists to prevent."""
        from app.domains.conocimiento.embedding import E5Embedder

        embedder = E5Embedder(rol="passage")
        embedder.count_tokens("uno dos tres")
        assert st[0].tokenizer.vistos == ["passage: uno dos tres"]

    def test_it_reports_its_own_identity_dimensions_and_ceiling(self, st):
        from app.domains.conocimiento.embedding import (
            E5_MODEL_ID,
            E5_TOKEN_CEILING,
            E5Embedder,
        )

        embedder = E5Embedder(rol="query")
        # The HF id, which is what the provenance gate compares — and NOT
        # something shared with BGE-M3, whose dimension count is identical.
        assert embedder.model_id == E5_MODEL_ID
        assert embedder.model_id != DEFAULT_MODEL_ID
        assert embedder.dims == EMBEDDING_DIMENSIONS
        assert embedder.sintetico is False
        # A QUARTER of BGE-M3's window: switching models changes which units are
        # over the ceiling, so the ceiling travels with the embedder.
        assert embedder.token_ceiling == E5_TOKEN_CEILING == 512
        assert embedder.token_ceiling < TOKEN_CEILING

    def test_vectors_are_normalized_because_cosine_requires_it(self, st):
        from app.domains.conocimiento.embedding import E5Embedder

        E5Embedder(rol="passage").encode(["algo"])
        assert st[0].kwargs[0]["normalize_embeddings"] is True

    def test_get_embedder_resolves_it_with_the_role_threaded_through(self, st):
        from app.domains.conocimiento.embedding import E5_MODEL_ID, get_embedder

        embedder = get_embedder("e5-large", rol="passage")
        assert embedder.prefijo == "passage: "
        # The default `model_id` is BGE-M3's; letting it through would stamp
        # `BAAI/bge-m3` onto e5 vectors and defeat the only gate that can tell
        # these two 1024-dim models apart.
        assert embedder.model_id == E5_MODEL_ID

    def test_get_embedder_requires_a_role_from_every_caller(self):
        from app.domains.conocimiento.embedding import get_embedder

        with pytest.raises(TypeError):
            get_embedder("deterministic")  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="unknown rol"):
            get_embedder("deterministic", rol="documento")

    def test_the_symmetric_embedders_accept_the_role_and_ignore_it(self):
        """`rol` is meaningless for BGE-M3 and the fake, and still required: the
        one call site that forgets is the one that builds a worse index."""
        from app.domains.conocimiento.embedding import get_embedder

        uno = get_embedder("deterministic", rol="query")
        otro = get_embedder("deterministic", rol="passage")
        assert uno.encode(["texto"]) == otro.encode(["texto"])

    def test_an_unknown_name_still_names_all_three_options(self):
        from app.domains.conocimiento.embedding import get_embedder

        with pytest.raises(ValueError, match="e5-large"):
            get_embedder("no-existe", rol="query")
