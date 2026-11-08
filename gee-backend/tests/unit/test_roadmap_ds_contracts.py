"""Contratos del roadmap de denuncias que no necesitan base de datos."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import column

from app.domains.denuncias.notify import notification_task_id, payload_hash
from app.shared.list_sort import order_clause


def test_sort_desconocido_se_rechaza() -> None:
    created = column("created_at")
    with pytest.raises(HTTPException) as caught:
        order_clause("email", "asc", {"created_at": created}, default=created, tie=column("id"))
    assert caught.value.status_code == 400


def test_sort_vacio_no_es_ascendente() -> None:
    created = column("created_at")
    primary, _tie = order_clause(
        None, None, {"created_at": created}, default=created, tie=column("id")
    )
    assert "DESC" in str(primary).upper()


def test_aviso_misma_transicion_misma_clave() -> None:
    denuncia_id = uuid.uuid4()
    first = notification_task_id(denuncia_id, "resuelto", "listo")
    second = notification_task_id(denuncia_id, "resuelto", "listo")
    other = notification_task_id(denuncia_id, "resuelto", "otro")
    assert first == second
    assert first != other


def test_hash_de_lote_no_depende_del_orden() -> None:
    one = uuid.uuid4()
    two = uuid.uuid4()
    assert payload_hash([one, two], "en_revision", None) == payload_hash(
        [two, one], "en_revision", None
    )
