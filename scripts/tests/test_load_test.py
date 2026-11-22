"""Tests for the stdlib load test harness (`scripts/load_test.py`)."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

import pytest

from scripts import load_test


@pytest.mark.parametrize(
    "url",
    [
        "https://cc10demayo-api.javierzader.com",
        "https://consorcio-canalero.pages.dev",
        "https://preview-abc.consorcio-canalero.pages.dev",
        "https://cc10demayo-tiles.javierzader.com/",
        "ftp://127.0.0.1:8000",
        "not-a-url",
    ],
)
def test_refuses_production_host_or_bad_scheme_without_allow_prod(url: str) -> None:
    rc = load_test.main(["--base-url", url])
    assert rc == 2


def test_missing_required_scenario_inputs_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOAD_TEST_CAMPO_TOKEN", raising=False)
    monkeypatch.delenv("LOAD_TEST_BEARER_TOKEN", raising=False)

    assert load_test.main(["--base-url", "http://127.0.0.1:8000", "--scenario", "campo"]) == 2
    assert load_test.main(["--base-url", "http://127.0.0.1:8000", "--scenario", "informe-pdf"]) == 2
    assert (
        load_test.main(
            [
                "--base-url",
                "http://127.0.0.1:8000",
                "--scenario",
                "informe-pdf",
                "--informe-id",
                "inf-1",
            ]
        )
        == 2
    )


def _start_loopback_server(*, fail_path: str | None = None, delay_s: float = 0.0):
    seen_headers: list[tuple[str, str | None, str | None]] = []
    lock = threading.Lock()

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            if delay_s > 0:
                time.sleep(delay_s)
            with lock:
                seen_headers.append(
                    (
                        self.path,
                        self.headers.get("Authorization"),
                        self.headers.get("Accept-Encoding"),
                    )
                )
            if fail_path and self.path == fail_path:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"error")
                return
            if self.path in {"/live", "/ready", "/api/v2/public/layers/catalog"}:
                payload = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.path == "/api/v2/public/campo/tok123":
                payload = b'{"campo":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.path == "/api/v2/geo/informes-area/inf-1/pdf":
                if self.headers.get("Authorization") != "Bearer secret-tok":
                    self.send_response(401)
                    self.end_headers()
                    return
                payload = b"%PDF-1.4\n"
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8"))
            if self.path == "/api/v2/geo/analisis-zona" and body.get("tipo") == "geometria":
                payload = b'{"resumen":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(400)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, seen_headers


def test_smoke_public_and_all_scenarios_against_loopback_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOAD_TEST_BEARER_TOKEN", "secret-tok")
    server, _thread, seen_headers = _start_loopback_server()
    try:
        port = server.server_address[1]
        report_path = tmp_path / "load-report.json"
        rc = load_test.main(
            [
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--scenario",
                "all",
                "--concurrency",
                "3",
                "--requests",
                "12",
                "--campo-token",
                "tok123",
                "--informe-id",
                "inf-1",
                "--max-p95-ms",
                "2000",
                "--max-error-rate",
                "0.0",
                "--json-out",
                str(report_path),
            ]
        )
    finally:
        server.shutdown()
        server.server_close()

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    overall = report["overall"]
    assert overall["total"] == 12
    assert overall["ok"] == 12
    assert overall["errors"] == 0
    assert 0.0 <= overall["min_ms"] <= overall["p50_ms"] <= overall["p95_ms"] <= overall["p99_ms"]
    assert overall["p99_ms"] <= overall["max_ms"]
    assert set(report["targets"]) == {
        "live",
        "ready",
        "public-layers",
        "analisis-zona",
        "campo-package",
        "informe-pdf",
    }
    campo_headers = [h for h in seen_headers if h[0] == "/api/v2/public/campo/tok123"]
    assert campo_headers and all(h[2] == "gzip" for h in campo_headers)


def test_budget_failure_on_error_rate_and_p95() -> None:
    failing_server, _t1, _ = _start_loopback_server(fail_path="/ready")
    try:
        port = failing_server.server_address[1]
        rc_err = load_test.main(
            [
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--scenario",
                "smoke-public",
                "--concurrency",
                "2",
                "--requests",
                "6",
                "--max-error-rate",
                "0.0",
            ]
        )
    finally:
        failing_server.shutdown()
        failing_server.server_close()
    assert rc_err == 1

    slow_server, _t2, _ = _start_loopback_server(delay_s=0.02)
    try:
        port = slow_server.server_address[1]
        rc_p95 = load_test.main(
            [
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--scenario",
                "smoke-public",
                "--concurrency",
                "2",
                "--requests",
                "3",
                "--max-p95-ms",
                "1.0",
            ]
        )
    finally:
        slow_server.shutdown()
        slow_server.server_close()
    assert rc_p95 == 1


def test_percentile_calculation_edge_cases() -> None:
    assert load_test.percentile([], 95.0) == 0.0
    assert load_test.percentile([42.5], 95.0) == 42.5
    assert load_test.percentile([10.0, 20.0, 30.0, 40.0], 50.0) == 25.0
    assert load_test.percentile([10.0, 20.0, 30.0, 40.0], 100.0) == 40.0
