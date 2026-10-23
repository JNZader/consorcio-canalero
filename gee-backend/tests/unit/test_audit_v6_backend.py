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
    """BE-07: an async route that takes a sync Session must offload that work.

    The marker may live in the route or in a same-module helper the route
    hands the session to. ``proxy_tile`` does the latter: the publicity lookup
    moved into ``_cached_public_layer_tipo``, and a scan that only reads the
    route body flags a function that does not touch the session itself.
    """
    offenders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        source = path.read_text()
        offenders.extend(
            f"{path.relative_to(APP_ROOT)}:{name}" for name in _session_offload_offenders(source)
        )
    assert offenders == []


def test_session_offload_accepts_a_same_module_helper():
    source = "\n".join(
        (
            "async def _lookup(db: Session):",
            "    return await run_in_threadpool(read, db)",
            "",
            "async def proxy_tile(db: Session):",
            "    return await _lookup(db)",
        )
    )
    assert _session_offload_offenders(source) == []


def test_session_offload_rejects_a_direct_session_call():
    source = "\n".join(
        (
            "async def proxy_tile(db: Session):",
            "    return db.query()",
        )
    )
    assert _session_offload_offenders(source) == ["proxy_tile"]


def test_session_offload_rejects_a_helper_that_stays_on_the_loop():
    source = "\n".join(
        (
            "def _lookup(db: Session):",
            "    return db.query()",
            "",
            "async def proxy_tile(db: Session):",
            "    return _lookup(db)",
        )
    )
    assert _session_offload_offenders(source) == ["proxy_tile"]


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


_OFFLOAD_MARKERS = ("run_in_threadpool", "_run_blocking")


def _session_offload_offenders(source: str) -> list[str]:
    tree = ast.parse(source)
    functions = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and not _route_offloads_session(node, functions):
            offenders.append(node.name)
    return offenders


def _route_offloads_session(node: ast.AsyncFunctionDef, functions: dict[str, str]) -> bool:
    session_name = _session_parameter(node)
    if session_name is None:
        return True
    if _offloads(functions.get(node.name, "")):
        return True
    handed_off = False
    for child in _walk_without_nested(node):
        if not isinstance(child, ast.Call) or not _call_uses_session(child, session_name):
            continue
        callee = _callee_name(child)
        if callee in _OFFLOAD_MARKERS or _offloads(functions.get(callee or "", "")):
            handed_off = True
            continue
        return False
    return handed_off


def _session_parameter(node: ast.AsyncFunctionDef) -> str | None:
    for arg in (*node.args.args, *node.args.kwonlyargs):
        annotation = arg.annotation
        if isinstance(annotation, ast.Name) and annotation.id == "Session":
            return arg.arg
        if isinstance(annotation, ast.Constant) and annotation.value == "Session":
            return arg.arg
    return None


def _offloads(segment: str) -> bool:
    return any(marker in segment for marker in _OFFLOAD_MARKERS)


def _callee_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _call_uses_session(call: ast.Call, session_name: str) -> bool:
    for arg in (*call.args, *(kw.value for kw in call.keywords)):
        if isinstance(arg, ast.Name) and arg.id == session_name:
            return True
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == session_name
    )


def _walk_without_nested(node: ast.AST):
    stack = list(getattr(node, "body", []))
    while stack:
        current = stack.pop()
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield current
        stack.extend(ast.iter_child_nodes(current))


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
