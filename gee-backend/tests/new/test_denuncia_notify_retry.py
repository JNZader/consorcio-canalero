"""Issue #697: una falla transitoria de SMTP reintenta, no desaparece.

``denuncias.notify_status`` corre con el early-ack default de la app
(``task_acks_late=False``): apenas el worker lo toma, un raise queda acked
y no se re-entrega nunca. Antes de este fix el task no declaraba retry y
``send_email_blocking`` se tragaba las fallas de SMTP, así que una caída
transitoria perdía la notificación al vecino para siempre.

Drive pattern (sin broker): el task bound se ejecuta directo con
``push_request(retries=n)`` simulando la n-ésima re-entrega, y ``task.retry``
se reemplaza por un stub que levanta la ``Retry`` de Celery — exactamente
lo que hace el ``self.retry`` real cuando agenda otro intento. Misma
filosofía de seam que los tests de ``_revisit_stale`` (rainfall), que
reciben ``retry=self.retry`` inyectable.
"""

from __future__ import annotations

import logging

import pytest
from celery.exceptions import Retry

import app.domains.denuncias.tasks as denuncias_tasks
from app.config import settings
from app.domains.denuncias.models import Denuncia, EstadoDenuncia

LOGGER_NAME = "app.domains.denuncias.tasks"
CONTACT_EMAIL = "vecino@example.test"
ESTADO = EstadoDenuncia.RESUELTO.value


@pytest.fixture(autouse=True)
def _structlog_through_stdlib():
    """Route structlog events into stdlib logging so caplog sees them.

    Same configuration the running app installs (``app.main`` import); the
    module's task logger has not been used yet, so nothing is cached under
    the default PrintLoggerFactory (``cache_logger_on_first_use=True``).
    """
    from app.core.logging import configure_structlog

    configure_structlog(json_format=True, log_level="INFO")


@pytest.fixture
def denuncia_id(db_session_factory) -> str:
    """Una denuncia con email de contacto, visible para la sesión del task.

    ``deliver_status_email`` abre SU PROPIA ``SessionLocal()``; el test la
    parchea al factory del conftest para que el task lea la fila desde la
    misma conexión/transacción del test (patrón ``db_session_factory``).
    """
    denuncia = Denuncia(
        tipo="desborde",
        descripcion="Canal tapado junto al puente.",
        latitud=-32.6,
        longitud=-62.7,
        estado=EstadoDenuncia.RESUELTO,
        contacto_email=CONTACT_EMAIL,
    )
    db = db_session_factory()
    try:
        db.add(denuncia)
        db.flush()
        yield str(denuncia.id)
    finally:
        db.close()


def _scheduled_retry(**_kwargs):
    """Stub de ``self.retry``: agenda (levanta Retry) como el real."""
    raise Retry("retry scheduled by test stub")


def _run_attempt(task, denuncia_id: str, *, retries: int) -> str:
    """Ejecuta el cuerpo del task como la n-ésima entrega del broker."""
    task.push_request(retries=retries)
    try:
        return task.run(denuncia_id, ESTADO)
    finally:
        task.pop_request()


def test_flag_off_short_circuits_without_touching_smtp(monkeypatch, denuncia_id) -> None:
    """La condición de encendido: flag OFF no abre SMTP ni DB."""
    monkeypatch.setattr(settings, "denuncia_status_email_enabled", False)

    def _must_not_send(**_kwargs):  # pragma: no cover - would fail the test
        raise AssertionError("send_email_blocking must not run with the flag off")

    monkeypatch.setattr(denuncias_tasks, "send_email_blocking", _must_not_send)
    task = denuncias_tasks.notify_denuncia_status

    assert _run_attempt(task, denuncia_id, retries=0) == "flag_off"


def test_transient_smtp_failure_recovers_after_retries(
    monkeypatch, denuncia_id, db_session_factory
) -> None:
    """Falla dos veces, recupera en la tercera entrega: enviado tras reintentos."""
    task = denuncias_tasks.notify_denuncia_status
    pending_failures = [RuntimeError("smtp down"), RuntimeError("smtp still down")]
    calls: list[dict] = []

    def _flaky_send(**kwargs):
        calls.append(kwargs)
        if pending_failures:
            raise pending_failures.pop(0)

    monkeypatch.setattr(settings, "denuncia_status_email_enabled", True)
    monkeypatch.setattr(denuncias_tasks, "SessionLocal", db_session_factory)
    monkeypatch.setattr(denuncias_tasks, "send_email_blocking", _flaky_send)
    monkeypatch.setattr(task, "retry", _scheduled_retry)

    # Entregas 1 y 2 (retries 0 y 1): falla transitoria -> agenda reintento.
    with pytest.raises(Retry):
        _run_attempt(task, denuncia_id, retries=0)
    with pytest.raises(Retry):
        _run_attempt(task, denuncia_id, retries=1)

    # Entrega 3 (retries=2): SMTP recuperado -> entregado, sin más reintentos.
    assert _run_attempt(task, denuncia_id, retries=2) == "queued_or_sent"

    assert len(calls) == 3, "dos intentos fallidos + el que llega"
    assert calls[-1]["to_email"] == CONTACT_EMAIL
    assert ESTADO in calls[-1]["body_text"]


def test_permanent_smtp_failure_logs_terminal_without_crashing(
    monkeypatch, denuncia_id, db_session_factory, caplog
) -> None:
    """Falla siempre: reintentos agotados + log definitivo, sin excepción."""
    task = denuncias_tasks.notify_denuncia_status
    calls: list[dict] = []

    def _always_fails(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("smtp unreachable")

    monkeypatch.setattr(settings, "denuncia_status_email_enabled", True)
    monkeypatch.setattr(denuncias_tasks, "SessionLocal", db_session_factory)
    monkeypatch.setattr(denuncias_tasks, "send_email_blocking", _always_fails)
    monkeypatch.setattr(task, "retry", _scheduled_retry)

    # Entregas 1..max_retries: agenda reintento (Retry propagada al worker).
    for retries in range(task.max_retries):
        with pytest.raises(Retry):
            _run_attempt(task, denuncia_id, retries=retries)

    # Última entrega permitida (retries == max_retries): fallo definitivo
    # registrado como log estructurado, NO como raise — el worker sigue vivo.
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = _run_attempt(task, denuncia_id, retries=task.max_retries)

    assert result == "failed_after_retries"
    assert len(calls) == task.max_retries + 1, "max_retries + 1 intentos totales"

    terminal = [
        record.msg
        for record in caplog.records
        if isinstance(record.msg, dict)
        and record.msg.get("event") == "denuncia.notify_status.failed_permanently"
    ]
    assert len(terminal) == 1, caplog.text
    assert terminal[0]["denuncia_id"] == denuncia_id
    assert terminal[0]["estado"] == ESTADO
    assert terminal[0]["attempts"] == task.max_retries + 1
    assert "smtp unreachable" in terminal[0]["error"]
