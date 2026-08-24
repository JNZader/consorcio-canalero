"""`conocimiento-embed`: one BGE-M3 process, three endpoints, no database.

Why this exists at all: the server image cannot embed a query and must not learn
how. `requirements-rag.txt:1-9` says torch is "jamás para la imagen del
servidor", the V0 Judgment Day amendment asserts by test that
`torch`/`transformers`/`FlagEmbedding` appear in none of the app's three
requirement closures, and the app runs two uvicorn workers — torch in the image
would mean two 2.2 GB model copies on a 2-vCPU box. So the model lives here, in
one process, loaded once (`design.md:41-50`).

Three properties are contracts, not implementation details:

* **The encoder is the backend's `BGEM3Embedder`, imported, not re-implemented.**
  The Dockerfile copies `embedding.py` and `ddl.py` into the image for exactly
  this reason. A second CLS-pooling-plus-L2-normalize written out here would be a
  second implementation of the thing the corpus vectors were produced with, and
  the failure mode of the two drifting apart — same model id, same revision,
  different vectors — is precisely the one `verificar_embedder` CANNOT see,
  because both operands would still report `BAAI/bge-m3` at the same commit.

* **`revision_hf` is the RESOLVED commit hash, and it is an output, never an
  echo of the input.** `EMBED_REVISION_HF` may be a tag, a branch or a hash; what
  this service reports is what `transformers` recorded on the loaded config
  (`design.md:73-84`). A tag comparison would pass two different commits both
  tagged `main`.

* **Readiness is a state, not a wait.** `/health` answers the moment the process
  is up; `/ready` turns true only after the weights load AND one warm-up embed
  completes. Until then `/embed` refuses with `embedder_no_listo`
  (`design.md:117-120`). The request thread never blocks on a 30-60 s model load,
  and nothing downstream routes or abstains on the strength of an embedder that
  has not finished loading.

The service takes no `DATABASE_URL`, opens no connection and reads no corpus. It
turns text into vectors.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domains.conocimiento.embedding import DEFAULT_MODEL_ID, TOKEN_CEILING, BGEM3Embedder

LOG = logging.getLogger("conocimiento_embed")

#: The pin the operator asked for. It is an INPUT: a tag, a branch or a hash are
#: all accepted here, and none of them is what gets reported. Empty means "the
#: revision transformers resolves by default", which is still reported as the
#: resolved hash.
MODEL_ID = os.environ.get("EMBED_MODEL_ID", DEFAULT_MODEL_ID)
REVISION_SOLICITADA = os.environ.get("EMBED_REVISION_HF") or None
DEVICE = os.environ.get("EMBED_DEVICE", "cpu")
MAX_LENGTH = int(os.environ.get("EMBED_MAX_LENGTH", str(TOKEN_CEILING)))

#: The text the warm-up embeds. Its content is irrelevant and its execution is
#: not: the first forward pass is where lazy CUDA/kernel initialisation and the
#: tokenizer's own lazy files actually happen, so a service that reported ready
#: on `from_pretrained` alone would hand its first real caller the cold-start
#: cost it was built to hide.
TEXTO_DE_CALENTAMIENTO = "consorcio canalero"

#: The cause name the backend adapter and the surface both key on. Spelled once,
#: here, because it crosses a process boundary as a string.
CAUSA_NO_LISTO = "embedder_no_listo"


class EstadoDelModelo:
    """Load state, owned by the loader thread and read by the request threads.

    Deliberately three-valued rather than a boolean: "still loading" and "failed
    to load" are different operational facts, and collapsing them would make a
    permanently broken sidecar look like a slow one forever.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.embedder: BGEM3Embedder | None = None
        self.error: str | None = None

    def listo(self) -> bool:
        with self._lock:
            return self.embedder is not None

    def publicar(self, embedder: BGEM3Embedder) -> None:
        with self._lock:
            self.embedder = embedder
            self.error = None

    def fallar(self, detalle: str) -> None:
        with self._lock:
            self.embedder = None
            self.error = detalle

    def instantanea(self) -> tuple[BGEM3Embedder | None, str | None]:
        with self._lock:
            return self.embedder, self.error


ESTADO = EstadoDelModelo()


def cargar(estado: EstadoDelModelo) -> None:
    """Load the weights and burn one forward pass, then publish. Never both halves."""
    try:
        embedder = BGEM3Embedder(
            model_id=MODEL_ID,
            device=DEVICE,
            revision=REVISION_SOLICITADA,
            max_length=MAX_LENGTH,
        )
        embedder.encode([TEXTO_DE_CALENTAMIENTO])
    except Exception as exc:  # noqa: BLE001 - the state IS the error report
        LOG.exception("model load failed")
        estado.fallar(f"{type(exc).__name__}: {exc}")
        return
    LOG.info("model %s ready at revision %s", embedder.model_id, embedder.revision)
    estado.publicar(embedder)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    hilo = threading.Thread(target=cargar, args=(ESTADO,), name="carga-modelo", daemon=True)
    hilo.start()
    yield


app = FastAPI(title="conocimiento-embed", lifespan=lifespan)


class PedidoDeEmbedding(BaseModel):
    textos: list[str] = Field(min_length=1)


def _no_listo(error: str | None) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "listo": False,
            "causa": CAUSA_NO_LISTO,
            "detalle": error or "the model is still loading",
        },
    )


def _identidad(embedder: BGEM3Embedder) -> dict[str, Any]:
    return {
        "modelo": embedder.model_id,
        "revision_hf": embedder.revision,
        "revision_solicitada": REVISION_SOLICITADA,
        "dims": embedder.dims,
        "token_ceiling": embedder.token_ceiling,
    }


@app.get("/health")
def health() -> dict[str, bool]:
    """The process is up. Says NOTHING about the model — that is `/ready`'s job."""
    return {"vivo": True}


@app.get("/ready")
def ready() -> Any:
    embedder, error = ESTADO.instantanea()
    if embedder is None:
        return _no_listo(error)
    return {"listo": True, **_identidad(embedder)}


@app.post("/embed")
def embed(pedido: PedidoDeEmbedding) -> Any:
    embedder, error = ESTADO.instantanea()
    if embedder is None:
        return _no_listo(error)
    vectores = embedder.encode(pedido.textos)
    # The identity travels with every batch of vectors on purpose: the caller's
    # guard compares what produced THESE numbers, not what a separate `/ready`
    # call reported at some other moment. A sidecar restarted onto different
    # weights between the two calls is exactly the case the guard exists for.
    return {"vectores": vectores, **_identidad(embedder)}
