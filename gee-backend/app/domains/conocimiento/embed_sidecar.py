"""The backend half of the query-embedding sidecar: an `Embedder` over HTTP.

The app image holds no model, no weights and no torch import — that is the whole
point of `design.md:41-50`, and the V0 Judgment Day amendment asserts it by test
against all three requirement closures. What it holds instead is a URL, a
timeout, and this adapter.

Two rules govern everything here.

**The identity is carried verbatim, never reconstructed.** `model_id` and
`revision` come from what the sidecar reports about the weights it actually
loaded. Hardcoding `"BAAI/bge-m3"` on this side would defeat `verificar_embedder`
completely (`service.py`), because the guard would then be comparing a constant
against a database row — it would agree with itself no matter which model was
running, which is a guard that has been quietly deleted rather than a guard that
passes.

**Every failure is a NAMED refusal.** Unreachable, not `/ready`, timing out or
returning a malformed vector all end as `SidecarNoDisponible` with a `causa`, and
the surface turns that into `no_disponible` with the cause named. It never falls
back to stage-1 rules and answers, and it never redirects: a redirect is a
*classification claim* ("this is operational, go to /finanzas"), and making that
claim because a container is down is a fabricated classification
(`design.md:198-202`).
"""

from __future__ import annotations

from typing import Any, Sequence

import httpx

from app.domains.conocimiento.ddl import EMBEDDING_DIMENSIONS
from app.domains.conocimiento.embedding import TOKEN_CEILING

#: The cause names. They cross a process boundary and reach a user-facing state,
#: so they are constants rather than string literals sprinkled at raise sites.
#: `embedder_no_listo` is the one the design names verbatim (`design.md:117-120`).
CAUSA_NO_LISTO = "embedder_no_listo"
CAUSA_INALCANZABLE = "embedder_inalcanzable"
CAUSA_RESPUESTA_INVALIDA = "embedder_respuesta_invalida"

#: The sidecar loads a 2.2 GB model once; a query embedding afterwards is
#: milliseconds-to-a-second work on CPU. This ceiling is about a HUNG sidecar,
#: not about a slow one, and the box's real query-embedding latency is an
#: unmeasured risk with its own measurement task (`design.md:107-116`).
TIMEOUT_POR_DEFECTO_S = 10.0


class SidecarNoDisponible(RuntimeError):
    """The query cannot be embedded, and the reason is named rather than guessed.

    Deliberately not a subclass of anything the retrieval path already catches:
    the caller must decide to end the request in `no_disponible`, and a failure
    that could be swallowed by an existing `except` would become a silent
    downgrade — which is the entire failure family this domain is arranged
    against.
    """

    def __init__(self, causa: str, detalle: str) -> None:
        super().__init__(f"{causa}: {detalle}")
        self.causa = causa
        self.detalle = detalle


class SidecarEmbedder:
    """An `Embedder` whose arithmetic happens in another process.

    Constructed through `conectar_sidecar`, never directly, because the identity
    attributes the `Embedder` protocol declares are only knowable after `/ready`
    answers — and an instance carrying a placeholder identity is precisely the
    object `verificar_embedder` must never be handed.
    """

    sintetico = False

    def __init__(
        self,
        cliente: httpx.Client,
        *,
        model_id: str,
        revision: str | None,
        dims: int,
        token_ceiling: int,
    ) -> None:
        self._cliente = cliente
        self.model_id = model_id
        self.revision = revision
        self.dims = dims
        self.token_ceiling = token_ceiling

    def close(self) -> None:
        """Release the HTTP pool. Idempotent, and NOT optional for short-lived uses.

        Added in U7 for the same reason `PuenteGenerador.close` exists: the
        readiness gate builds one of these every TTL to ask `/ready` and throws
        it away, and a leaked pool per probe is a descriptor leak that shows up
        as a server that stops answering and blames the sidecar. A long-lived
        adapter never needs this; the probe does.
        """
        self._cliente.close()

    def __enter__(self) -> SidecarEmbedder:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.close()

    def count_tokens(self, texto: str) -> int:
        """Refused on purpose. This is a QUERY seam; token counting is INGESTION.

        The ceiling pre-flight has to be measured with the model's real
        tokenizer, in the same process that will truncate — which is
        `rag_embed_batch.py` on the workstation, over the corpus, before
        anything is embedded. Returning a plausible estimate from here would let
        an ingestion path measure the ceiling with something that is not the
        tokenizer, and the symptom would be silent truncation inside the model.
        """
        raise NotImplementedError(
            "the query sidecar does not count tokens. The ceiling pre-flight is an "
            "ingestion-time measurement and belongs to the batch embedder, which "
            "holds the real tokenizer (see scripts/rag_embed_batch.py)."
        )

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        cuerpo = self._pedir("POST", "/embed", json={"textos": list(textos)})
        vectores = cuerpo.get("vectores")

        # The identity travels WITH the vectors and is re-checked here. A sidecar
        # restarted onto different weights between `/ready` and this call reports
        # the same URL and a different model; reading the identity only at
        # connection time would miss it by construction, and the resulting hits
        # would be fully attributed to weights that never produced them.
        if (cuerpo.get("modelo"), cuerpo.get("revision_hf")) != (self.model_id, self.revision):
            raise SidecarNoDisponible(
                CAUSA_RESPUESTA_INVALIDA,
                f"the sidecar reported {self.model_id!r}@{self.revision!r} when it "
                f"was connected and {cuerpo.get('modelo')!r}@"
                f"{cuerpo.get('revision_hf')!r} for these vectors. It was restarted "
                "onto different weights mid-flight.",
            )

        if not isinstance(vectores, list) or len(vectores) != len(textos):
            raise SidecarNoDisponible(
                CAUSA_RESPUESTA_INVALIDA,
                f"expected {len(textos)} vectors, got {vectores!r}",
            )
        for vector in vectores:
            if not isinstance(vector, list) or len(vector) != self.dims:
                raise SidecarNoDisponible(
                    CAUSA_RESPUESTA_INVALIDA,
                    f"a vector of {len(vector) if isinstance(vector, list) else '?'} "
                    f"dimensions cannot be compared against a {self.dims}-dimension "
                    "column: the distance would compute and mean nothing.",
                )
        return [[float(v) for v in vector] for vector in vectores]

    def _pedir(self, metodo: str, ruta: str, **kwargs: Any) -> dict[str, Any]:
        try:
            respuesta = self._cliente.request(metodo, ruta, **kwargs)
        except httpx.TimeoutException as agotado:
            raise SidecarNoDisponible(CAUSA_INALCANZABLE, f"timed out: {agotado}") from agotado
        except httpx.HTTPError as fallo:
            raise SidecarNoDisponible(CAUSA_INALCANZABLE, str(fallo)) from fallo

        if respuesta.status_code == 503:
            raise SidecarNoDisponible(CAUSA_NO_LISTO, _detalle_de(respuesta))
        if respuesta.status_code != 200:
            raise SidecarNoDisponible(
                CAUSA_RESPUESTA_INVALIDA,
                f"HTTP {respuesta.status_code} from {ruta}: {_detalle_de(respuesta)}",
            )
        try:
            cuerpo = respuesta.json()
        except ValueError as no_json:
            raise SidecarNoDisponible(
                CAUSA_RESPUESTA_INVALIDA, f"{ruta} returned non-JSON"
            ) from no_json
        if not isinstance(cuerpo, dict):
            raise SidecarNoDisponible(CAUSA_RESPUESTA_INVALIDA, f"{ruta} returned {cuerpo!r}")
        return cuerpo


def _detalle_de(respuesta: httpx.Response) -> str:
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return respuesta.text[:200]
    if isinstance(cuerpo, dict):
        return str(cuerpo.get("detalle") or cuerpo.get("causa") or cuerpo)
    return str(cuerpo)


def conectar_sidecar(
    url: str,
    *,
    timeout: float = TIMEOUT_POR_DEFECTO_S,
    transporte: httpx.BaseTransport | None = None,
) -> SidecarEmbedder:
    """Ask `/ready` who is loaded, and build the seam around that answer.

    Readiness is checked at connection time and NOT waited on: a model load takes
    30-60 s and a request thread parked on it is an outage that hangs rather than
    an outage that says so (`design.md:117-120`). A sidecar that has not finished
    loading raises `SidecarNoDisponible(CAUSA_NO_LISTO)` here, the caller ends the
    request in `no_disponible` with that cause, and the next request tries again.

    `transporte` exists so the adapter's refusals are testable without a
    container. Nothing in production passes it.
    """
    cliente = httpx.Client(base_url=url, timeout=timeout, transport=transporte)
    # Every refusal below closes the pool on the way out. U7's readiness gate
    # calls this once per TTL and discards the result, so a client leaked on the
    # FAILURE path leaks once every few seconds for as long as the sidecar is
    # down — the exact condition under which the server can least afford to run
    # out of descriptors (bounded correction, U7).
    try:
        sonda = SidecarEmbedder(
            cliente,
            model_id="",
            revision=None,
            dims=EMBEDDING_DIMENSIONS,
            token_ceiling=TOKEN_CEILING,
        )
        cuerpo = sonda._pedir("GET", "/ready")

        if not cuerpo.get("listo"):
            raise SidecarNoDisponible(CAUSA_NO_LISTO, str(cuerpo.get("detalle") or cuerpo))

        modelo = cuerpo.get("modelo")
        if not isinstance(modelo, str) or not modelo:
            raise SidecarNoDisponible(
                CAUSA_RESPUESTA_INVALIDA,
                f"/ready reported modelo={modelo!r}. An embedder with no identity "
                "cannot be compared against the snapshot's recorded provenance, and "
                "assuming one would make the guard agree with itself.",
            )
        revision = cuerpo.get("revision_hf")
        if revision is not None and not isinstance(revision, str):
            raise SidecarNoDisponible(
                CAUSA_RESPUESTA_INVALIDA, f"/ready reported revision_hf={revision!r}"
            )

        dims = cuerpo.get("dims")
        if not isinstance(dims, int) or dims <= 0:
            raise SidecarNoDisponible(CAUSA_RESPUESTA_INVALIDA, f"/ready reported dims={dims!r}")
    except BaseException:
        cliente.close()
        raise

    techo = cuerpo.get("token_ceiling")
    return SidecarEmbedder(
        cliente,
        model_id=modelo,
        revision=revision,
        dims=dims,
        token_ceiling=techo if isinstance(techo, int) and techo > 0 else TOKEN_CEILING,
    )
