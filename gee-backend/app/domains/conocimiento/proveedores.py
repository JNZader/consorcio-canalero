"""U6: the concrete provider seam — the pin, its terms gate and its budgets.

U5 declared the port (`generacion.Generador`) and shipped only the stand-in. This
module fills it with the real adapter, and everything here is arranged around
three facts that the amendments ratified.

**The pin is `deepseek-v4-flash` through the opencode-go pool, routed by
mcp-llm-bridge, and it lives in CONFIG (amendment A2).** Changing the model must
be a config edit and never a code edit, so no model name is written in this file:
`model_id` is whatever `conocimiento_modelo` says, and it is carried verbatim
into the outbound payload and out to `verificar_generador`-style provenance. A
hardcoded name here would make the pin a lie the moment someone changed the env
var — the same failure mode the sidecar's identity rule exists to prevent
(`embed_sidecar.py`).

**The terms are a pin CRITERION, not a footnote (`design.md:493-497`, task
6.7).** A provider that trains on inputs is not eligible regardless of price or
latency, because the ratified privacy amendment permits public law text plus the
question to leave the box — not to become training data. What lives in code is
the MECHANISM: a checked-in record next to the pin, and a gate that refuses when
that record is absent, unverified, unauditable or about a different model. The
verification itself is the owner's operational act (see
`docs/rag/proveedor-terminos.md`); the record shipped today is UNVERIFIED, so the
gate refuses today. Fail-closed, not a warning.

**The semaphore is gone and the timeouts moved (amendment A3).** There is no HTTP
request to abort here: a queued item is processed by a worker, so
`conocimiento_provider_timeout_s` bounds ONE attempt and `PresupuestoDeItem`
bounds the whole item. Saturation is queue depth, not a refusal at the door.

Nothing in this module ever runs in a test against a real socket: every seam is
constructed through `conectar_puente`, which takes an `httpx.BaseTransport`
exactly so the refusals are testable without a gateway.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx
import yaml

from app.domains.conocimiento.costos import MedidorDeGasto
from app.domains.conocimiento.generacion import (
    GeneracionNoDisponible,
    GeneracionTransporte,
    PresupuestoAgotado,
    SalidaProveedor,
)

#: Re-exported for the readers who look for it next to the budget that raises it.
#: It is DEFINED in `generacion.py` because `generar_respuesta` has to catch it,
#: and that module cannot import this one without a cycle. A terminal state the
#: state machine cannot name is a state it cannot reach.
__all__ = [
    "CAMPOS_CORTE",
    "CAMPOS_TEXTO",
    "CORTE_COMPLETO",
    "CORTE_POR_LONGITUD",
    "EVIDENCIA_REQUERIDA",
    "RETENCION_MAX_DIAS",
    "RUTA_GENERAR",
    "TERMINOS_PATH",
    "PresupuestoAgotado",
    "PresupuestoDeItem",
    "ProveedorMalConfigurado",
    "PuenteGenerador",
    "TerminosNoVerificados",
    "cargar_terminos",
    "conectar_puente",
    "verificar_terminos",
]

#: The bridge's generation route. One constant, because it is the seam between
#: this repo and a service configured outside it.
RUTA_GENERAR = "/v1/generate"

#: The terms record lives NEXT TO THE PIN, in the domain, checked in — so a
#: silent terms change is a diff rather than a discovery (`design.md:496-497`).
TERMINOS_PATH = Path(__file__).parent / "proveedor_terminos.yaml"

#: Stop reasons that mean "the model stopped because it was done".
CORTE_COMPLETO = frozenset({"stop", "end_turn", "stop_sequence", "eos"})
#: Stop reasons that mean "the model stopped because it ran out of room". This is
#: NOT a failure: the call completed, it is an enforcement violation, and it
#: consumes the single regeneration attempt (`design.md:555-576`).
CORTE_POR_LONGITUD = frozenset({"max_tokens", "length", "max_output_tokens"})

#: Response field aliases. The gateway's exact body shape is configured outside
#: this repo and is part of what task 6.7 verifies operationally; accepting the
#: two or three names it plausibly uses is cheaper than a wrong guess that fails
#: closed at 3 a.m., and every unrecognised shape still REFUSES rather than
#: producing an empty answer.
CAMPOS_TEXTO = ("text", "content", "completion", "output")
CAMPOS_CORTE = ("stop_reason", "finish_reason", "stop")


# ---------------------------------------------------------------------------
# 6.6 — there is no server-side answer cache, and that is a DECISION
# ---------------------------------------------------------------------------
#
# Written here, at the only place a cache would plausibly be added, because a
# decision recorded only in a design document is a decision the next reader of
# this file will not find.
#
# Every question is answered fresh (`design.md:499-514`). The reason is the
# per-request privacy contract: a cache keyed on the question would serve an
# answer built from a payload whose classification was verified at some EARLIER
# request, so a document reclassified to `privado` would keep leaking through the
# cache for as long as the entry lived. And a cache that re-verified the
# classification on every hit has already done the expensive part of the work —
# it would save the generation call and keep the retrieval, which is not where
# the cost is.
#
# The cost of not caching is bounded by the quota and the spend ceiling in
# `costos.py`, which are the controls that belong to that problem. Client side
# the same rule holds in the other direction: a finite `staleTime` and no
# persistence to `localStorage`/`IndexedDB` (U8), because an answer sitting in a
# persisted cache is a legal opinion outliving the session that asked for it.
#
# Stated rather than silently ignored: answers already served are historical
# documents. If a document is later reclassified `privado`, past answers that
# cited it were served under the classification then in force. V1 has no answer
# store to purge; when the queue's item history becomes one, this note becomes a
# requirement.


class ProveedorMalConfigurado(RuntimeError):
    """The adapter cannot be built: no credential, no pin, no pool.

    Raised at CONSTRUCTION rather than at the first call. A misconfigured
    provider discovered on the first question is a question that dies; discovered
    at wiring time it is a boot failure, which is where a configuration fact
    belongs.
    """


class TerminosNoVerificados(RuntimeError):
    """The published terms behind the pin are not on record.

    Not a subclass of the generation exceptions on purpose: this is not a
    per-item failure state, it is the ENABLEMENT gate. Its correct effect is that
    the flag does not turn on, not that a question fails.
    """


# ---------------------------------------------------------------------------
# 6.5 — the worker's per-item budget
# ---------------------------------------------------------------------------


class PresupuestoDeItem:
    """A wall-clock bound on processing ONE queued item.

    Monotonic, because it measures elapsed processing and a clock adjustment
    mid-item must not extend or collapse it. Started when the worker picks the
    item up — under amendment A3 nobody is waiting on a socket while it runs, so
    this is a budget rather than a user-facing deadline.
    """

    def __init__(self, segundos: float, reloj: Callable[[], float] | None = None) -> None:
        self._reloj = reloj or time.monotonic
        self._segundos = segundos
        self._inicio = self._reloj()

    def restante(self) -> float:
        return self._segundos - (self._reloj() - self._inicio)

    def vencido(self) -> bool:
        return self.restante() <= 0

    def exigir_vigente(self) -> None:
        if self.vencido():
            raise PresupuestoAgotado(
                f"the item budget of {self._segundos:.1f}s is spent. The item ends "
                "in generacion_fallida, which is the honest state for 'grounded "
                "context existed and no certified answer was produced'."
            )


# ---------------------------------------------------------------------------
# 6.7 — the terms gate
# ---------------------------------------------------------------------------

#: Evidence fields. A record nobody can audit is a claim, not a verification, so
#: each of these is required and its absence refuses.
EVIDENCIA_REQUERIDA = ("verificado_el", "verificado_por", "fuente_url", "sha256_terminos")

#: The upper bound on a retention window that still counts as BOUNDED. Three
#: years, and the number is arguable — which is why it is a named constant and an
#: overridable argument rather than a literal buried in a comparison.
#:
#: The point is that "bounded" was previously satisfied by any non-negative
#: integer, so `retencion_dias: 36500` passed the gate. A hundred-year retention
#: of the questions a CD member asks about their own consorcio is not a retention
#: term with a large number in it; it is indefinite retention written in days,
#: and reading it as bounded is exactly the pretending this gate exists to
#: prevent (bounded correction, 2026-08-24).
RETENCION_MAX_DIAS = 365 * 3


def cargar_terminos(path: Path | None = None) -> Mapping[str, Any] | None:
    """Read the terms record, or `None` when there is not one.

    A missing file is not an error here and IS a refusal one line later: keeping
    the two apart is what lets the gate say "nobody recorded anything" rather
    than crashing with a traceback about a path.
    """
    destino = path or TERMINOS_PATH
    if not destino.exists():
        return None
    crudo = yaml.safe_load(destino.read_text(encoding="utf-8"))
    return crudo if isinstance(crudo, Mapping) else None


def verificar_terminos(
    registro: Mapping[str, Any] | None,
    *,
    modelo: str,
    pool: str,
    retencion_max_dias: int = RETENCION_MAX_DIAS,
) -> None:
    """Refuse unless the record verifiably covers THIS pin. Fail-closed.

    Task 6.7 is a blocking pre-enablement gate: without (a) the exact model id as
    the pool exposes it and (b) published no-training-on-input plus a bounded
    retention window, the flag is not enabled. This function is that gate; the
    reading of the terms is the owner's act and lands in the record.

    `retencion_max_dias` is where "bounded" stops being a type check: beyond it
    the window is indefinite retention written in days, and the record refuses.
    """
    if registro is None:
        raise TerminosNoVerificados(
            f"no terms record at {TERMINOS_PATH}. The pin permits public law text "
            "and the question to leave the box; without the provider's published "
            "no-training and retention terms on file, nothing authorises that."
        )
    if registro.get("verificado") is not True:
        raise TerminosNoVerificados(
            "the terms record is marked unverified. Nobody has read the provider's "
            "published terms yet, so the flag stays off (task 6.7)."
        )
    if registro.get("modelo_id") != modelo:
        raise TerminosNoVerificados(
            f"the record covers {registro.get('modelo_id')!r} and the pin is "
            f"{modelo!r}. Terms verified for one route say nothing about another."
        )
    if registro.get("pool") != pool:
        raise TerminosNoVerificados(
            f"the record covers pool {registro.get('pool')!r} and the pin routes "
            f"through {pool!r}. The same model id behind a different pool is a "
            "different operator, different terms and different retention."
        )
    if registro.get("no_entrenamiento") is not True:
        raise TerminosNoVerificados(
            "the provider does not publish no-training-on-input. It is ineligible "
            "regardless of price or latency: the ratified amendment permits the "
            "question to leave the box, not to become training data."
        )
    retencion = registro.get("retencion_dias")
    if not isinstance(retencion, int) or isinstance(retencion, bool) or retencion < 0:
        raise TerminosNoVerificados(
            f"retencion_dias={retencion!r} is not a bounded window. 'They keep it "
            "for a while' is not a retention term. (`True` is not 30 days either: "
            "a bool is an int in Python and would otherwise read as 1.)"
        )
    if retencion > retencion_max_dias:
        raise TerminosNoVerificados(
            f"retencion_dias={retencion} exceeds the {retencion_max_dias}-day "
            "ceiling on what still counts as a BOUNDED window. A retention this "
            "long is indefinite retention written in days, and the questions a CD "
            "member asks about their own consorcio are not archive material for "
            "the provider."
        )
    faltantes = [c for c in EVIDENCIA_REQUERIDA if not registro.get(c)]
    if faltantes:
        raise TerminosNoVerificados(
            f"the record is missing its evidence: {', '.join(faltantes)}. A record "
            "nobody can audit is a claim, not a verification."
        )


# ---------------------------------------------------------------------------
# 6.1 — the adapter
# ---------------------------------------------------------------------------


class PuenteGenerador:
    """A `Generador` that reaches the pinned model through the bridge gateway.

    Built through `conectar_puente`, never directly, so that a misconfigured pin
    fails at wiring time and so that the transport is injectable — the whole
    failure-translation table below is exercised in tests with the socket closed.
    """

    #: A real model wrote the text. The serving gate and the eval publish gate
    #: refuse a synthetic generator; this one is exactly what they exist to admit.
    sintetico = False

    def __init__(
        self,
        cliente: httpx.Client,
        *,
        modelo: str,
        pool: str,
        timeout_s: float,
        medidor: MedidorDeGasto | None = None,
        presupuesto: PresupuestoDeItem | None = None,
    ) -> None:
        self._cliente = cliente
        self.model_id = modelo
        self.pool = pool
        self._timeout_s = timeout_s
        self._medidor = medidor
        self._presupuesto = presupuesto

    def timeout_efectivo(self) -> float:
        """The smaller of the attempt timeout and what is left of the item.

        20 s per attempt against 4 s of remaining item budget is a 4 s attempt,
        or the item budget is decorative: the attempt would run past it and the
        budget would only be noticed afterwards, having already been exceeded.
        """
        if self._presupuesto is None:
            return self._timeout_s
        return max(0.0, min(self._timeout_s, self._presupuesto.restante()))

    def generar(self, prompt: str, *, max_tokens: int) -> SalidaProveedor:
        # Order matters and is the fail-closed order: budget, then ceiling, then
        # the socket. A request that leaves before the ceiling is checked has
        # already been billed.
        if self._presupuesto is not None:
            self._presupuesto.exigir_vigente()
        if self._medidor is not None:
            self._medidor.cobrar_intento()

        cuerpo = {
            "provider": self.pool,
            "model": self.model_id,
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
        try:
            respuesta = self._cliente.post(
                RUTA_GENERAR, json=cuerpo, timeout=self.timeout_efectivo()
            )
        except httpx.TimeoutException as agotado:
            raise GeneracionTransporte(f"provider attempt timed out: {agotado}") from agotado
        except httpx.HTTPError as fallo:
            raise GeneracionTransporte(f"provider unreachable: {fallo}") from fallo

        self._traducir_estado(respuesta)
        return self._leer(respuesta)

    @staticmethod
    def _traducir_estado(respuesta: httpx.Response) -> None:
        """Map the status code onto the exception whose STATE is correct.

        The split that matters: 401/403/429 are `GeneracionNoDisponible` and not
        transport. A 429 retried inside the transport budget is a retry storm
        against a provider that just said stop, and a 401 does not fix itself on
        the second attempt — retrying either one burns the item's budget to
        arrive at the same answer, and burns spend doing it.
        """
        codigo = respuesta.status_code
        if codigo == 200:
            return
        detalle = respuesta.text[:200]
        if codigo in (401, 403):
            raise GeneracionNoDisponible(f"provider rejected the credential (HTTP {codigo})")
        if codigo == 429:
            raise GeneracionNoDisponible(f"provider rate-limited the pool (HTTP 429): {detalle}")
        raise GeneracionTransporte(f"HTTP {codigo} from {RUTA_GENERAR}: {detalle}")

    @staticmethod
    def _leer(respuesta: httpx.Response) -> SalidaProveedor:
        """Read a body the gateway ALREADY answered 200 for.

        Every refusal below is `GeneracionNoDisponible`, and that is a bounded
        correction against the first cut (2026-08-24), which raised
        `GeneracionTransporte` here. A 200 whose body this adapter cannot read is
        a CONTRACT MISMATCH — a gateway configured to a shape we do not speak, or
        a pool whose response envelope changed — and not an outage. Classifying
        it as transport meant the request was retried inside the transport budget
        and BILLED TWICE to arrive at exactly the same unreadable body, then
        reported to the operator as a network fault pointing at a healthy socket.
        A misconfiguration does not fix itself on the second attempt.
        """
        try:
            cuerpo = respuesta.json()
        except ValueError as no_json:
            raise GeneracionNoDisponible(
                f"{RUTA_GENERAR} answered 200 with a non-JSON body. That is a "
                "gateway contract mismatch, not an outage: retrying re-bills the "
                "attempt to receive the same body again."
            ) from no_json
        if not isinstance(cuerpo, Mapping):
            raise GeneracionNoDisponible(
                f"{RUTA_GENERAR} answered 200 with {cuerpo!r}, which is not an "
                "object. Contract mismatch, not an outage."
            )

        texto = next(
            (cuerpo[c] for c in CAMPOS_TEXTO if isinstance(cuerpo.get(c), str) and cuerpo[c]),
            None,
        )
        if texto is None:
            raise GeneracionNoDisponible(
                f"{RUTA_GENERAR} answered 200 with no text under any of "
                f"{CAMPOS_TEXTO}. An empty answer served as an answer is worse "
                "than a failed item: it cites nothing and reads like a finding. "
                "Contract mismatch, so it refuses instead of retrying."
            )

        corte = next((cuerpo[c] for c in CAMPOS_CORTE if isinstance(cuerpo.get(c), str)), None)
        if corte in CORTE_POR_LONGITUD:
            return SalidaProveedor(texto=texto, truncado=True)
        if corte in CORTE_COMPLETO:
            return SalidaProveedor(texto=texto, truncado=False)
        # Unreadable stop reason. Reading it as "complete" would serve a possibly
        # truncated legal answer as a whole one, and the design forbids exactly
        # that distinction being re-derived by sniffing the prose. Refusing
        # without a retry is the other half: a provider that reports a stop
        # reason this adapter does not know reports the same one every time.
        raise GeneracionNoDisponible(
            f"{RUTA_GENERAR} reported stop reason {corte!r}, which cannot be read "
            "as complete or truncated. Assuming complete would serve a cut-off "
            "answer as a finished one; retrying would pay twice for the same "
            "unreadable report."
        )

    # -- lifetime ---------------------------------------------------------
    def close(self) -> None:
        """Release the underlying connection pool.

        `conectar_puente` OPENS an `httpx.Client`, and an adapter built per
        queued item without this leaks a pool per item until the worker's
        file-descriptor limit notices. Idempotent, because a worker that fails an
        item in a `finally` must be able to close a client the happy path already
        closed.
        """
        self._cliente.close()

    def __enter__(self) -> PuenteGenerador:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.close()


def conectar_puente(
    url: str,
    *,
    modelo: str,
    pool: str,
    api_key: str,
    timeout_s: float,
    medidor: MedidorDeGasto | None = None,
    presupuesto: PresupuestoDeItem | None = None,
    transporte: httpx.BaseTransport | None = None,
) -> PuenteGenerador:
    """Build the adapter, refusing a configuration that cannot work.

    `transporte` exists so every refusal above is testable without a gateway.
    Nothing in production passes it.

    **Lifetime — the caller owns it.** This function OPENS an `httpx.Client` and
    hands it over; the returned adapter must be closed, and it is a context
    manager so the ordinary way is `with conectar_puente(...) as puente:`. The
    per-item budget (`presupuesto`) is per ITEM, so the worker builds one adapter
    per queued item and closing it is not optional at that rate: an unclosed pool
    per item is a descriptor leak that shows up as a worker that stops answering
    after N items and blames the provider. A long-lived adapter shared across
    items is legitimate ONLY without a `presupuesto`, since a budget started when
    the adapter was built would bound the wrong item.
    """
    if not modelo:
        raise ProveedorMalConfigurado(
            "conocimiento_modelo is empty. The pin lives in config precisely so it "
            "can be changed without a code edit; an empty one is not a pin."
        )
    if not pool:
        raise ProveedorMalConfigurado("conocimiento_pool is empty: no route to the model.")
    if not api_key:
        raise ProveedorMalConfigurado(
            "conocimiento_proveedor_api_key is empty. Fail-closed at wiring time: a "
            "credential discovered missing on the first question is a question that "
            "dies for a reason nobody can see from the answer."
        )
    cliente = httpx.Client(
        base_url=url,
        timeout=timeout_s,
        transport=transporte,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return PuenteGenerador(
        cliente,
        modelo=modelo,
        pool=pool,
        timeout_s=timeout_s,
        medidor=medidor,
        presupuesto=presupuesto,
    )
