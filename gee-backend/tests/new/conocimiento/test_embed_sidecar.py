"""U3: the `conocimiento-embed` sidecar, its adapter, and the identity guard.

Three things are under test here and they fail in three different ways, so they
are kept apart:

* **the image** — a serving container whose torch version floats is a serving
  container whose vectors can change on rebuild (`design.md:122-128`). That is
  asserted against the lock file itself, because it is the only artifact that
  can be checked without a 2.2 GB download;
* **readiness as a state** — `/ready` is true only after the weights load AND one
  warm-up embed completes; until then the answer is `embedder_no_listo` and never
  a blocked request thread (`design.md:117-120`);
* **the revision half of the provenance guard** — today `verificar_embedder`
  compares the model id and stops, while `ProcedenciaEmbeddings` has carried
  `revision_hf` all along. Two BGE-M3 revisions report the same `model_id` and
  produce different vectors; the symptom is a confident, meaningless ranking with
  full provenance attached, which is the exact failure the guard exists for
  (`design.md:89-105`).

The model is never loaded here. What a test can honestly exercise about "the real
embedder" is the identity plumbing and the refusals, and that is all these
exercise — retrieval quality is the eval harness's job on the GPU box.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Sequence

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.domains.conocimiento import service
from app.domains.conocimiento.embed_sidecar import (
    CAUSA_INALCANZABLE,
    CAUSA_NO_LISTO,
    CAUSA_RESPUESTA_INVALIDA,
    SidecarEmbedder,
    SidecarNoDisponible,
    conectar_sidecar,
)
from app.domains.conocimiento.embedding import (
    DEFAULT_MODEL_ID,
    DETERMINISTIC_MODEL_ID,
    EMBEDDING_DIMENSIONS,
    TOKEN_CEILING,
    DeterministicEmbedder,
    RevisionNoResoluble,
    canonicalizar_revision,
    resolver_revision,
)
from app.domains.conocimiento.repository import registrar_procedencia

SHA = "e" * 40

#: Two DIFFERENT resolved commits of the same model. The whole point of the
#: revision half of the guard is that these two are indistinguishable at
#: `model_id` and produce different vectors.
REVISION_A = "5617a9f61b028005a4858fdac845db406aefb181"
REVISION_B = "babcf60cae0554b2077b71b4dd57e88b5cbb3d20"

RAIZ_DEL_REPO = Path(__file__).resolve().parents[4]
DIRECTORIO_SIDECAR = RAIZ_DEL_REPO / "docker" / "embed"


# --------------------------------------------------------------------------- #
# 3.1 — the image's dependency closure
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def lock_del_sidecar() -> str:
    ruta = DIRECTORIO_SIDECAR / "requirements-embed.lock"
    assert ruta.is_file(), f"{ruta} does not exist; the sidecar image has no pinned closure"
    return ruta.read_text(encoding="utf-8")


class TestCierreDeDependenciasDelSidecar:
    """3.1: the sidecar's closure is pinned, hashed, CPU-only and not the RAG one."""

    def test_every_requirement_is_pinned_to_an_exact_version(self, lock_del_sidecar):
        """A range in a serving lock is a rebuild that can change the vectors.

        `requirements-rag.txt` is a range spec (`torch>=2.0.0`,
        `transformers>=4.40.0`) and it is right to be one — it feeds an offline
        batch on a workstation. Inheriting that here would mean the provenance
        guard catches a BUILD problem in production, which is the expensive place
        to catch it.
        """
        sueltos = [
            linea
            for linea in lock_del_sidecar.splitlines()
            if linea and not linea.startswith((" ", "#", "-")) and "==" not in linea
        ]
        assert sueltos == []

    def test_every_pin_carries_hashes(self, lock_del_sidecar):
        """`--require-hashes` is refused by pip unless EVERY entry has one."""
        pines = re.findall(r"^([a-zA-Z0-9._-]+)==\S+", lock_del_sidecar, re.MULTILINE)
        assert pines, "the lock declares no requirements at all"
        assert lock_del_sidecar.count("--hash=sha256:") >= len(pines)

    def test_torch_is_the_cpu_wheel_and_the_cuda_stack_is_absent(self, lock_del_sidecar):
        """The box has no GPU and 2 shared vCPU. The CUDA stack is ~6 GB of dead weight."""
        assert re.search(r"^torch==\S+\+cpu", lock_del_sidecar, re.MULTILINE)
        assert "nvidia-" not in lock_del_sidecar

    def test_sentence_transformers_is_absent(self, lock_del_sidecar):
        """It exists in `requirements-rag.txt:30-33` for the E5 baseline ONLY.

        E5 is asymmetric and is not the model this corpus was embedded with; a
        serving container has no business carrying the machinery for a second,
        wrong-prefixed encoder.
        """
        assert "sentence-transformers" not in lock_del_sidecar

    def test_the_image_installs_the_lock_with_require_hashes(self):
        dockerfile = (DIRECTORIO_SIDECAR / "Dockerfile").read_text(encoding="utf-8")
        assert "--require-hashes" in dockerfile
        assert "requirements-embed.lock" in dockerfile

    def test_the_image_is_not_built_from_requirements_rag(self):
        dockerfile = (DIRECTORIO_SIDECAR / "Dockerfile").read_text(encoding="utf-8")
        assert "requirements-rag.txt" not in dockerfile

    def test_the_server_image_closure_is_still_torch_free(self):
        """The D8 guard, restated where U3 could plausibly have broken it.

        The sidecar exists so the backend never needs torch. If U3 had "solved"
        query embedding by adding torch to the app's own lock, every argument in
        `design.md:41-50` would have been lost and this suite would still be
        green without this line.
        """
        for nombre in ("requirements.lock", "requirements-dev.lock"):
            contenido = (RAIZ_DEL_REPO / "gee-backend" / nombre).read_text(encoding="utf-8")
            assert not re.search(r"^torch==", contenido, re.MULTILINE), nombre
            assert not re.search(r"^transformers==", contenido, re.MULTILINE), nombre


# --------------------------------------------------------------------------- #
# 3.2 — readiness is a state
# --------------------------------------------------------------------------- #


class EmbedderFalso:
    """Stands in for `BGEM3Embedder` inside the sidecar process.

    It reports an identity and counts its calls. It says nothing about retrieval
    quality and no test here asks it to.
    """

    sintetico = False

    def __init__(self, *, revision: str | None = REVISION_A) -> None:
        self.model_id = DEFAULT_MODEL_ID
        self.revision = revision
        self.dims = EMBEDDING_DIMENSIONS
        self.token_ceiling = TOKEN_CEILING
        self.llamadas: list[list[str]] = []

    def count_tokens(self, texto: str) -> int:
        return len(texto)

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        self.llamadas.append(list(textos))
        return [[1.0] + [0.0] * (self.dims - 1) for _ in textos]


@pytest.fixture(scope="module")
def modulo_sidecar():
    """Import `docker/embed/app.py` by path — it is not part of the app package.

    Loading it here rather than mirroring its behaviour in the test is the whole
    point: the file that ships in the image is the file under test.
    """
    ruta = DIRECTORIO_SIDECAR / "app.py"
    spec = importlib.util.spec_from_file_location("conocimiento_embed_app", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["conocimiento_embed_app"] = modulo
    spec.loader.exec_module(modulo)
    yield modulo
    sys.modules.pop("conocimiento_embed_app", None)


@pytest.fixture
def sidecar(modulo_sidecar):
    """A client over the real ASGI app with its load state reset per test."""
    modulo_sidecar.ESTADO.fallar(None)
    # The lifespan starts a loader thread that would try to pull 2.2 GB of
    # weights. `TestClient` without a context manager does not run lifespan,
    # which is exactly the isolation this needs: the load state is driven
    # explicitly below, one transition at a time.
    cliente = TestClient(modulo_sidecar.app)
    yield modulo_sidecar, cliente
    modulo_sidecar.ESTADO.fallar(None)


class TestPreparacionDelSidecar:
    """3.2: `/health` is liveness, `/ready` is the model, and they are not the same."""

    def test_health_answers_while_the_model_is_still_loading(self, sidecar):
        """Liveness must not wait on a 30-60 s model load, or the orchestrator restarts it."""
        _, cliente = sidecar
        respuesta = cliente.get("/health")
        assert respuesta.status_code == 200
        assert respuesta.json() == {"vivo": True}

    def test_ready_is_false_with_the_named_cause_before_the_model_loads(self, sidecar):
        _, cliente = sidecar
        respuesta = cliente.get("/ready")
        assert respuesta.status_code == 503
        cuerpo = respuesta.json()
        assert cuerpo["listo"] is False
        assert cuerpo["causa"] == "embedder_no_listo"

    def test_embed_refuses_before_the_model_loads(self, sidecar):
        """It refuses rather than blocking: a queued request thread is an outage that hangs."""
        _, cliente = sidecar
        respuesta = cliente.post("/embed", json={"textos": ["¿quién mantiene el canal?"]})
        assert respuesta.status_code == 503
        assert respuesta.json()["causa"] == "embedder_no_listo"

    def test_ready_reports_the_identity_once_loaded(self, sidecar):
        modulo, cliente = sidecar
        modulo.ESTADO.publicar(EmbedderFalso())

        cuerpo = cliente.get("/ready").json()
        assert cuerpo["listo"] is True
        assert cuerpo["modelo"] == DEFAULT_MODEL_ID
        assert cuerpo["revision_hf"] == REVISION_A
        assert cuerpo["dims"] == EMBEDDING_DIMENSIONS

    def test_embed_returns_vectors_carrying_the_identity_that_produced_them(self, sidecar):
        """Identity travels WITH the vectors, not on a separate `/ready` call.

        A sidecar restarted onto different weights between the two calls is the
        case the whole provenance chain exists for; reading the identity from a
        different request would miss it by construction.
        """
        modulo, cliente = sidecar
        modulo.ESTADO.publicar(EmbedderFalso())

        cuerpo = cliente.post("/embed", json={"textos": ["a", "b"]}).json()
        assert len(cuerpo["vectores"]) == 2
        assert cuerpo["modelo"] == DEFAULT_MODEL_ID
        assert cuerpo["revision_hf"] == REVISION_A

    def test_a_failed_load_is_reported_as_a_failure_not_as_a_slow_load(self, sidecar):
        """Two different operational facts. Collapsing them hides a broken container forever."""
        modulo, cliente = sidecar
        modulo.ESTADO.fallar("OSError: no such revision")

        cuerpo = cliente.get("/ready").json()
        assert cuerpo["listo"] is False
        assert "no such revision" in cuerpo["detalle"]

    def test_ready_only_turns_true_after_a_warm_up_embed(self, sidecar, monkeypatch):
        """`from_pretrained` returning is not readiness.

        The first forward pass is where the lazy kernel and tokenizer work
        actually happens, so a service that reported ready on construction alone
        would hand its first real caller the cold start it was built to hide.
        """
        modulo, _ = sidecar
        falso = EmbedderFalso()
        monkeypatch.setattr(modulo, "BGEM3Embedder", lambda **_kwargs: falso)

        assert modulo.ESTADO.listo() is False
        modulo.cargar(modulo.ESTADO)

        assert falso.llamadas == [[modulo.TEXTO_DE_CALENTAMIENTO]]
        assert modulo.ESTADO.listo() is True

    def test_a_warm_up_that_raises_leaves_the_sidecar_not_ready(self, sidecar, monkeypatch):
        """Loaded weights plus a broken forward pass is NOT ready, and must not read as ready."""
        modulo, cliente = sidecar

        class RompeAlCalentar(EmbedderFalso):
            def encode(self, textos):
                raise RuntimeError("kernel image is invalid")

        monkeypatch.setattr(modulo, "BGEM3Embedder", lambda **_kwargs: RompeAlCalentar())
        modulo.cargar(modulo.ESTADO)

        assert modulo.ESTADO.listo() is False
        assert cliente.get("/ready").json()["causa"] == "embedder_no_listo"


# --------------------------------------------------------------------------- #
# 3.2 — the adapter: the sidecar's states, seen from the backend
# --------------------------------------------------------------------------- #


def _transporte(manejador) -> httpx.MockTransport:
    return httpx.MockTransport(manejador)


def _sidecar_listo(
    *,
    modelo: str = DEFAULT_MODEL_ID,
    revision: str | None = REVISION_A,
    dims: int = EMBEDDING_DIMENSIONS,
    identidad_al_embeber: tuple[str, str | None] | None = None,
    vectores: list[list[float]] | None = None,
) -> httpx.MockTransport:
    def manejador(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/ready":
            return httpx.Response(
                200,
                json={
                    "listo": True,
                    "modelo": modelo,
                    "revision_hf": revision,
                    "dims": dims,
                    "token_ceiling": TOKEN_CEILING,
                },
            )
        if pedido.url.path == "/embed":
            m, r = identidad_al_embeber or (modelo, revision)
            return httpx.Response(
                200,
                json={
                    "vectores": vectores if vectores is not None else [[1.0] + [0.0] * (dims - 1)],
                    "modelo": m,
                    "revision_hf": r,
                    "dims": dims,
                    "token_ceiling": TOKEN_CEILING,
                },
            )
        raise AssertionError(f"unexpected path {pedido.url.path}")

    return _transporte(manejador)


class TestAdaptadorDelSidecar:
    """The backend half: every sidecar state becomes a NAMED refusal, never a guess."""

    def test_it_carries_model_and_revision_verbatim_into_the_seam(self):
        """Hardcoding `BAAI/bge-m3` here would defeat `verificar_embedder` entirely."""
        embedder = conectar_sidecar("http://embed:8002", transporte=_sidecar_listo())

        assert embedder.model_id == DEFAULT_MODEL_ID
        assert embedder.revision == REVISION_A
        assert embedder.sintetico is False

    def test_a_sidecar_that_is_not_ready_is_a_named_refusal(self):
        def manejador(_pedido: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"listo": False, "causa": CAUSA_NO_LISTO})

        with pytest.raises(SidecarNoDisponible) as refusal:
            conectar_sidecar("http://embed:8002", transporte=_transporte(manejador))

        assert refusal.value.causa == CAUSA_NO_LISTO

    def test_an_unreachable_sidecar_is_a_named_refusal(self):
        """`design.md:198-202`: it is never a stage-1 redirect and never an abstention.

        A redirect is a CLASSIFICATION CLAIM. Making it because a container is
        down is a fabricated classification.
        """

        def manejador(pedido: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=pedido)

        with pytest.raises(SidecarNoDisponible) as refusal:
            conectar_sidecar("http://embed:8002", transporte=_transporte(manejador))

        assert refusal.value.causa == CAUSA_INALCANZABLE

    def test_a_malformed_vector_is_a_named_refusal_not_a_ranking(self):
        embedder = conectar_sidecar(
            "http://embed:8002",
            transporte=_sidecar_listo(vectores=[[1.0, 0.0]]),
        )

        with pytest.raises(SidecarNoDisponible) as refusal:
            embedder.encode(["¿quién mantiene el canal?"])

        assert refusal.value.causa == CAUSA_RESPUESTA_INVALIDA

    def test_a_restart_onto_different_weights_mid_flight_is_refused(self):
        """`/ready` said one thing, `/embed` produced another. That is the guard's whole subject."""
        embedder = conectar_sidecar(
            "http://embed:8002",
            transporte=_sidecar_listo(identidad_al_embeber=(DEFAULT_MODEL_ID, REVISION_B)),
        )

        with pytest.raises(SidecarNoDisponible) as refusal:
            embedder.encode(["¿quién mantiene el canal?"])

        assert refusal.value.causa == CAUSA_RESPUESTA_INVALIDA
        assert REVISION_B in str(refusal.value)

    def test_counting_tokens_refuses_rather_than_estimating(self):
        """`count_tokens` is an INGESTION pre-flight and this is a QUERY seam.

        Returning a plausible estimate would let an ingestion path silently
        measure the ceiling with something that is not the model's tokenizer —
        the exact failure `token_ceiling` was made an embedder attribute to
        prevent.
        """
        embedder = conectar_sidecar("http://embed:8002", transporte=_sidecar_listo())

        with pytest.raises(NotImplementedError):
            embedder.count_tokens("hola")

    def test_it_satisfies_the_embedder_protocol(self):
        from app.domains.conocimiento.embedding import Embedder

        embedder = conectar_sidecar("http://embed:8002", transporte=_sidecar_listo())
        assert isinstance(embedder, Embedder)
        assert isinstance(embedder, SidecarEmbedder)


# --------------------------------------------------------------------------- #
# 3.3 / 3.4 — revision canonicalization
# --------------------------------------------------------------------------- #


class TestCanonicalizacionDeRevision:
    """3.3: the compared value is always the RESOLVED commit hash, on both sides.

    Without this the realistic deployment — an offline manifest stamped with a
    hash, a sidecar started from `EMBED_REVISION_HF=<tag>` — makes the guard fire
    on two processes running the SAME weights, and the surface serves a permanent
    503 that no amount of re-loading fixes. That failure is indistinguishable at
    the query surface from the real mismatch the guard exists for, which is the
    worst possible shape for a guard (`design.md:61-84`).
    """

    def test_a_symbolic_pin_and_its_resolved_hash_compare_equal(self):
        """The manifest holds the hash, the operator started the sidecar from a tag."""
        del_sidecar = resolver_revision("v1.5", REVISION_A)
        del_manifiesto = canonicalizar_revision(REVISION_A)

        assert del_sidecar == del_manifiesto == REVISION_A

    def test_two_different_hashes_compare_unequal(self):
        assert canonicalizar_revision(REVISION_A) != canonicalizar_revision(REVISION_B)

    def test_case_is_not_an_identity(self):
        assert canonicalizar_revision(REVISION_A.upper()) == REVISION_A

    @pytest.mark.parametrize("ref", ["main", "v1.5", "refs/heads/main", "", "   ", "abc123"])
    def test_a_non_resolvable_ref_refuses(self, ref):
        """It never falls back to string-comparing tags.

        Two different commits can both be tagged `main`, and a tag comparison
        would pass them — which is the same fabricated ranking the guard is
        written to refuse, wearing a green check.
        """
        with pytest.raises(RevisionNoResoluble):
            canonicalizar_revision(ref)

    def test_null_stays_null(self):
        assert canonicalizar_revision(None) is None

    def test_the_resolved_hash_wins_over_the_symbolic_argument(self):
        """3.4: `EMBED_REVISION_HF` is an INPUT, never the report."""
        assert resolver_revision("main", REVISION_A) == REVISION_A

    def test_the_argument_survives_only_when_nothing_was_resolved(self):
        assert resolver_revision(REVISION_B, None) == REVISION_B

    def test_an_unresolvable_argument_with_no_resolved_hash_refuses(self):
        with pytest.raises(RevisionNoResoluble):
            resolver_revision("main", None)

    def test_nothing_requested_and_nothing_resolved_is_null(self):
        assert resolver_revision(None, None) is None

    def test_the_real_embedder_prefers_the_config_commit_hash(self):
        """3.4: `embedding.py:372` inverted, asserted on the source rather than on a 2.2 GB load.

        `BGEM3Embedder.__init__` cannot be exercised without torch and the
        weights, so what is checked is the precedence itself: the resolution goes
        through `resolver_revision`, whose ordering is covered above, and the old
        `revision or _commit_hash` form is gone.
        """
        import inspect

        from app.domains.conocimiento.embedding import BGEM3Embedder

        fuente = inspect.getsource(BGEM3Embedder.__init__)
        assert "resolver_revision" in fuente
        assert "revision or getattr" not in fuente


# --------------------------------------------------------------------------- #
# 3.5 — the guard compares the TUPLE
# --------------------------------------------------------------------------- #


def sembrar_corpus(db, *, sha: str = SHA) -> None:
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 1, true)"
        ),
        {"sha": sha},
    )
    db.flush()


class EmbedderConIdentidad:
    """A stand-in whose ONLY job is to report a `(model_id, revision)` pair."""

    sintetico = False
    dims = EMBEDDING_DIMENSIONS
    token_ceiling = TOKEN_CEILING

    def __init__(self, model_id: str, revision: str | None) -> None:
        self.model_id = model_id
        self.revision = revision

    def count_tokens(self, texto: str) -> int:
        return len(texto)

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (self.dims - 1) for _ in textos]


@pytest.fixture
def corpus(db):
    sembrar_corpus(db)
    return db


def estampar(db, *, modelo: str, revision_hf: str | None, sintetico: bool) -> None:
    registrar_procedencia(
        db,
        SHA,
        modelo=modelo,
        revision_hf=revision_hf,
        sintetico=sintetico,
        artifact_sha256="9" * 64,
    )
    db.flush()


class TestGuardaDeIdentidadPorTupla:
    """3.5: `(modelo, revision_hf)` — half a door is not a door.

    `ProcedenciaEmbeddings` has carried `revision_hf` since migration
    `conocimiento_004` and `VectorsManifest` has stamped it all along; the guard
    simply never read it. Two BGE-M3 revisions report the same `model_id`, so the
    model-only check passes and the vector leg returns fifty confident,
    fully-attributed hits ranked by arithmetic that means nothing.
    """

    def test_same_model_different_revision_is_refused(self, corpus):
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=REVISION_A, sintetico=False)

        with pytest.raises(service.EmbedderMismatch) as refusal:
            service.verificar_embedder(
                corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, REVISION_B)
            )

        mensaje = str(refusal.value)
        assert REVISION_A in mensaje and REVISION_B in mensaje

    def test_same_model_same_revision_is_accepted(self, corpus):
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=REVISION_A, sintetico=False)
        service.verificar_embedder(corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, REVISION_A))

    def test_a_symbolic_pin_resolved_to_the_stored_hash_is_accepted(self, corpus):
        """The false-positive this canonicalization exists to prevent.

        The offline batch and the serving sidecar are started by different
        operators at different times. If the tag/hash pair refused, the surface
        would serve a permanent 503 over two processes running identical weights.
        """
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=REVISION_A, sintetico=False)
        resuelta = resolver_revision("main", REVISION_A)
        service.verificar_embedder(corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, resuelta))

    def test_a_stored_revision_that_is_not_a_hash_is_unknown_provenance(self, corpus):
        """It never falls back to comparing `main` against `main`."""
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf="main", sintetico=False)

        with pytest.raises(service.EmbedderMismatch, match="main"):
            service.verificar_embedder(
                corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, REVISION_A)
            )

    def test_an_embedder_revision_that_is_not_a_hash_is_unknown_provenance(self, corpus):
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=REVISION_A, sintetico=False)

        with pytest.raises(service.EmbedderMismatch, match="v1.5"):
            service.verificar_embedder(corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, "v1.5"))

    def test_a_null_stored_revision_is_refused_rather_than_matching_anything(self, corpus):
        """Rows loaded before the sidecar existed. NULL is UNKNOWN, not a wildcard.

        Treating it as "matches anything" would restore the exact hole this task
        closes. The fix is a re-load of a manifest that carries the revision, and
        the guard says so.
        """
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=None, sintetico=False)

        with pytest.raises(service.EmbedderMismatch):
            service.verificar_embedder(
                corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, REVISION_A)
            )

    def test_null_on_both_sides_is_refused_for_a_real_embedder(self, corpus):
        """The one exemption is `DeterministicEmbedder`'s, and it is keyed on `sintetico`.

        A real embedder reporting no revision has unknown provenance no matter
        what the row says; matching two unknowns would be matching nothing to
        nothing and calling it identity.
        """
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=None, sintetico=False)

        with pytest.raises(service.EmbedderMismatch):
            service.verificar_embedder(corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, None))

    def test_null_on_both_sides_is_accepted_for_the_deterministic_embedder(self, corpus):
        """The smoke path stays open: the pipeline must be exercisable end to end.

        `DeterministicEmbedder.revision` is `None` by construction
        (`embedding.py:304`) and its artifacts stamp `revision_hf: null`.
        """
        estampar(corpus, modelo=DETERMINISTIC_MODEL_ID, revision_hf=None, sintetico=True)
        service.verificar_embedder(corpus, SHA, DeterministicEmbedder())

    def test_the_model_half_of_the_guard_still_refuses(self, corpus):
        """Regression: adding the revision must not have relaxed the original check."""
        estampar(corpus, modelo=DETERMINISTIC_MODEL_ID, revision_hf=None, sintetico=True)

        with pytest.raises(service.EmbedderMismatch):
            service.verificar_embedder(
                corpus, SHA, EmbedderConIdentidad(DEFAULT_MODEL_ID, REVISION_A)
            )


# --------------------------------------------------------------------------- #
# 3.6 — one question, one embedding
# --------------------------------------------------------------------------- #


class TestVectorDeConsultaProvistoPorElLlamador:
    """3.6: `recuperar` accepts a `qvec`, and `qvec` bypasses NOTHING.

    Stage 2 of the router and the retrieval vector leg need the SAME vector of
    the SAME text under the SAME model. Embedding twice costs a second sidecar
    hop on the critical path and, worse, creates a state where the router
    classified one vector and retrieval searched another (`design.md:145-160`).
    """

    def test_recuperar_declares_a_keyword_only_qvec(self):
        import inspect

        firma = inspect.signature(service.recuperar)
        assert "qvec" in firma.parameters
        assert firma.parameters["qvec"].kind is inspect.Parameter.KEYWORD_ONLY
        assert firma.parameters["qvec"].default is None

    def test_qvec_does_not_bypass_the_identity_guard(self, corpus, monkeypatch):
        """The identity lives on the EMBEDDER, not on the vector.

        A caller handing in a vector computed by a different model is a bug the
        guard cannot see; what it can see, and must keep seeing, is that the
        embedder it was given is not the one that wrote the column.

        `require_vector_support` is stubbed because it runs FIRST by design
        (capability before content) and CI's image has no pgvector — stubbing it
        is what puts `verificar_embedder` in reach, and the ordering itself is
        already covered by `test_rag_retrieval.py`.
        """
        monkeypatch.setattr(service, "require_vector_support", lambda _db: None)
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=REVISION_A, sintetico=False)

        with pytest.raises(service.EmbedderMismatch):
            service.recuperar(
                corpus,
                SHA,
                "¿quién mantiene el canal?",
                modo="vector",
                embedder=EmbedderConIdentidad(DEFAULT_MODEL_ID, REVISION_B),
                qvec=[1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
            )

    def test_qvec_does_not_make_the_embedder_optional(self, corpus):
        """`embedder` is still required: the identity it carries is the thing compared."""
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=REVISION_A, sintetico=False)

        with pytest.raises(service.EmbedderRequerido):
            service.recuperar(
                corpus,
                SHA,
                "¿quién mantiene el canal?",
                modo="vector",
                qvec=[1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
            )

    def test_the_callers_vector_is_used_instead_of_re_embedding(self, corpus, monkeypatch):
        """The behaviour change is exactly one line: use the caller's vector if given."""
        estampar(corpus, modelo=DEFAULT_MODEL_ID, revision_hf=REVISION_A, sintetico=False)

        class NoDebeEmbeber(EmbedderConIdentidad):
            def encode(self, textos):
                raise AssertionError("recuperar re-embedded a question it was handed a vector for")

        qvec = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
        capturado: list[list[float]] = []

        def espia_vector_search(_db, _sha, vector, *, limite):
            capturado.append(list(vector))
            return []

        monkeypatch.setattr(service, "vector_search", espia_vector_search)
        monkeypatch.setattr(service, "require_vector_support", lambda _db: None)

        service.recuperar(
            corpus,
            SHA,
            "¿quién mantiene el canal?",
            modo="vector",
            embedder=NoDebeEmbeber(DEFAULT_MODEL_ID, REVISION_A),
            qvec=qvec,
        )

        assert capturado == [qvec]
