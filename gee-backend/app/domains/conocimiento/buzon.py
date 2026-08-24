"""The mailbox queue: enqueue, claim, persist, diagnose (U7, amendment A3).

`design.md:1321-1366` replaced the synchronous answerer with an asynchronous
mailbox. This module owns the queue's data operations and nothing else: no HTTP,
no provider, no retrieval. The worker that USES it is `trabajador.py`.

**The claim, and why it deliberately has no `en_proceso` state.**
`reclamar_pendiente` selects the oldest `pendiente` row with `FOR UPDATE SKIP
LOCKED` and returns it still marked `pendiente`. The row lock lives until the
CALLER's transaction ends, and the caller is the worker processing that one item.

The alternative — the `geo_jobs` pattern: claim by committing `PENDING → RUNNING`,
then process — has a known window this domain does not have to inherit. A worker
killed between the claim commit and the terminal write leaves a `RUNNING` row
nothing will ever finish, which is why `geo/reconciliation.py` exists to
terminalize stale trackers. Here a killed worker aborts its transaction, the lock
is released by Postgres, and the item is still `pendiente` — the state it never
left. There is nothing to reap because nothing was orphaned, and no seventh state
was added to a union the design fixed at six.

The cost is stated rather than hidden: the item's transaction stays open for the
duration of its processing, holding one connection and one row lock. That is
bounded by `conocimiento_item_deadline_s` (60 s), which is the same budget the
provider attempts are already bounded by, and the surface is admin-only and
low-volume by construction. If throughput ever makes a 60 s transaction the
binding constraint, the fix is a lease column plus a reaper — and it must be
taken as a decision, with the orphan window written down, not slid in.

**Staleness needs no heartbeat.** A3's honesty obligation is that an item must
not sit `pendiente` forever with no explanation. The signal is the item's own
age: a `pendiente` older than the configured window IS a worker that has not
picked it up. A separate "last heartbeat" row would be a second thing to keep
true, and one that reports a healthy worker while a poison item sits unclaimed.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.conocimiento.models import ESTADO_PENDIENTE, RagConsulta
from app.domains.conocimiento.schemas import RespuestaConocimiento

#: A question longer than this is refused at the door. The body limit
#: (`enforce_body_limit`) bounds the BYTES; this bounds the text that will be
#: stored verbatim, embedded, and put in a prompt. They are different limits and
#: a deployment needs both: a 1 MB body of valid UTF-8 is one question.
PREGUNTA_MAX_CHARS = 2000


class PreguntaInvalida(ValueError):
    """The submitted text cannot be a question. Refused before it is stored."""


class EstadoIncoherente(RuntimeError):
    """A terminal write whose payload disagrees with the state column.

    Raised BEFORE the row is touched. The database's CHECKs catch the coupling
    between `estado`, `respuesta` and `procesada_en`; they cannot compare the
    column against a key INSIDE the JSON payload, and that is the one drift the
    duplication makes possible.
    """


def encolar(db: Session, *, usuario_id: uuid.UUID | None, pregunta: str) -> RagConsulta:
    """Write one `pendiente` item and return it. The whole POST does this."""
    limpia = (pregunta or "").strip()
    if not limpia:
        raise PreguntaInvalida(
            "an empty question is not a question. Enqueuing it would spend a "
            "quota slot and a worker's item budget to produce an abstention "
            "nobody asked for."
        )
    if len(limpia) > PREGUNTA_MAX_CHARS:
        raise PreguntaInvalida(
            f"the question is {len(limpia)} characters and the ceiling is "
            f"{PREGUNTA_MAX_CHARS}. Refused here rather than truncated: a "
            "truncated legal question is a DIFFERENT question, and the answer "
            "would be certified against text the asker never wrote."
        )
    item = RagConsulta(usuario_id=usuario_id, pregunta=limpia, estado=ESTADO_PENDIENTE)
    db.add(item)
    db.flush()
    return item


def obtener(db: Session, consulta_id: uuid.UUID, *, usuario_id: uuid.UUID | None) -> Any:
    """One item, scoped to its requester.

    The scoping is not a convenience filter: the row holds a verbatim question a
    CD member asked, and every admin being able to read every other admin's
    questions by guessing an id is a privacy fact, not a permissions detail. A
    non-owner gets `None`, which the router turns into a 404 rather than a 403 —
    a 403 confirms the id exists.
    """
    return db.execute(
        select(RagConsulta).where(
            RagConsulta.id == consulta_id,
            RagConsulta.usuario_id == usuario_id,
        )
    ).scalar_one_or_none()


def listar(db: Session, *, usuario_id: uuid.UUID | None, limite: int = 50) -> list[Any]:
    """The requester's own items, newest first."""
    return list(
        db.execute(
            select(RagConsulta)
            .where(RagConsulta.usuario_id == usuario_id)
            .order_by(RagConsulta.creada_en.desc(), RagConsulta.id.desc())
            .limit(limite)
        )
        .scalars()
        .all()
    )


def reclamar_pendiente(db: Session) -> Any:
    """The oldest unclaimed `pendiente`, locked for THIS transaction, or `None`.

    `SKIP LOCKED` is what makes two workers safe without a coordination table:
    each takes the oldest row the other is not already holding. See the module
    docstring for why the row is NOT flipped to an intermediate state.
    """
    return db.execute(
        select(RagConsulta)
        .where(RagConsulta.estado == ESTADO_PENDIENTE)
        .order_by(RagConsulta.creada_en.asc(), RagConsulta.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()


def persistir_resultado(
    db: Session,
    item: RagConsulta,
    respuesta: RespuestaConocimiento,
    *,
    decision_ruta_id: uuid.UUID | None = None,
    ahora: datetime.datetime | None = None,
) -> RagConsulta:
    """Move one item from `pendiente` to its terminal state, atomically.

    Refuses a `pendiente` payload: `pendiente` is the state an item is BORN in
    and the one state no processing run may write. Persisting it would look like
    a completed item and would trip the database's own coupling CHECK one layer
    later, with a constraint name instead of a reason.
    """
    if respuesta.estado == ESTADO_PENDIENTE:
        raise EstadoIncoherente(
            "a processing run cannot write `pendiente`: that is the state the "
            "item was already in, and writing it as a RESULT would claim the "
            "worker decided something when it decided nothing."
        )
    if item.estado != ESTADO_PENDIENTE:
        raise EstadoIncoherente(
            f"item {item.id} is already {item.estado!r}. An item has exactly one "
            "terminal state; overwriting it would silently replace an answer a "
            "CD member may already have read."
        )
    carga = respuesta.model_dump(mode="json")
    if carga.get("estado") != respuesta.estado:
        raise EstadoIncoherente(
            "the serialized payload's estado does not match the object's. The "
            "column and the payload are two copies of one fact and this is the "
            "seam where they could drift."
        )
    item.estado = respuesta.estado
    item.respuesta = carga
    item.decision_ruta_id = decision_ruta_id
    item.procesada_en = ahora or datetime.datetime.now(datetime.timezone.utc)
    db.flush()
    return item


# ---------------------------------------------------------------------------
# Diagnostics (task 7.6) — where a permanently-down worker becomes visible
# ---------------------------------------------------------------------------


def profundidad(db: Session) -> int:
    """How many items are waiting. Every requester's, not one user's."""
    return int(
        db.execute(
            select(func.count())
            .select_from(RagConsulta)
            .where(RagConsulta.estado == ESTADO_PENDIENTE)
        ).scalar_one()
        or 0
    )


def mas_antiguo_pendiente(db: Session) -> datetime.datetime | None:
    """When the oldest waiting item was submitted, or `None` if none is."""
    return db.execute(
        select(func.min(RagConsulta.creada_en)).where(RagConsulta.estado == ESTADO_PENDIENTE)
    ).scalar_one_or_none()


def ultima_corrida(db: Session) -> datetime.datetime | None:
    """When the worker last finished an item, or `None` if it never has.

    Derived from the items themselves rather than from a heartbeat: a heartbeat
    can report a healthy worker while every item it touches fails, and this
    cannot.
    """
    return db.execute(
        select(func.max(RagConsulta.procesada_en)).where(RagConsulta.estado != ESTADO_PENDIENTE)
    ).scalar_one_or_none()


def esta_demorado(
    item: RagConsulta,
    *,
    ventana_s: float,
    ahora: datetime.datetime | None = None,
) -> bool:
    """A3's honesty obligation: is this `pendiente` no longer honest?

    True only for a `pendiente` older than the window. A terminal item is never
    delayed — it is finished — and saying otherwise would put a warning next to
    an answer that arrived.

    `ventana_s <= 0` disables the check rather than making everything delayed:
    an unset window must not paint every fresh submission as a stuck one.
    """
    if item.estado != ESTADO_PENDIENTE or ventana_s <= 0:
        return False
    referencia = ahora or datetime.datetime.now(datetime.timezone.utc)
    creada = item.creada_en
    if creada is None:
        return False
    if creada.tzinfo is None:
        # `creada_en` is TIMESTAMPTZ; a naive value here means the row was built
        # in memory and never round-tripped. Comparing it against an aware `now`
        # raises, so it is read as UTC rather than crashing the diagnostic.
        creada = creada.replace(tzinfo=datetime.timezone.utc)
    return (referencia - creada).total_seconds() > ventana_s
