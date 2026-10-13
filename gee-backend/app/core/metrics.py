"""In-process Prometheus metrics for HTTP latency, HTTP 429s, and GEE calls.

The text format is the one Prometheus scrapes. Histograms use fixed buckets
so a scraper can compute p95 with ``histogram_quantile`` without a client
library in this process. Labels stay low-cardinality: method, a path with
ids collapsed, and status.
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict

_HTTP_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_GEE_BUCKETS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_NUMERIC_SEGMENT_RE = re.compile(r"/\d+(?=/|$)")

_lock = threading.Lock()
_http_requests: dict[tuple[str, str, str], int] = defaultdict(int)
_http_429: dict[tuple[str, str], int] = defaultdict(int)
_http_hist: dict[tuple[str, str], list[float]] = {}
_gee_hist: dict[str, list[float]] = {}


def route_label(path: str) -> str:
    """Collapse ids so a tile or a UUID does not become its own series."""
    bare = path.split("?", 1)[0] or "/"
    bare = _UUID_RE.sub("{id}", bare)
    bare = _NUMERIC_SEGMENT_RE.sub("/{n}", bare)
    if len(bare) > 160:
        bare = bare[:160]
    return bare


def reset_metrics() -> None:
    """Clear every series. Tests start from an empty registry."""
    with _lock:
        _http_requests.clear()
        _http_429.clear()
        _http_hist.clear()
        _gee_hist.clear()


def _histogram(store: dict, key, buckets: tuple[float, ...]) -> list[float]:
    row = store.get(key)
    if row is None:
        # bucket counts, then +Inf count, sum, count
        row = [0.0] * (len(buckets) + 3)
        store[key] = row
    return row


def _observe(row: list[float], buckets: tuple[float, ...], elapsed: float) -> None:
    for index, bound in enumerate(buckets):
        if elapsed <= bound:
            row[index] += 1
            break
    row[len(buckets)] += 1
    row[len(buckets) + 1] += elapsed
    row[len(buckets) + 2] += 1


def observe_http_request(method: str, path: str, status: int, elapsed_seconds: float) -> None:
    """Record one finished HTTP call, including a dedicated 429 counter."""
    method_label = method.upper()
    status_label = str(status)
    with _lock:
        _http_requests[(method_label, path, status_label)] += 1
        if status == 429:
            _http_429[(method_label, path)] += 1
        row = _histogram(_http_hist, (method_label, path), _HTTP_BUCKETS)
        _observe(row, _HTTP_BUCKETS, elapsed_seconds)


def observe_gee_call(operation: str, elapsed_seconds: float) -> None:
    """Record one Earth Engine call so Prometheus can compute its p95."""
    with _lock:
        row = _histogram(_gee_hist, operation, _GEE_BUCKETS)
        _observe(row, _GEE_BUCKETS, elapsed_seconds)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(pairs: tuple[tuple[str, str], ...]) -> str:
    if not pairs:
        return ""
    rendered = ",".join(f'{key}="{_escape(value)}"' for key, value in pairs)
    return "{" + rendered + "}"


def _emit_histogram(
    lines: list[str],
    name: str,
    help_text: str,
    store: dict,
    buckets: tuple[float, ...],
    label_names: tuple[str, ...],
) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} histogram")
    for key, row in sorted(store.items(), key=lambda item: item[0]):
        keys = key if isinstance(key, tuple) else (key,)
        base = tuple(zip(label_names, keys, strict=True))
        cumulative = 0
        for index, bound in enumerate(buckets):
            cumulative += int(row[index])
            labels = _labels((*base, ("le", _format_bound(bound))))
            lines.append(f"{name}_bucket{labels} {cumulative}")
        labels = _labels((*base, ("le", "+Inf")))
        lines.append(f"{name}_bucket{labels} {int(row[len(buckets)])}")
        lines.append(f"{name}_sum{_labels(base)} {row[len(buckets) + 1]}")
        lines.append(f"{name}_count{_labels(base)} {int(row[len(buckets) + 2])}")


def _format_bound(bound: float) -> str:
    text = f"{bound:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def render_prometheus() -> str:
    """Render the registry in Prometheus text exposition format 0.0.4."""
    with _lock:
        http_requests = dict(_http_requests)
        http_429 = dict(_http_429)
        http_hist = {key: list(row) for key, row in _http_hist.items()}
        gee_hist = {key: list(row) for key, row in _gee_hist.items()}

    lines: list[str] = []
    lines.append("# HELP http_requests_total HTTP responses by method, route and status.")
    lines.append("# TYPE http_requests_total counter")
    for (method, path, status), count in sorted(http_requests.items()):
        labels = _labels((("method", method), ("path", path), ("status", status)))
        lines.append(f"http_requests_total{labels} {count}")

    lines.append("# HELP http_responses_429_total HTTP 429 responses by method and route.")
    lines.append("# TYPE http_responses_429_total counter")
    for (method, path), count in sorted(http_429.items()):
        labels = _labels((("method", method), ("path", path)))
        lines.append(f"http_responses_429_total{labels} {count}")

    _emit_histogram(
        lines,
        "http_request_duration_seconds",
        "HTTP request latency in seconds.",
        http_hist,
        _HTTP_BUCKETS,
        ("method", "path"),
    )
    _emit_histogram(
        lines,
        "gee_call_duration_seconds",
        "Google Earth Engine call latency in seconds.",
        gee_hist,
        _GEE_BUCKETS,
        ("operation",),
    )
    lines.append("")
    return "\n".join(lines)


class RequestMetricsMiddleware:
    """ASGI middleware that times the request and records the status code.

    Implemented as raw ASGI rather than ``BaseHTTPMiddleware`` so it does not
    add another response-buffering layer on top of the ones already installed.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or "/"
        if path in {"/", "/health", "/live", "/ready", "/metrics"}:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        label = route_label(path)
        status_holder = {"code": 500}
        started = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            observe_http_request(method, label, 500, time.perf_counter() - started)
            raise
        observe_http_request(method, label, status_holder["code"], time.perf_counter() - started)
