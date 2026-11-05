"""F2: a retry with the same Idempotency-Key does not insert a second denuncia."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from geoalchemy2.functions import ST_MakePoint, ST_SetSRID
from sqlalchemy.exc import IntegrityError

from app.auth.models import User, UserRole
from app.domains.denuncias.models import Denuncia
from app.domains.denuncias.schemas import DenunciaCreate
from app.domains.denuncias.service import DenunciaService
from app.shared.submission_limit import DAILY_SUBMISSION_LIMIT


@pytest.fixture
def user_id(db) -> uuid.UUID:
    user = User(
        id=uuid.uuid4(),
        email=f"idem-{uuid.uuid4().hex[:8]}@x.test",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=UserRole.CIUDADANO,
    )
    db.add(user)
    db.flush()
    return user.id


def _payload(suffix: str = "a") -> DenunciaCreate:
    return DenunciaCreate(
        tipo="desborde",
        descripcion=f"Canal tapado junto al puente {suffix} y un poco mas.",
        latitud=-32.6,
        longitud=-62.7,
    )


def test_retry_returns_the_same_row_and_does_not_spend_another_slot(db, user_id) -> None:
    service = DenunciaService()
    first = service.create(db, _payload(), user_id=user_id, idempotency_key="retry-key-1")
    second = service.create(db, _payload(), user_id=user_id, idempotency_key="retry-key-1")

    assert second.id == first.id
    stored = db.query(Denuncia).filter(Denuncia.user_id == user_id).count()
    assert stored == 1


def test_same_key_with_a_different_body_is_409(db, user_id) -> None:
    service = DenunciaService()
    service.create(db, _payload("a"), user_id=user_id, idempotency_key="retry-key-2")
    with pytest.raises(HTTPException) as exc_info:
        service.create(db, _payload("b"), user_id=user_id, idempotency_key="retry-key-2")
    assert exc_info.value.status_code == 409


def test_lost_race_on_the_unique_key_returns_the_winner(db, user_id, monkeypatch) -> None:
    service = DenunciaService()
    winner = Denuncia(
        tipo="desborde",
        descripcion="Canal tapado junto al puente a y un poco mas.",
        latitud=-32.6,
        longitud=-62.7,
        geom=ST_SetSRID(ST_MakePoint(-62.7, -32.6), 4326),
        user_id=user_id,
        idempotency_key="retry-key-3",
    )
    db.add(winner)
    db.flush()

    def boom(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    monkeypatch.setattr(service.repo, "create", boom)
    replayed = service.create(db, _payload(), user_id=user_id, idempotency_key="retry-key-3")
    assert replayed.id == winner.id


def test_replay_does_not_count_against_a_full_quota(db, user_id) -> None:
    service = DenunciaService()
    first = service.create(db, _payload("quota"), user_id=user_id, idempotency_key="retry-key-4")
    for index in range(DAILY_SUBMISSION_LIMIT - 1):
        service.create(
            db,
            _payload(f"extra-{index}-texto"),
            user_id=user_id,
            idempotency_key=f"other-{index}",
        )

    replayed = service.create(db, _payload("quota"), user_id=user_id, idempotency_key="retry-key-4")
    assert replayed.id == first.id
