"""N6: an ARCO soft-delete must free the 5/24h submission slot."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from geoalchemy2.functions import ST_MakePoint, ST_SetSRID

from app.auth.models import User, UserRole
from app.domains.denuncias.models import Denuncia, EstadoDenuncia
from app.shared.submission_limit import DAILY_SUBMISSION_LIMIT, get_submission_status


@pytest.fixture
def user_id(db) -> uuid.UUID:
    user = User(
        id=uuid.uuid4(),
        email=f"quota-{uuid.uuid4().hex[:8]}@x.test",
        hashed_password="x" * 20,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=UserRole.CIUDADANO,
    )
    db.add(user)
    db.flush()
    return user.id


def _denuncia(db, user_id: uuid.UUID, *, deleted: bool) -> None:
    row = Denuncia(
        tipo="desborde",
        descripcion="Cuota: la fila borrada no debe contar.",
        latitud=-33.7,
        longitud=-63.9,
        geom=ST_SetSRID(ST_MakePoint(-63.9, -33.7), 4326),
        estado=EstadoDenuncia.PENDIENTE,
        user_id=user_id,
        deleted_at=datetime.now(tz=timezone.utc) if deleted else None,
    )
    db.add(row)
    db.flush()


def test_soft_deleted_denuncias_do_not_burn_the_daily_slot(db, user_id: uuid.UUID) -> None:
    for _ in range(DAILY_SUBMISSION_LIMIT):
        _denuncia(db, user_id, deleted=False)

    full = get_submission_status(db, model=Denuncia, user_id_attr=Denuncia.user_id, user_id=user_id)
    assert full["remaining"] == 0

    for row in db.query(Denuncia).filter(Denuncia.user_id == user_id).all():
        row.deleted_at = datetime.now(tz=timezone.utc)
    db.flush()

    freed = get_submission_status(
        db, model=Denuncia, user_id_attr=Denuncia.user_id, user_id=user_id
    )
    assert freed["remaining"] == DAILY_SUBMISSION_LIMIT
    assert freed["reset_seconds"] == 0
