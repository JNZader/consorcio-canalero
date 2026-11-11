"""Business-logic layer for denuncias domain."""

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.denuncias.models import (
    Denuncia,
    EstadoDenuncia,
    VALID_TRANSITIONS,
)
from app.domains.denuncias.repository import DenunciaRepository
from app.domains.denuncias.schemas import DenunciaCreate, DenunciaUpdate
from app.shared.enum_params import require_choice
from app.shared.submission_limit import (
    enforce_submission_limit,
    get_submission_status,
)


class DenunciaService:
    """Orchestrates repository calls with business rules."""

    def __init__(self, repository: DenunciaRepository | None = None) -> None:
        self.repo = repository or DenunciaRepository()

    # ── QUERIES ───────────────────────────────

    def get_by_id(self, db: Session, denuncia_id: uuid.UUID) -> Denuncia:
        denuncia = self.repo.get_by_id(db, denuncia_id)
        if denuncia is None:
            raise HTTPException(status_code=404, detail="Denuncia no encontrada")
        return denuncia

    def list_denuncias(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado: Optional[str] = None,
        cuenca: Optional[str] = None,
        tipo: Optional[str] = None,
        categoria: Optional[str] = None,
        search: Optional[str] = None,
        sort: Optional[str] = None,
        order: Optional[str] = None,
    ) -> tuple[list[Denuncia], int]:
        estado = require_choice(estado, EstadoDenuncia, "estado")
        return self.repo.get_all(
            db,
            page=page,
            limit=limit,
            estado_filter=estado,
            cuenca_filter=cuenca,
            tipo_filter=tipo,
            categoria_filter=categoria,
            search=search,
            sort=sort,
            order=order,
        )

    def list_by_user(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Denuncia], int]:
        """Citizen-owned paginated list — used by `GET /denuncias/mine`."""
        return self.repo.get_all_by_user(db, user_id=user_id, page=page, limit=limit)

    def get_stats(self, db: Session) -> dict:
        return self.repo.get_stats(db)

    # ── COMMANDS ──────────────────────────────

    def create(
        self,
        db: Session,
        data: DenunciaCreate,
        user_id: Optional[uuid.UUID] = None,
        idempotency_key: Optional[str] = None,
    ) -> Denuncia:
        """Create a denuncia and commit.

        The same ``idempotency_key`` for the same user and the same payload
        returns the row already stored. A lost response can be retried
        without a second denuncia and without spending another quota slot.
        """
        if user_id is not None and idempotency_key:
            existing = self.repo.get_active_by_idempotency(db, user_id, idempotency_key)
            if existing is not None:
                self._require_same_attempt(existing, data)
                return existing
        if user_id is not None:
            enforce_submission_limit(
                db,
                model=Denuncia,
                user_id_attr=Denuncia.user_id,
                user_id=user_id,
            )
        try:
            with db.begin_nested():
                denuncia = self.repo.create(
                    db,
                    data,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                )
        except IntegrityError:
            if user_id is not None and idempotency_key:
                existing = self.repo.get_active_by_idempotency(db, user_id, idempotency_key)
                if existing is not None:
                    self._require_same_attempt(existing, data)
                    return existing
            raise
        db.commit()
        db.refresh(denuncia)
        return denuncia

    @staticmethod
    def _require_same_attempt(existing: Denuncia, data: DenunciaCreate) -> None:
        same = (
            existing.tipo == data.tipo
            and existing.descripcion == data.descripcion
            and abs(existing.latitud - data.latitud) < 1e-7
            and abs(existing.longitud - data.longitud) < 1e-7
        )
        if same:
            return
        raise HTTPException(
            status_code=409,
            detail="Esa clave de idempotencia ya se usó con otro contenido.",
        )

    def get_rate_limit_status(self, db: Session, user_id: uuid.UUID) -> dict:
        """Quota left for a citizen — used by `GET /denuncias/rate-limit`."""
        return get_submission_status(
            db,
            model=Denuncia,
            user_id_attr=Denuncia.user_id,
            user_id=user_id,
        )

    def update(
        self,
        db: Session,
        denuncia_id: uuid.UUID,
        data: DenunciaUpdate,
        operator_id: uuid.UUID,
    ) -> Denuncia:
        """
        Update estado / respuesta, validating state transitions
        and recording changes in historial. Commits here-and-now
        (single-item PATCH path).
        """
        updated = self._apply_update(db, denuncia_id, data, operator_id=operator_id)
        db.commit()
        db.refresh(updated)
        return updated

    def _apply_update(
        self,
        db: Session,
        denuncia_id: uuid.UUID,
        data: DenunciaUpdate,
        operator_id: uuid.UUID,
    ) -> Denuncia:
        """
        Flush-only core of ``update`` — the caller owns the commit.

        ``bulk_update`` reuses this so a whole batch (plus its receipt) can
        commit once at the end; anything raised here leaves the session's
        transaction exactly as the caller's savepoint policy decides.
        """
        denuncia = self.get_by_id(db, denuncia_id)
        previous_estado = denuncia.estado
        previous_respuesta = denuncia.respuesta
        self._validate_assignee(db, data)

        # State transition validation
        if data.estado is not None and data.estado != denuncia.estado:
            allowed = VALID_TRANSITIONS.get(denuncia.estado, set())
            if data.estado not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=(f"Transicion de estado invalida: {denuncia.estado} -> {data.estado}"),
                )

            # Record in historial
            self.repo.add_historial(
                db,
                denuncia_id=denuncia_id,
                estado_anterior=denuncia.estado,
                estado_nuevo=data.estado,
                comentario=data.comentario,
                usuario_id=operator_id,
            )

        updated = self.repo.update(db, denuncia_id, data)
        if updated is None:
            # Unreachable: ``get_by_id`` above would have raised 404 first.
            raise HTTPException(status_code=404, detail="Denuncia no encontrada")
        attended = (
            updated.estado == EstadoDenuncia.RESUELTO and updated.estado != previous_estado
        ) or (
            bool((updated.respuesta or "").strip())
            and (updated.respuesta or "") != (previous_respuesta or "")
        )
        from app.domains.denuncias.notify import maybe_enqueue_status_email

        maybe_enqueue_status_email(db, updated, became_attended=attended)
        return updated

    def _validate_assignee(self, db: Session, data: DenunciaUpdate) -> None:
        if "asignado_a" not in data.model_fields_set or data.asignado_a is None:
            return
        from app.auth.models import User, UserRole

        user = db.get(User, data.asignado_a)
        if user is None or user.role not in (UserRole.OPERADOR, UserRole.ADMIN):
            raise HTTPException(
                status_code=400, detail="El asignado tiene que ser operador o admin"
            )

    def bulk_update(
        self,
        db: Session,
        *,
        ids: list[uuid.UUID],
        estado: str,
        comentario: Optional[str],
        idempotency_key: str,
        operator_id: uuid.UUID,
    ) -> list[dict]:
        """
        Apply one estado change to many denuncias — all-or-nothing.

        Semantics (issue #696, parte 1): the whole batch flushes inside a
        savepoint and commits ONCE at the end, together with the
        ``DenunciaBulkReceipt`` row. Items and receipt share a single
        transaction, so a mid-batch non-HTTP failure (SQLAlchemyError from
        the outbox savepoint, a dropped connection, DataError) rolls the
        batch savepoint back and propagates: NOTHING stays applied, no
        receipt is written, and the route answers 500. Retrying with the
        same idempotency key starts from a clean slate.

        Expected per-item failures (HTTPException: 404 unknown id, 400
        invalid transition) do NOT abort the batch — each item runs in its
        own savepoint, only that item is undone, and the receipt records
        the per-item error.
        """
        from sqlalchemy import select

        from app.domains.denuncias.models import DenunciaBulkReceipt
        from app.domains.denuncias.notify import payload_hash

        digest = payload_hash(ids, estado, comentario)
        existing = db.execute(
            select(DenunciaBulkReceipt).where(
                DenunciaBulkReceipt.operador_id == operator_id,
                DenunciaBulkReceipt.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.payload_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail="Esa clave de idempotencia ya se usó con otro lote.",
                )
            return list(existing.resultado)

        resultados: list[dict] = []
        # Batch savepoint: on ANY non-HTTP escape the context manager rolls
        # back to here, discarding every flushed item — no half-applied
        # batch, no receipt. (The old loop committed per item inside
        # ``update()``, so a mid-batch SQLAlchemyError left earlier items
        # applied with no receipt at all.)
        with db.begin_nested():
            for denuncia_id in ids:
                # Per-item savepoint: an expected HTTPException (404/400)
                # undoes only this item's partial flushes and the batch
                # keeps going. Replaces the old session-wide ``db.rollback()``,
                # which here would also wipe the already-flushed items.
                try:
                    with db.begin_nested():
                        current = self.get_by_id(db, denuncia_id)
                        if current.estado == estado:
                            resultados.append({"id": str(denuncia_id), "ok": True, "error": None})
                            continue
                        self._apply_update(
                            db,
                            denuncia_id,
                            DenunciaUpdate(estado=estado, comentario=comentario),
                            operator_id=operator_id,
                        )
                        resultados.append({"id": str(denuncia_id), "ok": True, "error": None})
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, str) else "No se pudo actualizar"
                    resultados.append({"id": str(denuncia_id), "ok": False, "error": detail})

        # Single commit: the flushed batch and the receipt land atomically.
        receipt = DenunciaBulkReceipt(
            id=uuid.uuid4(),
            idempotency_key=idempotency_key,
            operador_id=operator_id,
            payload_hash=digest,
            resultado=resultados,
        )
        db.add(receipt)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent requests with the same operator+key: the unique
            # uq_denuncia_bulk_operator_key keeps one receipt. Mirror the
            # sequential replay path — same payload returns the winner's
            # resultado; a different payload is 409. Do NOT assume both
            # racers share the same destination (VALID_TRANSITIONS allows
            # e.g. pendiente→en_revision and pendiente→descartado).
            db.rollback()
            winner = db.execute(
                select(DenunciaBulkReceipt).where(
                    DenunciaBulkReceipt.operador_id == operator_id,
                    DenunciaBulkReceipt.idempotency_key == idempotency_key,
                )
            ).scalar_one_or_none()
            if winner is not None:
                if winner.payload_hash != digest:
                    raise HTTPException(
                        status_code=409,
                        detail="Esa clave de idempotencia ya se usó con otro lote.",
                    )
                return list(winner.resultado)
            raise
        return resultados
