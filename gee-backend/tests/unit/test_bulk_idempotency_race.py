"""R1-001: IntegrityError replay of bulk_update must honor payload_hash."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.domains.denuncias.models import DenunciaBulkReceipt
from app.domains.denuncias.notify import payload_hash
from app.domains.denuncias.service import DenunciaService


def test_bulk_update_integrity_error_mismatched_hash_is_409() -> None:
    operator_id = uuid.uuid4()
    denuncia_id = uuid.uuid4()
    key = f"key-{uuid.uuid4().hex[:12]}"
    digest = payload_hash([denuncia_id], "en_revision", None)
    other = payload_hash([denuncia_id], "descartado", "otro")
    assert digest != other

    winner = DenunciaBulkReceipt(
        id=uuid.uuid4(),
        idempotency_key=key,
        operador_id=operator_id,
        payload_hash=other,
        resultado=[{"id": str(denuncia_id), "ok": True, "error": None}],
    )

    db = MagicMock()
    # First execute: no existing receipt. Second (after IntegrityError): winner.
    lookups = iter(
        [
            MagicMock(scalar_one_or_none=lambda: None),
            MagicMock(scalar_one_or_none=lambda: winner),
        ]
    )
    db.execute.side_effect = lambda *_a, **_k: next(lookups)
    db.commit.side_effect = IntegrityError("INSERT", {}, Exception("uq"))

    service = DenunciaService(repository=MagicMock())
    current = MagicMock()
    current.estado = "en_revision"  # short-circuit: no nested update/commit
    service.get_by_id = MagicMock(return_value=current)  # type: ignore[method-assign]

    with pytest.raises(HTTPException) as caught:
        service.bulk_update(
            db,
            ids=[denuncia_id],
            estado="en_revision",
            comentario=None,
            idempotency_key=key,
            operator_id=operator_id,
        )

    assert caught.value.status_code == 409
    assert "idempotencia" in str(caught.value.detail).lower()
    db.rollback.assert_called()


def test_bulk_update_integrity_error_same_hash_returns_winner() -> None:
    operator_id = uuid.uuid4()
    denuncia_id = uuid.uuid4()
    key = f"key-{uuid.uuid4().hex[:12]}"
    digest = payload_hash([denuncia_id], "en_revision", None)
    winner_rows = [{"id": str(denuncia_id), "ok": True, "error": None}]

    winner = DenunciaBulkReceipt(
        id=uuid.uuid4(),
        idempotency_key=key,
        operador_id=operator_id,
        payload_hash=digest,
        resultado=winner_rows,
    )

    db = MagicMock()
    lookups = iter(
        [
            MagicMock(scalar_one_or_none=lambda: None),
            MagicMock(scalar_one_or_none=lambda: winner),
        ]
    )
    db.execute.side_effect = lambda *_a, **_k: next(lookups)
    db.commit.side_effect = IntegrityError("INSERT", {}, Exception("uq"))

    service = DenunciaService(repository=MagicMock())
    current = MagicMock()
    current.estado = "en_revision"
    service.get_by_id = MagicMock(return_value=current)  # type: ignore[method-assign]

    result = service.bulk_update(
        db,
        ids=[denuncia_id],
        estado="en_revision",
        comentario=None,
        idempotency_key=key,
        operator_id=operator_id,
    )
    assert result == winner_rows
