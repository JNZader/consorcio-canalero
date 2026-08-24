"""The mailbox's HTTP surface (U7, tasks 7.1-7.6), mounted at `/api/v2/conocimiento`.

Under amendment A3 this surface does NOT answer. `POST /preguntas` enqueues and
returns an id plus `pendiente`; `GET /preguntas/{id}` and `GET /preguntas` are the
status and listing surfaces; `GET /estado` is the admin diagnostic where a
permanently-down worker becomes visible. Everything that needs a GPU or a hosted
call happens in `trabajador.py`, off the request path.

**Dependency order is load-bearing** (`design.md:747-754`, minus the in-flight
slot the queue replaced):

    enforce_conocimiento_qa_enabled
      -> require_admin
      -> enforce_body_limit
      -> enforce_qa_rate_limit
      -> enforce_qa_quota

The flag AND is first so a deployment that is off answers before the body is
read, before the limiter is consulted, before a quota slot is spent and before a
row is written. The quota runs AFTER `require_admin` precisely so a user id
exists to key on — the ficha's `_client_ip` keying is the wrong precedent behind
an authenticated route and a proxy (`design.md:751-754`).

**Why `/estado` does not take the full AND.** It takes the flag and
`require_admin` and then REPORTS the three availability facts instead of
enforcing them. A3 moved the "worker is down" fault off the per-question path and
onto this endpoint; an endpoint that 503s whenever the sidecar is down would be
unreachable during exactly the outage it exists to describe.
"""

from __future__ import annotations

import datetime
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from app.config import settings
from app.core.rate_limit import DistributedRateLimiter
from app.db.session import get_db
from app.domains.conocimiento import buzon, repository
from app.domains.conocimiento.costos import AlmacenEnMemoria, CuotaDiaria
from app.domains.conocimiento.embed_sidecar import SidecarNoDisponible, conectar_sidecar
from app.domains.conocimiento.generacion import GeneracionNoDisponible
from app.domains.conocimiento.proveedores import (
    TerminosNoVerificados,
    cargar_terminos,
    verificar_terminos,
)
from app.domains.conocimiento.schemas import (
    ConsultaEncolada,
    EstadoBuzon,
    ItemBuzon,
    PreguntaEntrada,
    RespuestaConocimiento,
)

router = APIRouter(prefix="/conocimiento", tags=["conocimiento"])

#: The one 503 error code the enablement gate speaks, with the CAUSE naming which
#: of the ANDed facts is false. One code and a cause, rather than four codes: the
#: caller's handling is identical (the deployment is not ready) and the operator's
#: is not (they need the specific knob).
ERROR_NO_LISTA = "base_de_conocimiento_no_lista"
ERROR_APAGADA = "funcionalidad_no_disponible"

CAUSA_TERMINOS = "terminos_no_verificados"
CAUSA_CREDENCIAL = "credencial_ausente"
CAUSA_EMBEDDER = "embedder_no_listo"


def _no_lista(causa: str, detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"error": ERROR_NO_LISTA, "causa": causa, "detalle": detalle},
    )


# ---------------------------------------------------------------------------
# The cached `/ready` probe
# ---------------------------------------------------------------------------


class SondaSidecar:
    """A `/ready` result with a short TTL, so the gate costs nothing per request.

    It caches the REFUSAL as well as the success, and that is the point: a
    sidecar that is down would otherwise be probed once per request, turning a
    readiness gate into a retry storm against a container that is already
    struggling. The TTL is seconds, so the gate still flips within seconds of the
    container dying (`design.md:729-733`).
    """

    def __init__(self, ttl_s: float | None = None) -> None:
        self._ttl_s = ttl_s
        self._lock = threading.Lock()
        self._vencimiento = 0.0
        self._fallo: SidecarNoDisponible | None = None
        self._probado = False

    @property
    def ttl_s(self) -> float:
        return settings.conocimiento_ready_ttl_s if self._ttl_s is None else self._ttl_s

    def _probar(self) -> SidecarNoDisponible | None:
        if not settings.conocimiento_embed_url:
            return SidecarNoDisponible(
                CAUSA_EMBEDDER,
                "conocimiento_embed_url is unset. There is no sidecar to be ready.",
            )
        try:
            # Closed immediately: this probe wants the `/ready` ANSWER, not a
            # connection pool, and it runs once per TTL forever.
            with conectar_sidecar(
                settings.conocimiento_embed_url,
                timeout=settings.conocimiento_embed_timeout_s,
            ):
                return None
        except SidecarNoDisponible as exc:
            return exc

    def exigir_listo(self, *, ahora: float | None = None) -> None:
        """Raise `SidecarNoDisponible` unless the sidecar answered `/ready`."""
        import time

        momento = time.monotonic() if ahora is None else ahora
        with self._lock:
            if not self._probado or momento >= self._vencimiento:
                self._fallo = self._probar()
                self._vencimiento = momento + self.ttl_s
                self._probado = True
            fallo = self._fallo
        if fallo is not None:
            raise fallo

    def invalidar(self) -> None:
        with self._lock:
            self._probado = False


_sonda = SondaSidecar()


def get_sonda_sidecar() -> SondaSidecar:
    """Overridable seam: the tests replace the probe, never the network."""
    return _sonda


# ---------------------------------------------------------------------------
# Task 7.2 + 7.3 — THE FIRST DEPENDENCY: the flag ANDed with three facts
# ---------------------------------------------------------------------------


def enforce_conocimiento_flag() -> None:
    """The kill switch alone. 503 while the surface is switched off.

    Split out from the AND below so `/estado` can be reachable while a
    dependency is down without being reachable on a deployment that never turned
    the surface on.
    """
    if not settings.conocimiento_qa_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": ERROR_APAGADA,
                "causa": "conocimiento_qa_enabled",
                "detalle": (
                    "the conocimiento Q&A surface is switched off. The default "
                    "state of a deployment with no flag set is OFF (G4)."
                ),
            },
        )


def enforce_conocimiento_qa_enabled(
    sonda: SondaSidecar = Depends(get_sonda_sidecar),
) -> None:
    """The flag ANDed with THREE facts, checked in this order. The FIRST dependency.

    A surface that is "on" and fails on every request is not on
    (`design.md:725-742`), so the flag alone was never the gate. The order is not
    cosmetic:

    0. **The provider TERMS record** covers this exact `(modelo, pool)` pair. It
       is first because it is the only one of the three that governs whether the
       public law text and a CD member's verbatim question may leave the box at
       all. U6 built the whole mechanism — the checked-in record, the six
       refusals, the test proving the shipped record refuses — and gave it NO
       CALLER on the serving path; with the flag flipped, the surface would have
       answered questions against a record marked `verificado: false`. This line
       is that caller (task 7.2, amended 2026-08-24).
    1. **The credential is present** — no provider key configured is a 503, not a
       500 from the first hosted call.
    2. **The sidecar is ready** — `/ready` true, through the cached probe.

    All three are checked PER REQUEST against loaded state rather than once at
    import, so flipping the terms record is a deploy and never a code change —
    the same reason the pin lives in config.

    503 and not 500 throughout: an unverified record, a missing key and a dead
    sidecar are all "this deployment is not ready", which is a different thing
    from "this deployment is broken" and sends the operator somewhere different.

    Note what is NOT here: reranker availability. Task 7.3's per-question `503
    reranker_no_disponible` was REPLACED by the queue state (A3). A GPU that is
    not currently up is the normal case, not an outage; items stay `pendiente`
    and a permanently misconfigured worker surfaces on `GET /estado`.
    """
    enforce_conocimiento_flag()

    try:
        verificar_terminos(
            cargar_terminos(),
            modelo=settings.conocimiento_modelo,
            pool=settings.conocimiento_pool,
        )
    except TerminosNoVerificados as exc:
        raise _no_lista(CAUSA_TERMINOS, str(exc)) from exc

    if not settings.conocimiento_proveedor_api_key:
        raise _no_lista(
            CAUSA_CREDENCIAL,
            "conocimiento_proveedor_api_key is unset. The surface would fail on "
            "the first hosted call with a 500 that names nothing.",
        )

    try:
        sonda.exigir_listo()
    except SidecarNoDisponible as exc:
        raise _no_lista(CAUSA_EMBEDDER, str(exc)) from exc


# ---------------------------------------------------------------------------
# Auth, body, rate limit, quota
# ---------------------------------------------------------------------------


def _require_admin():
    """House lazy-import shim (`settings/router.py:34-37`), for the circular dep.

    `require_admin` is the V1 APPROXIMATION of the Comisión Directiva role. The
    real role is follow-up F3 and is out of this change's scope; recorded here so
    the approximation is visible at the surface that relies on it.
    """
    from app.auth import require_admin

    return require_admin


async def enforce_body_limit(request: Request) -> None:
    """413 before parsing, on the `enforce_body_limit` precedent (JDB-007).

    Bounds the BYTES. `buzon.PREGUNTA_MAX_CHARS` bounds the text, and the two are
    different limits: a megabyte of valid UTF-8 is one question, and a 2000-char
    question inside a 1 MB body is a megabyte this process still had to read.
    """
    maximo = settings.conocimiento_max_body_bytes
    declarado = request.headers.get("content-length")
    if declarado is not None:
        try:
            if int(declarado) > maximo:
                raise _cuerpo_excedido(maximo)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "content_length_invalido"},
            ) from None

    if hasattr(request, "_body"):
        return

    trozos: list[bytes] = []
    leido = 0
    try:
        async for trozo in request.stream():
            leido += len(trozo)
            if leido > maximo:
                raise _cuerpo_excedido(maximo)
            trozos.append(trozo)
    except ClientDisconnect:
        # Same reason as the ficha's guard: letting this reach the generic
        # handler ships a Sentry event and three ERROR records per hit, and this
        # dependency runs before the limiter by design.
        raise HTTPException(
            status_code=499,  # nginx's client-closed-request; Starlette has no name for it
            detail={"error": "cliente_desconectado"},
        ) from None
    request._body = b"".join(trozos)


def _cuerpo_excedido(maximo: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail={"error": "cuerpo_excedido", "maximo_bytes": maximo},
    )


_limiter: DistributedRateLimiter | None = None


def get_conocimiento_rate_limiter() -> DistributedRateLimiter:
    """Own limiter instance, own Redis key namespace.

    `ratelimit:conocimiento:` and not the shared one: a shared limiter would let
    a burst of legal questions throttle the operator geo routes, which have
    nothing to do with this surface's cost (`design.md:747-750`).
    """
    global _limiter
    if _limiter is None:
        _limiter = DistributedRateLimiter(
            redis_url=settings.redis_url,
            max_requests=settings.conocimiento_rate_limit_requests,
            window_seconds=settings.conocimiento_rate_limit_window,
            key_prefix="ratelimit:conocimiento:",
        )
    return _limiter


_almacen_cuota = AlmacenEnMemoria()


def get_almacen_cuota() -> Any:
    """The quota's counter store.

    **Stated rather than implied: this is an IN-PROCESS store.** U6 defined
    `AlmacenDeContadores` as the Redis-shaped seam and shipped only the in-memory
    implementation; building the Redis one is not U7's slice. So with N server
    workers the effective daily quota is N x `conocimiento_quota_diaria_usuario`,
    the same honesty note the ficha limiter carries about its fallback window.
    That is a ceiling that is looser than it reads, and it is written down here
    rather than discovered from a bill — the ceiling that actually bounds spend
    is `MedidorDeGasto`, which refuses on the projection before an attempt is
    issued.
    """
    return _almacen_cuota


async def enforce_qa_rate_limit(
    request: Request,
    usuario: Any = Depends(_require_admin()),
    limiter: DistributedRateLimiter = Depends(get_conocimiento_rate_limiter),
) -> None:
    """Keyed on the authenticated USER ID, never on the client IP.

    Behind a proxy `request.client.host` collapses every admin into one bucket,
    so the ficha's `_client_ip` keying is the wrong precedent for an
    authenticated route (`design.md:751-754`).
    """
    permitido, _restante, reinicia = await limiter.check(f"user:{usuario.id}")
    if not permitido:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "limite_de_tasa", "retry_after": reinicia},
            headers={"Retry-After": str(int(reinicia or 1))},
        )


def enforce_qa_quota(
    usuario: Any = Depends(_require_admin()),
    almacen: Any = Depends(get_almacen_cuota),
) -> None:
    """`conocimiento_quota_diaria_usuario` questions per user per Cordoba day.

    UNSET REFUSES. The number is blocked on the cost re-derivation against the
    `deepseek-v4-flash` pin (amendment A6), and a surface that served an
    unbounded number of billed questions while the ceiling was "not decided yet"
    is the failure this fail-closed default exists to prevent.

    Charged at SUBMIT and not at processing: the quota bounds what a user may
    ASK, and charging it in the worker would let one user fill the queue and only
    discover the ceiling an hour later, having already displaced everyone else's
    items.
    """
    cuota = CuotaDiaria(almacen, limite=settings.conocimiento_quota_diaria_usuario)
    try:
        cuota.consumir(str(usuario.id))
    except GeneracionNoDisponible as exc:
        # Every quota refusal (`CuotaAgotada`, `CuotaNoConfigurada`) is a subclass
        # of this, by U6's design: they are dependency/ceiling facts, never "no
        # applicable norm".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": ERROR_NO_LISTA, "causa": type(exc).__name__, "detalle": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# Task 7.1 — the three mailbox routes
# ---------------------------------------------------------------------------


def _a_item(fila: Any) -> ItemBuzon:
    return ItemBuzon(
        id=fila.id,
        pregunta=fila.pregunta,
        estado=fila.estado,
        creada_en=fila.creada_en,
        procesada_en=fila.procesada_en,
        demorado=buzon.esta_demorado(fila, ventana_s=settings.conocimiento_worker_stale_after_s),
        respuesta=(
            RespuestaConocimiento.model_validate(fila.respuesta)
            if fila.respuesta is not None
            else None
        ),
    )


@router.post(
    "/preguntas",
    response_model=ConsultaEncolada,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": PreguntaEntrada.model_json_schema()}},
        }
    },
    dependencies=[
        Depends(enforce_conocimiento_qa_enabled),
        Depends(_require_admin()),
        Depends(enforce_body_limit),
        Depends(enforce_qa_rate_limit),
        Depends(enforce_qa_quota),
    ],
)
async def encolar_pregunta(
    request: Request,
    usuario: Any = Depends(_require_admin()),
    db: Session = Depends(get_db),
) -> ConsultaEncolada:
    """202 with an id and `pendiente`. It never carries an answer (A3).

    202 and not 201: the item was ACCEPTED for processing, and the thing the
    caller asked for does not exist yet. A 201 would name the question as the
    created resource, which is true of the row and false of the intent.

    **Why the body is parsed HERE and not declared as a typed parameter.**
    FastAPI reads and deserializes a declared body BEFORE it solves the route's
    dependencies, so with `cuerpo: PreguntaEntrada` in the signature the whole
    request would already be in memory by the time `enforce_body_limit` ran —
    "413 before parsing" would be a comment rather than a guard, and a chunked
    body with no `Content-Length` would sail past the only check that could stop
    it. This is the same reason `router_ficha.py` reads its body by hand
    (`_cuerpo_crudo`). The schema is still published through `openapi_extra`, so
    the contract is not lost with the parameter.
    """
    try:
        cuerpo = PreguntaEntrada.model_validate_json(await request.body() or b"null")
    except (ValidationError, ValueError) as exc:
        # The message is summarized rather than echoed: pydantic's error objects
        # carry the offending INPUT in `ctx`, and echoing a rejected body back is
        # how a malformed-input handler becomes a reflection surface.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "cuerpo_invalido",
                "detalle": "the body must be a JSON object with a single `pregunta` string",
            },
        ) from exc

    try:
        item = buzon.encolar(db, usuario_id=usuario.id, pregunta=cuerpo.pregunta)
    except buzon.PreguntaInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "pregunta_invalida", "detalle": str(exc)},
        ) from exc
    db.commit()
    return ConsultaEncolada(id=item.id, creada_en=item.creada_en)


@router.get(
    "/preguntas",
    response_model=list[ItemBuzon],
    dependencies=[Depends(enforce_conocimiento_qa_enabled), Depends(_require_admin())],
)
def listar_preguntas(
    usuario: Any = Depends(_require_admin()),
    db: Session = Depends(get_db),
    limite: int = 50,
) -> list[ItemBuzon]:
    """The requester's own bandeja, newest first."""
    return [_a_item(fila) for fila in buzon.listar(db, usuario_id=usuario.id, limite=limite)]


@router.get(
    "/preguntas/{consulta_id}",
    response_model=ItemBuzon,
    dependencies=[Depends(enforce_conocimiento_qa_enabled), Depends(_require_admin())],
)
def ver_pregunta(
    consulta_id: uuid.UUID,
    usuario: Any = Depends(_require_admin()),
    db: Session = Depends(get_db),
) -> ItemBuzon:
    """One item, scoped to its requester.

    404 and not 403 for another admin's item: a 403 confirms the id exists, and
    the row holds the verbatim question a specific person asked.
    """
    fila = buzon.obtener(db, consulta_id, usuario_id=usuario.id)
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "consulta_no_encontrada"},
        )
    return _a_item(fila)


# ---------------------------------------------------------------------------
# Task 7.6 — the diagnostic
# ---------------------------------------------------------------------------


@router.get(
    "/estado",
    response_model=EstadoBuzon,
    dependencies=[Depends(enforce_conocimiento_flag), Depends(_require_admin())],
)
def estado_del_buzon(
    db: Session = Depends(get_db),
    sonda: SondaSidecar = Depends(get_sonda_sidecar),
) -> EstadoBuzon:
    """Snapshot provenance, the three enablement facts, and the QUEUE.

    The queue block is what A3 added and what makes this endpoint load-bearing
    rather than decorative: with the per-question `503 reranker_no_disponible`
    replaced by items staying `pendiente`, this is the ONLY place a permanently
    down worker is visible. Depth alone does not say it — a batch worker is
    supposed to have a backlog — so it is reported next to the oldest pending
    item and the last successful run, which together separate "between batches"
    from "down since yesterday".
    """
    corpus_sha = repository.corpus_activo(db)
    procedencia = repository.leer_procedencia(db, corpus_sha) if corpus_sha else None

    terminos_ok: bool
    causa: str | None = None
    try:
        verificar_terminos(
            cargar_terminos(),
            modelo=settings.conocimiento_modelo,
            pool=settings.conocimiento_pool,
        )
        terminos_ok = True
    except TerminosNoVerificados as exc:
        terminos_ok = False
        causa = f"{CAUSA_TERMINOS}: {exc}"

    embedder_ok: bool
    try:
        sonda.exigir_listo()
        embedder_ok = True
    except SidecarNoDisponible as exc:
        embedder_ok = False
        causa = causa or f"{CAUSA_EMBEDDER}: {exc}"

    credencial_ok = bool(settings.conocimiento_proveedor_api_key)
    if not credencial_ok:
        causa = causa or f"{CAUSA_CREDENCIAL}: conocimiento_proveedor_api_key is unset"

    mas_antiguo = buzon.mas_antiguo_pendiente(db)
    ventana = settings.conocimiento_worker_stale_after_s
    demorado = False
    if mas_antiguo is not None and ventana > 0:
        referencia = datetime.datetime.now(datetime.timezone.utc)
        creada = (
            mas_antiguo
            if mas_antiguo.tzinfo is not None
            else mas_antiguo.replace(tzinfo=datetime.timezone.utc)
        )
        demorado = (referencia - creada).total_seconds() > ventana

    return EstadoBuzon(
        corpus_sha=corpus_sha,
        embedding_modelo=procedencia.modelo if procedencia else None,
        embedding_sintetico=procedencia.sintetico if procedencia else None,
        embeddings_loaded_at=procedencia.loaded_at if procedencia else None,
        terminos_verificados=terminos_ok,
        credencial_presente=credencial_ok,
        embedder_listo=embedder_ok,
        causa_no_listo=causa,
        profundidad_cola=buzon.profundidad(db),
        mas_antiguo_pendiente=mas_antiguo,
        ultima_corrida_worker=buzon.ultima_corrida(db),
        worker_demorado=demorado,
    )
