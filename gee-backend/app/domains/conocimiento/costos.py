"""U6: the two ceilings that bound a hosted-generation surface.

A rate limiter caps *rate*, not *total* (`design.md:458-470`). Two controls sit
underneath it and both are **fail-CLOSED**: when a ceiling is hit the item ends
in `no_disponible` with the cause named, and never in a cheaper or an uncited
answer.

| Control | Keyed on | Why that key |
|---|---|---|
| Per-user daily quota | the **authenticated user id** | `router_ficha.py:130-131` keys on `request.client.host`, which is right for a public surface and wrong here: this route is behind `require_admin`, the deployment sits behind a proxy, and every admin arriving through it would collapse into one bucket. One CD member would exhaust the quota of all of them and the audit trail would say "the proxy did it". Trusting a forwarded-for header would be worse: it is caller-controlled |
| Global spend ceiling | the deployment | a runaway is a deployment fact |

**"Daily" is a calendar day in `America/Argentina/Cordoba`**, not a rolling 24 h
window (`design.md:471-481`). The reason is the user rather than the
implementation: a CD member who exhausts the quota can be told "se renueva a la
medianoche", which a rolling window cannot state without naming the timestamp of
their first call. The stated cost of the choice: a burst across a midnight
boundary, up to two quotas in a few minutes — bounded, visible in the spend
ceiling, and cheaper than the alternative's opacity.

**The spend ceiling keeps its rolling window**, because a runaway does not
respect midnight. Its granularity is honest and stated: hour buckets summed over
`ventana_h`, so the effective window is between `ventana_h - 1` and `ventana_h`
hours. Sizing a runaway bound to the minute would need a timestamp set per
attempt, which buys precision nobody spends.

**Every number here is UNSET at rest.** Amendment A6 leaves
`conocimiento_quota_diaria_usuario`, `conocimiento_spend_ceiling_usd` and the
per-attempt cost blocked on the cost re-derivation against the
`deepseek-v4-flash` pin (the Claude-class figures in the design body are stale by
construction, amendment A2). Unset therefore REFUSES: an unset ceiling that
admits everything is not a ceiling, it is a ceiling somebody deleted while it
still looked configured.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Callable, Iterable, Protocol
from zoneinfo import ZoneInfo

from app.domains.conocimiento.generacion import GeneracionNoDisponible

#: The consorcio's civil time. Not UTC: `utcnow().date()` names the wrong day for
#: three hours out of every twenty-four here (UTC-3), which is precisely the
#: window in which a CD member works late.
ZONA_CUOTA = ZoneInfo("America/Argentina/Cordoba")

#: Key namespaces. They cross a process boundary (Redis) and appear in operator
#: debugging, so they are constants rather than f-string literals at call sites.
CLAVE_CUOTA = "quota:conocimiento"
CLAVE_GASTO = "spend:conocimiento"

Reloj = Callable[[], datetime]


def _ahora() -> datetime:
    return datetime.now(ZONA_CUOTA)


# ---------------------------------------------------------------------------
# Refusals — every one of them is a `no_disponible` with a name
# ---------------------------------------------------------------------------


class _Refusal(GeneracionNoDisponible):
    """A ceiling, named. Subclasses `GeneracionNoDisponible` on purpose: the
    generation path already ends that exception in `no_disponible`, and a ceiling
    IS a dependency fact rather than a generation fact (`design.md:549`)."""

    causa = "no_disponible"

    def __init__(self, detalle: str) -> None:
        super().__init__(f"{self.causa}: {detalle}")
        self.detalle = detalle


class CuotaAgotada(_Refusal):
    causa = "cuota_agotada"


class CuotaNoConfigurada(_Refusal):
    causa = "cuota_no_configurada"


class TechoDeGasto(_Refusal):
    causa = "techo_de_gasto"


class TechoNoConfigurado(_Refusal):
    causa = "techo_no_configurado"


class VentanaNoConfigurada(_Refusal):
    """`conocimiento_spend_window_h` is not a usable window.

    Its own cause rather than a `TechoNoConfigurado`, because the operator action
    differs: the ceiling is a number nobody has derived yet, and this is a number
    somebody set wrong.
    """

    causa = "ventana_no_configurada"


# ---------------------------------------------------------------------------
# The counter store
# ---------------------------------------------------------------------------


class AlmacenDeContadores(Protocol):
    """What a quota and a meter need from Redis, and nothing more.

    Narrow on purpose: the whole surface is "add to a keyed number that expires".
    Keeping it this small is what lets the ceilings be tested without a Redis and
    without either mechanism growing a second, untested code path for the
    degraded case.
    """

    def incrementar(self, clave: str, monto: float, ttl_s: int) -> float: ...

    def leer(self, claves: Iterable[str]) -> float: ...


class AlmacenEnMemoria:
    """A per-process store. Test double, and the honest degraded mode.

    Stated rather than hidden: with `app/server.py` running 2 uvicorn workers,
    an in-memory quota is per PROCESS, so the box-wide bound doubles. The
    worker-side ceilings that matter run in ONE worker process, which is why this
    is a usable degraded mode there and would not be one on the HTTP surface.
    """

    def __init__(self, reloj: Callable[[], float] | None = None) -> None:
        self._valores: dict[str, tuple[float, float]] = {}
        self._reloj = reloj
        self._lock = threading.Lock()

    def _t(self) -> float:
        if self._reloj is not None:
            return self._reloj()
        return _ahora().timestamp()

    def _purgar(self, ahora: float) -> None:
        for clave, (_, vence) in list(self._valores.items()):
            if vence <= ahora:
                del self._valores[clave]

    def incrementar(self, clave: str, monto: float, ttl_s: int) -> float:
        with self._lock:
            ahora = self._t()
            self._purgar(ahora)
            actual, _ = self._valores.get(clave, (0.0, 0.0))
            nuevo = actual + monto
            self._valores[clave] = (nuevo, ahora + ttl_s)
            return nuevo

    def leer(self, claves: Iterable[str]) -> float:
        with self._lock:
            ahora = self._t()
            self._purgar(ahora)
            return sum(self._valores.get(c, (0.0, 0.0))[0] for c in claves)

    # -- test/diagnostic surface ------------------------------------------
    def claves(self) -> list[str]:
        with self._lock:
            self._purgar(self._t())
            return list(self._valores)

    def ttl(self, clave: str) -> float:
        with self._lock:
            _, vence = self._valores.get(clave, (0.0, 0.0))
            return vence - self._t()


# ---------------------------------------------------------------------------
# 6.3 — the per-user daily quota
# ---------------------------------------------------------------------------


def segundos_a_medianoche(ahora: datetime) -> int:
    """Seconds from `ahora` to the next local midnight in Cordoba.

    This is the counter's TTL, which is what turns the quota into a single
    integer per user per day rather than a timestamp set (`design.md:475-477`).
    """
    local = ahora.astimezone(ZONA_CUOTA)
    manana = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((manana - local).total_seconds())


class CuotaDiaria:
    """`limite` questions per authenticated user per Cordoba calendar day."""

    def __init__(
        self,
        almacen: AlmacenDeContadores,
        *,
        limite: int,
        reloj: Reloj | None = None,
    ) -> None:
        self._almacen = almacen
        self._limite = limite
        self._reloj = reloj or _ahora

    def clave(self, user_id: str) -> str:
        dia = self._reloj().astimezone(ZONA_CUOTA).strftime("%Y-%m-%d")
        return f"{CLAVE_CUOTA}:{user_id}:{dia}"

    def consumir(self, user_id: str) -> int:
        """Charge one question to `user_id`, or refuse with the cause named."""
        if self._limite <= 0:
            raise CuotaNoConfigurada(
                "conocimiento_quota_diaria_usuario is unset. It is blocked on the "
                "cost re-derivation against the deepseek-v4-flash pin (amendment "
                "A6); until it is set, this surface refuses rather than serving "
                "an unbounded number of billed questions."
            )
        ahora = self._reloj()
        usado = self._almacen.incrementar(self.clave(user_id), 1.0, segundos_a_medianoche(ahora))
        if usado > self._limite:
            raise CuotaAgotada(
                f"{user_id} used {int(usado) - 1}/{self._limite} questions today. "
                "The quota renews at midnight in Cordoba."
            )
        return int(usado)


# ---------------------------------------------------------------------------
# 6.4 — the spend meter, charged per ATTEMPT
# ---------------------------------------------------------------------------


class MedidorDeGasto:
    """Charges one provider ATTEMPT and refuses once the window is spent.

    Per attempt rather than per item, and the difference is the whole point
    (`design.md:666-673`): one item can issue up to four provider calls (two
    generations, each with a transport budget of two), all of them billed —
    a transport retry is charged even when the response never arrives intact. A
    meter that charged per item would under-count by 4x exactly in the degraded
    conditions it exists to bound.
    """

    def __init__(
        self,
        almacen: AlmacenDeContadores,
        *,
        techo_usd: float,
        ventana_h: int,
        costo_intento_usd: float,
        reloj: Reloj | None = None,
    ) -> None:
        self._almacen = almacen
        self._techo = techo_usd
        # Stored VERBATIM. The first cut wrote `max(1, ventana_h)`, which silently
        # repaired a misconfigured window toward the permissive side: a window of
        # 0 or a negative one became a one-hour window, so a ceiling meant to hold
        # over a day started resetting every hour and the deployment could spend
        # 24x the number the operator thought they had set — with nothing
        # anywhere saying so (bounded correction, 2026-08-24). An unusable window
        # now refuses, like every other unset control in this module.
        self._ventana_h = ventana_h
        self._costo = costo_intento_usd
        self._reloj = reloj or _ahora

    def _claves_de_la_ventana(self) -> list[str]:
        # The choke point for BOTH `gastado()` and `cobrar_intento()`, which is
        # why the window check lives here: a window that refuses on spend but
        # reports USD 0.00 on read would be a diagnostic that lies.
        if self._ventana_h < 1:
            raise VentanaNoConfigurada(
                f"conocimiento_spend_window_h={self._ventana_h} is not a window. "
                "It is not quietly rounded up to 1 h: that would shrink the "
                "ceiling's period without shrinking the ceiling, and let the "
                "deployment spend it again every hour."
            )
        ahora = self._reloj().astimezone(ZONA_CUOTA)
        return [
            f"{CLAVE_GASTO}:{(ahora - timedelta(hours=h)).strftime('%Y-%m-%dT%H')}"
            for h in range(self._ventana_h)
        ]

    def _exigir_configuracion(self) -> None:
        faltantes = []
        if self._techo <= 0:
            faltantes.append(f"conocimiento_spend_ceiling_usd={self._techo!r}")
        if self._costo <= 0:
            faltantes.append(f"conocimiento_costo_intento_usd={self._costo!r}")
        if faltantes:
            raise TechoNoConfigurado(
                f"unset: {', '.join(faltantes)}. Blocked on the cost re-derivation "
                "against the deepseek-v4-flash pin (amendments A2/A6). A "
                "per-attempt cost of 0 never reaches any ceiling, which is a "
                "ceiling that has been deleted while still looking configured."
            )

    def gastado(self) -> float:
        return self._almacen.leer(self._claves_de_la_ventana())

    def cobrar_intento(self) -> float:
        """Charge one attempt BEFORE it is issued, or refuse.

        Charging up front is deliberate: an attempt that times out was still
        processed and still billed, so a meter that charged on success would
        under-count exactly the degraded path.
        """
        self._exigir_configuracion()
        # The ceiling is not EXCEEDED and then noticed: an attempt that would
        # cross it never leaves. Checking "already over" instead would always
        # overshoot by one attempt, and would let a ceiling smaller than a single
        # attempt admit an unbounded first call — which is how a ceiling of USD
        # 0.05 quietly authorises a USD 0.10 spend.
        proyectado = self.gastado() + self._costo
        if proyectado > self._techo:
            raise TechoDeGasto(
                f"USD {self.gastado():.4f} spent in the last {self._ventana_h} h; "
                f"this attempt would reach USD {proyectado:.4f} against a ceiling "
                f"of USD {self._techo:.4f}. The surface refuses; it does not fall "
                "back to a cheaper model or an uncited answer."
            )
        clave = self._claves_de_la_ventana()[0]
        return self._almacen.incrementar(clave, self._costo, self._ventana_h * 3600)
