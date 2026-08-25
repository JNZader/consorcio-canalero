"""`scripts/rag_eval.py` — the thin entry point, exercised for real (task 4.12).

`main()` is where the pieces meet, so it gets its own tests rather than being
assumed correct because its parts are: the slice-2 review found exactly this hole
(`rag_ingest.main` was invoked by no test at all, ledger RAG2-006).

The session is threaded in rather than opened by the CLI so these run against the
real test database inside the fixture's transaction — real SQL, real gates, no
committed rows.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from app.domains.conocimiento.embedding import (
    DETERMINISTIC_MODEL_ID,
    BGEM3Embedder,
    E5Embedder,
)
from app.domains.conocimiento.eval.harness import cargar_gold_set as cargar_gold_set_real
from app.domains.conocimiento.eval.report import ETIQUETA_SMOKE
from app.domains.conocimiento.eval.slm_bench import PIN_REFERENCIA
from app.domains.conocimiento.recuperacion.reranker import RerankerNoDisponible
from app.domains.conocimiento.repository import registrar_procedencia
from scripts import rag_eval

from .test_rag_eval_harness import PREGUNTAS, SHA, gold_item, gold_set, seed

#: The bench tests seed their OWN two-document snapshot, so they use their own
#: snapshot id: sharing `SHA` would collide with `seed`'s corpus row.
SHA_BENCH = "b" * 40

MOMENTO = "2026-08-10T16:30:00+00:00"

#: A question whose lexemes appear nowhere in the seeded mini-snapshot, so the
#: lexical leg genuinely comes back empty. Since the FTS leg ORs its lexemes
#: (`repository.FTS_OPERADOR`), an empty leg is now a real vocabulary gap rather
#: than an artefact of the query operator — which is what makes it the right
#: fixture for the degraded-leg warning.
SIN_VOCABULARIO = "cuántos metros de ancho tiene la zona de camino"


class _SesionPrestada:
    """Hands `main()` the fixture's session and refuses to close it."""

    def __init__(self, db):
        self._db = db

    def __call__(self, _engine):
        return self

    def __enter__(self):
        return self._db

    def __exit__(self, *_):
        return False


class _NullEngine:
    def dispose(self) -> None:
        return None


class _EspiaEmbedder:
    """Records every attempt to build an embedder, and refuses to build one.

    The point is the ORDER, not the object: `--embedder bge-m3` imports torch and
    downloads 2.2 GB, so every refusal that can be decided without it MUST be
    decided before it. That property used to depend on the test machine simply
    not having torch installed, which is an environment coupling and not a test —
    it would pass silently for the wrong reason on any box that does.
    """

    def __init__(self) -> None:
        self.llamadas: list[str] = []

    def __call__(self, nombre, *, device, model_id):
        self.llamadas.append(nombre)
        raise AssertionError(
            f"the run built the {nombre!r} embedder before refusing; a cheap "
            "refusal must never cost a model load"
        )


@pytest.fixture
def espia_embedder(monkeypatch):
    espia = _EspiaEmbedder()
    monkeypatch.setattr(rag_eval, "_embedder", espia)
    return espia


@pytest.fixture
def cli(db, monkeypatch):
    seed(db)
    monkeypatch.setattr(rag_eval, "create_engine", lambda url: _NullEngine())
    monkeypatch.setattr(rag_eval, "Session", _SesionPrestada(db))
    # The seeded snapshot is `SHA`, so the gold set must pin `SHA` too — which is
    # exactly the reconciliation `verificar_corpus_sha` now enforces. Loading the
    # real 52-item set here would (correctly) be refused: it is pinned to the
    # real corpus revision, and this fixture is five hand-written units.
    monkeypatch.setattr(rag_eval, "cargar_gold_set", lambda *a, **k: PREGUNTAS)
    monkeypatch.delenv("RAG_GOLD_PRIVADO_PATH", raising=False)
    return db


def marcar(db, *, sintetico: bool, modelo: str = "BAAI/bge-m3") -> None:
    registrar_procedencia(
        db,
        SHA,
        modelo=modelo,
        revision_hf=None if sintetico else "a" * 40,
        sintetico=sintetico,
        artifact_sha256="b" * 64,
    )
    db.flush()


class TestUsage:
    def test_missing_database_url_exits_2(self, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert rag_eval.main(["--corpus-sha", SHA]) == 2
        assert "--database-url" in capsys.readouterr().err

    def test_an_unknown_snapshot_exits_1_before_running_anything(
        self, cli, monkeypatch, capsys, espia_embedder
    ):
        # The gold set pins the snapshot being asked for, so the identity check
        # passes and the run reaches — and stops at — the missing-snapshot check.
        monkeypatch.setattr(
            rag_eval,
            "cargar_gold_set",
            lambda *a, **k: gold_set(*PREGUNTAS.items, corpus_sha="f" * 40),
        )
        code = rag_eval.main(
            ["--corpus-sha", "f" * 40, "--database-url", "postgresql://unused/unused"]
        )
        assert code == 1
        assert "is not in rag_corpus" in capsys.readouterr().err
        assert espia_embedder.llamadas == []


class TestIdentidadDelCorpus:
    """RAG4-003: the gold set and the snapshot must be the same corpus revision.

    The gold set's `citas_esperadas` are citation keys of ONE revision. Scored
    against another, a key that does not exist there is indistinguishable from a
    retrieval miss — so every metric falls and the report blames the retriever.
    The error is fail-safe in direction (a spurious NO-GO, never a spurious GO)
    and that is precisely why it needed a check: an unexplainable NO-GO costs a
    re-run of the whole GPU batch, and the cause is one string comparison away.
    """

    def test_a_gold_set_from_another_corpus_revision_is_refused(
        self, cli, monkeypatch, tmp_path, capsys, espia_embedder
    ):
        monkeypatch.setattr(
            rag_eval,
            "cargar_gold_set",
            lambda *a, **k: gold_set(*PREGUNTAS.items, corpus_sha="a" * 40),
        )
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--destino",
                str(tmp_path / "nunca"),
            ]
        )
        assert code == rag_eval.SALIDA_IDENTIDAD
        error = capsys.readouterr().err
        # BOTH shas, because "they differ" without saying how is a message that
        # sends the reader back to the shell to work out which one is wrong.
        assert "a" * 40 in error
        assert SHA in error
        # Refused before scoring, before the report directory, before the model.
        assert not (tmp_path / "nunca").exists()
        assert espia_embedder.llamadas == []

    def test_a_matching_gold_set_proceeds(self, cli, tmp_path):
        marcar(cli, sintetico=False)
        assert (
            rag_eval.main(
                [
                    "--corpus-sha",
                    SHA,
                    "--database-url",
                    "postgresql://unused/unused",
                    "--modo",
                    "fts",
                    "--destino",
                    str(tmp_path),
                    "--generado-en",
                    MOMENTO,
                ]
            )
            == 0
        )
        assert (tmp_path / "retrieval-eval-dddddddd-2026-08-10.md").is_file()

    def test_a_private_file_pinned_to_another_revision_is_refused(
        self, cli, monkeypatch, tmp_path, capsys, espia_embedder
    ):
        """The owner-side file is resolved from an environment variable that
        points OUTSIDE this repository, so a stale copy left over from a previous
        corpus revision is an ordinary slip — and its only symptom would be 26
        questions quietly scored against citations that moved."""
        privado = tmp_path / "privado.yaml"
        privado.write_text(
            "version: 1\npara: gold_set.yaml\ncorpus_sha: " + "e" * 40 + "\npreguntas: {}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(privado))
        monkeypatch.setattr(rag_eval, "cargar_gold_set", cargar_gold_set_real)

        code = rag_eval.main(["--corpus-sha", SHA, "--database-url", "postgresql://unused/unused"])
        assert code == rag_eval.SALIDA_IDENTIDAD
        assert "e" * 40 in capsys.readouterr().err
        assert espia_embedder.llamadas == []

    def test_a_private_file_belonging_to_another_gold_set_is_refused(
        self, cli, monkeypatch, tmp_path, capsys, espia_embedder
    ):
        privado = tmp_path / "privado.yaml"
        privado.write_text(
            "version: 1\npara: otro-gold-set.yaml\npreguntas: {}\n", encoding="utf-8"
        )
        monkeypatch.setenv("RAG_GOLD_PRIVADO_PATH", str(privado))
        monkeypatch.setattr(rag_eval, "cargar_gold_set", cargar_gold_set_real)

        code = rag_eval.main(["--corpus-sha", SHA, "--database-url", "postgresql://unused/unused"])
        assert code == rag_eval.SALIDA_IDENTIDAD
        assert "otro-gold-set.yaml" in capsys.readouterr().err
        assert espia_embedder.llamadas == []


class TestRun:
    def test_an_fts_only_run_writes_both_artifacts_and_exits_0(self, cli, tmp_path, capsys):
        marcar(cli, sintetico=False)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 0
        salida = capsys.readouterr().out
        assert "NO EVALUABLE" in salida  # the fixture gold set is 3 items
        md = tmp_path / "retrieval-eval-dddddddd-2026-08-10.md"
        js = tmp_path / "retrieval-eval-dddddddd-2026-08-10.results.json"
        assert md.is_file() and js.is_file()
        assert json.loads(js.read_text(encoding="utf-8"))["corpus_sha"] == SHA

    def test_a_synthetic_snapshot_exits_1_and_writes_nothing(self, cli, tmp_path, capsys):
        marcar(cli, sintetico=True, modelo=DETERMINISTIC_MODEL_ID)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 1
        assert "SYNTHETIC" in capsys.readouterr().err
        assert list(tmp_path.glob("*")) == []

    def test_the_synthetic_refusal_costs_no_model_load(self, cli, tmp_path, espia_embedder):
        """4.12's ordering property, asserted instead of inherited from the box.

        No `--modo`, so the run asks for the full three-mode ablation and WOULD
        need an embedder. The refusal has to come first: a synthetic snapshot
        used to spend two minutes and 2.2 GB loading BGE-M3 before the report
        refused it, and the regression test for that was "this machine has no
        torch" — which passes for the wrong reason on any machine that does.
        """
        marcar(cli, sintetico=True, modelo=DETERMINISTIC_MODEL_ID)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 1
        assert espia_embedder.llamadas == []
        assert list(tmp_path.glob("*")) == []

    def test_the_smoke_flag_writes_a_labelled_artifact_instead(self, cli, tmp_path):
        marcar(cli, sintetico=True, modelo=DETERMINISTIC_MODEL_ID)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
                "--allow-synthetic",
            ]
        )
        assert code == 0
        escritos = sorted(p.name for p in tmp_path.glob("*.md"))
        assert escritos == ["retrieval-eval-SINTETICO-dddddddd-2026-08-10.md"]
        assert "NOT AN EVAL" in (tmp_path / escritos[0]).read_text(encoding="utf-8")

    def test_the_same_timestamp_produces_a_byte_identical_report(self, cli, tmp_path):
        marcar(cli, sintetico=False)
        for destino in ("a", "b"):
            assert (
                rag_eval.main(
                    [
                        "--corpus-sha",
                        SHA,
                        "--database-url",
                        "postgresql://unused/unused",
                        "--modo",
                        "fts",
                        "--destino",
                        str(tmp_path / destino),
                        "--generado-en",
                        MOMENTO,
                    ]
                )
                == 0
            )
        nombre = "retrieval-eval-dddddddd-2026-08-10.md"
        assert (tmp_path / "a" / nombre).read_text(encoding="utf-8") == (
            tmp_path / "b" / nombre
        ).read_text(encoding="utf-8")

    def test_the_degraded_leg_warning_reaches_the_operator_on_stdout(
        self, cli, monkeypatch, tmp_path, capsys
    ):
        """The eval's most misleading outcome must be visible without opening
        the report: a mode whose lexical leg matched nothing at all.

        The fixture question is a vocabulary gap, not a query-operator artefact —
        since RAG4-001 was fixed the lexical leg ORs its lexemes, so an empty leg
        now means the question and the corpus share no word at all. That is the
        residue the fix cannot remove, and it is still worth shouting about.
        """
        marcar(cli, sintetico=False)
        conjunto = gold_set(gold_item("g-hueco", SIN_VOCABULARIO, "answerable"))
        monkeypatch.setattr(rag_eval, "cargar_gold_set", lambda *a, **k: conjunto)

        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 0
        assert "LEG FTS DEGRADADA" in capsys.readouterr().out


def test_the_default_report_destination_is_docs_rag_so_it_survives_archive():
    """design.md D6: under `docs/`, not `openspec/changes/`, so `/sdd-archive`
    does not take the deliverable with it."""
    assert rag_eval.DESTINO_POR_DEFECTO.name == "rag"
    assert rag_eval.DESTINO_POR_DEFECTO.parent.name == "docs"


def test_the_cli_reads_the_clock_only_at_the_edge():
    """One clock read, in `main()`, threaded downstream as a value."""
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(rag_eval))
    lecturas = [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Attribute)
        and nodo.func.attr in {"now", "utcnow", "today"}
    ]
    assert len(lecturas) == 1
    assert isinstance(dt.datetime.now, object)


class TestDependenciaFaltante:
    """RJDA-002: the DEFAULT venv has no torch, and that is by design.

    `requirements-rag.txt` pulls the whole CUDA stack and is deliberately kept
    out of the app image (design.md D8), so `venv/` cannot build a real embedder
    — and the default ablation includes `vector` and `hybrid`, both of which
    need one on the QUERY side. `make rag-eval` therefore hit this path on the
    most ordinary invocation there is, and answered with a raw ImportError
    traceback: an environment problem presented as a crash, with the one-line
    fix buried inside the exception it did not catch.
    `scripts/rag_query_latency.py` had handled it correctly since slice 3.
    """

    #: The message `BGEM3Embedder.__init__` raises, verbatim in the part that
    #: matters. Reproduced here rather than imported so that deleting the
    #: instructions from the embedder breaks this test.
    FALTA_TORCH = (
        "BGE-M3 needs the ingestion extra. Install it into a SEPARATE "
        "virtualenv (it pulls the whole CUDA stack, ~6 GB) and never into "
        "the app image:\n"
        "    python -m venv venv-rag\n"
        "    venv-rag/bin/pip install -r requirements-rag.txt"
    )

    def _sin_torch(self, monkeypatch):
        def explota(nombre, *, device, model_id):
            raise RuntimeError(self.FALTA_TORCH)

        monkeypatch.setattr(rag_eval, "_embedder", explota)

    def test_a_missing_embedding_dependency_exits_2_with_instructions(
        self, cli, monkeypatch, tmp_path, capsys
    ):
        marcar(cli, sintetico=False)
        self._sin_torch(monkeypatch)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--destino",
                str(tmp_path / "nunca"),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == rag_eval.SALIDA_SIN_DEPENDENCIA == 2
        error = capsys.readouterr().err
        # The fix, not just the symptom: the file to install and the venv to
        # install it into.
        assert "requirements-rag.txt" in error
        assert "venv-rag" in error
        # And the escape hatch that needs no torch at all.
        assert "--modo fts" in error
        # Nothing was written: a refusal must not leave a half-built docs/rag entry.
        assert not (tmp_path / "nunca").exists()

    def test_the_real_embedders_raise_what_this_class_only_reproduces(self, monkeypatch):
        """RJDA-104: close the coupling between the fake message and the real one.

        Every other test here monkeypatches `rag_eval._embedder` and hands the
        CLI a `RuntimeError` carrying `FALTA_TORCH`. That proves the CLI's half
        and nothing about the raise site: they would all keep passing if
        `BGEM3Embedder` stopped wrapping the `ImportError`, stopped naming the
        file to install, or changed the class it raises — and the regression is
        invisible, because the happy path does not touch this branch and the
        environment that exercises it is precisely the one nobody runs tests in.

        So this imports the REAL module and makes the dependency genuinely
        unimportable: `None` in `sys.modules` is what CPython turns into an
        `ImportError` at the `import` statement. It runs identically on a box
        that has torch and on one that does not, and it never downloads 2.2 GB.
        """
        monkeypatch.setitem(sys.modules, "torch", None)
        with pytest.raises(RuntimeError) as bge:
            BGEM3Embedder()
        # Verbatim: this is what makes the class attribute above a check rather
        # than a copy that drifted.
        assert str(bge.value) == self.FALTA_TORCH
        assert "requirements-rag.txt" in str(bge.value)
        assert isinstance(bge.value.__cause__, ImportError)

        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        with pytest.raises(RuntimeError) as e5:
            E5Embedder(rol="query")
        assert "requirements-rag.txt" in str(e5.value)
        assert "venv-rag" in str(e5.value)
        assert isinstance(e5.value.__cause__, ImportError)

    def test_the_fts_only_ablation_never_needs_an_embedder(self, cli, monkeypatch, tmp_path):
        """The escape hatch the error message offers has to actually work."""
        marcar(cli, sintetico=False)
        self._sin_torch(monkeypatch)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 0
        assert (tmp_path / "retrieval-eval-dddddddd-2026-08-10.md").is_file()


class TestLatenciaEnLaCLI:
    """RJDA-006 at the entry point: the file is read at the edge, early."""

    def test_the_measurement_reaches_the_report(self, cli, tmp_path):
        marcar(cli, sintetico=False)
        medicion = tmp_path / "latencia.json"
        medicion.write_text(
            json.dumps(
                {
                    "etiqueta": "ESTIMATE",
                    "modelo": "BAAI/bge-m3",
                    "sintetico": False,
                    "device": "cpu",
                    "cpu_count": 2,
                    "torch_threads": 2,
                    "preguntas": 3,
                    "calentamientos": 3,
                    "repeticiones": 3,
                    "n": 9,
                    "p50_ms": 90.0,
                    "p95_ms": 140.0,
                    "min_ms": 80.0,
                    "max_ms": 150.0,
                    "media_ms": 95.0,
                }
            ),
            encoding="utf-8",
        )
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path / "salida"),
                "--generado-en",
                MOMENTO,
                "--latencia",
                str(medicion),
            ]
        )
        assert code == 0
        markdown = (tmp_path / "salida" / "retrieval-eval-dddddddd-2026-08-10.md").read_text(
            encoding="utf-8"
        )
        assert "etiqueta: ESTIMATE" in markdown
        assert "90.0 ms" in markdown
        datos = json.loads(
            (tmp_path / "salida" / "retrieval-eval-dddddddd-2026-08-10.results.json").read_text(
                encoding="utf-8"
            )
        )
        assert datos["latencia"]["etiqueta"] == "ESTIMATE"

    def test_an_unreadable_latency_file_exits_2_before_the_ablation_runs(
        self, cli, tmp_path, capsys, espia_embedder
    ):
        """Read at the edge on purpose: a typo in the path must not be found out
        after a 52-question ablation has already run."""
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--destino",
                str(tmp_path / "nunca"),
                "--latencia",
                str(tmp_path / "no-existe.json"),
            ]
        )
        assert code == 2
        assert "rag_query_latency.py" in capsys.readouterr().err
        assert not (tmp_path / "nunca").exists()
        assert espia_embedder.llamadas == []

    @pytest.mark.parametrize(
        ("payload", "esperado"),
        [
            pytest.param([1, 2, 3], "se esperaba un objeto", id="una-lista"),
            pytest.param("ok", "se esperaba un objeto", id="un-string"),
            pytest.param({"etiqueta": "LOCAL"}, "falta `p50_ms`", id="sin-el-criterio"),
            pytest.param(
                {"p50_ms": "lento", "p95_ms": 140.0},
                "`p50_ms` es 'lento', se esperaba un número",
                id="un-string-donde-va-un-float",
            ),
            pytest.param(
                {"p50_ms": True, "p95_ms": 140.0},
                "`p50_ms` es True, se esperaba un número",
                id="un-bool-que-formatea-como-1.0",
            ),
        ],
    )
    def test_a_malformed_latency_file_is_refused_before_the_ablation_runs(
        self, cli, tmp_path, capsys, espia_embedder, payload, esperado
    ):
        """RJDB-102 ≡ RJDA-105: parsing was never validation.

        Reading the file early bought nothing while its SHAPE was still checked
        at render time. Any JSON at all parsed — a list, a bare string, a dict
        missing the two numbers that ARE the criterion — and the run died in the
        report's last block, after the whole ablation had been paid for:
        `f"{'lento':.1f}"` raises. The `True` case is the worse one, because it
        does not raise at all: it renders `1.0` and publishes a latency figure
        nobody measured.

        Each case must exit 2, name the offending file, and cost no model load.
        """
        medicion = tmp_path / "latencia.json"
        medicion.write_text(json.dumps(payload), encoding="utf-8")
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--destino",
                str(tmp_path / "nunca"),
                "--latencia",
                str(medicion),
            ]
        )
        assert code == 2
        error = capsys.readouterr().err
        assert str(medicion) in error, "the refusal has to name the file"
        assert esperado in error
        assert "rag_query_latency.py" in error
        assert not (tmp_path / "nunca").exists()
        assert espia_embedder.llamadas == []


class TestArmGateado:
    """Task 9.1b — `--modo bm25_ce` is reachable from the CLI, with its refusals.

    The arm the amended serving gate names could not be requested at all before
    this: `--modo` only accepted the three ablation modes, so the one
    configuration the change must clear was the one the command could not run.
    """

    def test_bm25_ce_es_un_modo_aceptado(self):
        parser = rag_eval.build_parser()
        args = parser.parse_args(["--corpus-sha", SHA, "--modo", "bm25_ce"])
        assert args.modo == ["bm25_ce"]

    def test_el_default_sigue_siendo_la_ablacion_de_tres(self):
        """Adding the arm must not silently make every run pay for a GPU."""
        parser = rag_eval.build_parser()
        args = parser.parse_args(["--corpus-sha", SHA])
        assert args.modo is None

    def test_sin_cross_encoder_sale_2_y_no_escribe_nada(self, cli, tmp_path, monkeypatch, capsys):
        """No CPU fallback, and no half-written `docs/rag/` entry.

        The measured CPU cost at depth 50 is ~99 s per query, so falling back is
        not a degraded mode — it is an outage that answers. The CLI says so and
        exits in the usage bucket, because nothing was queried or written.
        """
        marcar(cli, sintetico=False)

        def sin_gpu(nombre, *, device):
            raise RerankerNoDisponible("no CUDA device is available")

        monkeypatch.setattr(rag_eval, "_reranker", sin_gpu)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "bm25_ce",
                "--destino",
                str(tmp_path / "nunca"),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 2
        error = capsys.readouterr().err
        assert "no CUDA device" in error
        assert "--reranker deterministic" in error
        assert not (tmp_path / "nunca").exists()

    def test_un_stand_in_sin_allow_synthetic_sale_1(self, cli, tmp_path, capsys):
        """The U2 publish gate, reached through the CLI's new path.

        `bm25_ce`'s order is the cross-encoder's alone, so a stand-in does not
        degrade the ranking — it replaces it. Publishing that as a margin is the
        exact failure `_gate_sintetico` exists to refuse.
        """
        marcar(cli, sintetico=False)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "bm25_ce",
                "--reranker",
                "deterministic",
                "--destino",
                str(tmp_path / "nunca"),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 1
        assert "SYNTHETIC" in capsys.readouterr().err
        assert not (tmp_path / "nunca").exists()

    def test_el_smoke_publica_el_bloque_de_margen_sin_veredicto(self, cli, tmp_path, capsys):
        marcar(cli, sintetico=False)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "bm25_ce",
                "--reranker",
                "deterministic",
                "--allow-synthetic",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 0
        md = tmp_path / "retrieval-eval-SINTETICO-dddddddd-2026-08-10.md"
        assert md.is_file()
        texto = md.read_text(encoding="utf-8")
        assert "Margen contra el baseline FTS-only" in texto
        assert "0.138" in texto
        assert ETIQUETA_SMOKE in texto


class TestAnswerSetEnLaCLI:
    """Tasks 9.1-9.4 reaching the artifact a person actually reads."""

    def test_sin_answer_set_el_reporte_dice_por_que(self, cli, tmp_path):
        """An absent section reads as a section that was fine. So it is present."""
        marcar(cli, sintetico=False)
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 0
        md = (tmp_path / "retrieval-eval-dddddddd-2026-08-10.md").read_text(encoding="utf-8")
        assert "Métricas por respuesta" in md
        assert "worker con GPU" in md
        js = json.loads(
            (tmp_path / "retrieval-eval-dddddddd-2026-08-10.results.json").read_text(
                encoding="utf-8"
            )
        )
        assert js["respuestas"]["evaluado"] is False

    def test_un_answer_set_sin_ratificar_degrada_pero_no_mata_la_corrida(self, cli, tmp_path):
        """The ablation is a complete measurement on its own.

        Losing it because the answer set is unratified would make the report's
        most expensive half hostage to its cheapest.
        """
        marcar(cli, sintetico=False)
        conjunto = tmp_path / "answer_set.yaml"
        conjunto.write_text(
            "version: 1\nestado: 'BORRADOR'\nprompt_version: 1\n"
            "provider_model_pin: x\ncorpus_sha: y\nrespuestas: []\n",
            encoding="utf-8",
        )
        code = rag_eval.main(
            [
                "--corpus-sha",
                SHA,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                "fts",
                "--answer-set",
                str(conjunto),
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert code == 0
        md = (tmp_path / "retrieval-eval-dddddddd-2026-08-10.md").read_text(encoding="utf-8")
        assert "not-evaluable" in md
        assert "BORRADOR" in md

    def test_el_pin_del_prompt_sale_del_artefacto_de_plantillas(self):
        """Not a constant somebody must remember to bump.

        `plantillas_generacion.yaml` carries `version` and its own docstring says
        that editing a framing there IS editing the prompt. Reading it is what
        makes the 9.3 pin able to notice.
        """
        from app.domains.conocimiento.generacion import PLANTILLAS, cargar_plantillas

        assert PLANTILLAS.version == cargar_plantillas().version
        assert isinstance(PLANTILLAS.version, int)


class TestElBenchCorreDentroDeLaSesion:
    """W3 — the bench's universe is re-derived, so it needs the open session.

    `_bench_slm` used to take only `args` and ran AFTER the session closed,
    which is what made the bench the one path around task 9.4: same recorded
    payloads, same `corpus_sha`, no database read, so a reclassification that
    invalidates the single-arm figures left the bench publishing a delta between
    two arms both scored against a universe that no longer exists.
    """

    def sembrar(self, db, *, clasificacion: str) -> None:
        db.execute(
            text(
                "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
                "articulos_declarados, activo) VALUES (:sha, 'u', '2', 2, true)"
            ),
            {"sha": SHA_BENCH},
        )
        db.execute(
            text(
                "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                "(:sha, 'ley-9750', 'ley-provincial', false, 'provincial', 'vigente', "
                "'publico')"
            ),
            {"sha": SHA_BENCH},
        )
        db.execute(
            text(
                "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                "(:sha, 'ley-8548', 'ley-provincial', false, 'provincial', 'vigente', :clas)"
            ),
            {"sha": SHA_BENCH, "clas": clasificacion},
        )
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                "texto, texto_indexado, source_file, source_offset) VALUES "
                "(:sha, :key, :doc, 'articulo', 't', 't', 'f.md', 0)"
            ),
            [
                {"sha": SHA_BENCH, "key": "9750#1", "doc": "ley-9750"},
                {"sha": SHA_BENCH, "key": "8548#3", "doc": "ley-8548"},
            ],
        )
        db.flush()

    def escribir_bench(self, tmp_path):
        def brazo(pin):
            return {
                "estado": "RATIFICADO 2026-08-24 — prueba",
                "prompt_version": 1,
                "provider_model_pin": pin,
                "corpus_sha": SHA_BENCH,
                "expected_clasificacion_sha256": "a" * 64,
                "generador_sintetico": False,
                "tokens_por_segundo": 40.0,
                "respuestas": [
                    {
                        "id": "R-1",
                        "pregunta": "quién administra el canal",
                        "debe_abstenerse": False,
                        "estado_servido": "respuesta",
                        "claves_recuperadas": ["9750#1", "8548#3"],
                        # Graded under the NARROWER allowlist.
                        "claves_payload": ["9750#1"],
                        "texto": "El consorcio administra el canal [9750#1].",
                        "afirmaciones": [
                            {"id": "a", "texto": "…", "clave": "9750#1", "grado": "sostenida"}
                        ],
                        "regrado": {},
                    }
                ],
            }

        ruta = tmp_path / "slm_bench.yaml"
        ruta.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "estado": "RATIFICADO 2026-08-24 — prueba",
                    "prompt_version": 1,
                    "corpus_sha": SHA_BENCH,
                    "referencia": brazo(PIN_REFERENCIA),
                    "candidato": brazo("Qwen3-8B-Instruct-Q5"),
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        return ruta

    def test_una_reclasificacion_viva_degrada_el_bloque_a_su_motivo(self, db, tmp_path):
        """It degrades into a STATED reason, never into a crash and never into a table."""
        self.sembrar(db, clasificacion="publico")
        args = rag_eval.build_parser().parse_args(
            ["--corpus-sha", SHA_BENCH, "--slm-bench", str(self.escribir_bench(tmp_path))]
        )
        bench, motivo = rag_eval._bench_slm(db, args)
        assert bench is None
        assert motivo is not None
        assert "8548#3" in motivo

    def test_un_bench_al_dia_se_carga(self, db, tmp_path):
        self.sembrar(db, clasificacion="privado")
        args = rag_eval.build_parser().parse_args(
            ["--corpus-sha", SHA_BENCH, "--slm-bench", str(self.escribir_bench(tmp_path))]
        )
        bench, motivo = rag_eval._bench_slm(db, args)
        assert motivo is None
        assert bench is not None and bench.referencia.pin == PIN_REFERENCIA

    def test_el_bench_se_arma_dentro_del_bloque_de_sesion(self):
        """A structural check, because getting this wrong is silent again.

        `_bench_slm` outside the `with` block would either take no session (the
        defect this closes) or take a closed one. The call has to be indented
        INSIDE the block that opens it.
        """
        fuente = Path(rag_eval.__file__).read_text(encoding="utf-8")
        linea = next(texto for texto in fuente.splitlines() if "= _bench_slm(db, args)" in texto)
        assert linea.startswith("        "), linea
