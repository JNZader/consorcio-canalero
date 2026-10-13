"""Locks for the audit-v6 backend fixes that do not need PostgreSQL."""

import ast
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.shared.upload_limits import (
    MAX_TABULAR_IMPORT_BYTES,
    MAX_XLSX_UNCOMPRESSED_BYTES,
    assert_xlsx_is_not_a_zip_bomb,
    read_upload_bounded,
)

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


def _upload(payload: bytes, filename: str = "padron.csv") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(payload),
        filename=filename,
        headers=Headers({"content-type": "application/octet-stream"}),
    )


def test_read_upload_bounded_rejects_an_oversized_body():
    payload = b"a" * (MAX_TABULAR_IMPORT_BYTES + 1)
    with pytest.raises(HTTPException) as exc:
        read_upload_bounded(_upload(payload))
    assert exc.value.status_code == 413


def test_read_upload_bounded_returns_a_small_body():
    assert read_upload_bounded(_upload(b"nombre,apellido\n")) == b"nombre,apellido\n"


def test_xlsx_zip_bomb_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"x" * (MAX_XLSX_UNCOMPRESSED_BYTES + 1))
    with pytest.raises(HTTPException) as exc:
        assert_xlsx_is_not_a_zip_bomb(buffer.getvalue(), "padron.xlsx")
    assert exc.value.status_code == 400


def test_http_handlers_do_not_echo_exception_text():
    """BE-09: the handlers that used to return ``detail=str(exc)``."""
    offenders: list[str] = []
    for relative in (
        "domains/padron/router.py",
        "domains/geo/router_basins_bundle.py",
        "domains/geo/router_bundle_io.py",
        "domains/geo/intelligence/router.py",
        "domains/geo/rainfall/router.py",
    ):
        source = (APP_ROOT / relative).read_text()
        if "detail=str(" in source or "detail=str (" in source:
            offenders.append(relative)
    assert offenders == []


def test_async_routes_with_a_sync_session_leave_the_event_loop():
    """BE-07: an async route that takes a sync Session must offload that work."""
    offenders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not _takes_sync_session(node):
                continue
            body = ast.get_source_segment(source, node) or ""
            if "run_in_threadpool" not in body and "_run_blocking" not in body:
                offenders.append(f"{path.relative_to(APP_ROOT)}:{node.name}")
    assert offenders == []


def test_runtime_code_does_not_execute_create_extension():
    """DB-04: CREATE EXTENSION stays in migrations. The app role cannot run it."""
    offenders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if name != "execute":
                continue
            segment = ast.get_source_segment(source, node) or ""
            if "CREATE EXTENSION" in segment.upper() or "UPGRADE_STATEMENTS" in segment:
                offenders.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")
    assert offenders == []


def test_api_connect_hook_sets_statement_and_idle_timeouts(monkeypatch):
    from app.db import session as session_mod

    monkeypatch.setattr(session_mod, "_IS_CELERY_PROCESS", False)
    cursor = _FakeCursor()
    session_mod._apply_session_timeouts(_FakeConnection(cursor), None)
    assert cursor.statements == [
        "SET statement_timeout = 15000",
        "SET idle_in_transaction_session_timeout = 60000",
    ]


def test_celery_connect_hook_uses_the_longer_ceiling(monkeypatch):
    from app.db import session as session_mod

    monkeypatch.setattr(session_mod, "_IS_CELERY_PROCESS", True)
    cursor = _FakeCursor()
    session_mod._apply_session_timeouts(_FakeConnection(cursor), None)
    assert "SET statement_timeout = 300000" in cursor.statements
    assert "SET idle_in_transaction_session_timeout = 300000" in cursor.statements


def test_provision_script_transfers_matview_ownership_without_create_extension():
    script = (APP_ROOT.parents[1] / "scripts" / "provision_app_rw.sql").read_text()
    assert "idle_in_transaction_session_timeout" in script
    assert "ALTER MATERIALIZED VIEW" in script
    assert "vt_parcelas_catastro" in script
    assert "CREATE EXTENSION" not in script


def _takes_sync_session(node: ast.AsyncFunctionDef) -> bool:
    for arg in (*node.args.args, *node.args.kwonlyargs):
        annotation = arg.annotation
        if isinstance(annotation, ast.Name) and annotation.id == "Session":
            return True
        if isinstance(annotation, ast.Constant) and annotation.value == "Session":
            return True
    return False


class _FakeCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str) -> None:
        self.statements.append(sql)

    def close(self) -> None:
        return None


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor
