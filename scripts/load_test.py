#!/usr/bin/env python3
"""Concurrent HTTP load test harness for local, staging, or explicitly opted-in environments."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


PRODUCTION_HOSTS = frozenset(
    {
        "cc10demayo-api.javierzader.com",
        "consorcio-canalero.pages.dev",
        "cc10demayo-tiles.javierzader.com",
    }
)
PRODUCTION_SUFFIXES = (".javierzader.com", ".pages.dev")
MAX_CONCURRENCY = 32
MAX_REQUESTS = 500
DEFAULT_FICHA_PAYLOAD: dict[str, Any] = {
    "tipo": "geometria",
    "geometria": {
        "type": "Polygon",
        "coordinates": [
            [
                [-62.72, -32.64],
                [-62.70, -32.64],
                [-62.70, -32.62],
                [-62.72, -32.62],
                [-62.72, -32.64],
            ]
        ],
    },
}


class LoadTestConfigError(ValueError):
    """Raised when CLI arguments or environment prerequisites fail validation."""


@dataclass(frozen=True)
class EndpointTarget:
    name: str
    method: str
    path: str
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None


@dataclass(frozen=True)
class RequestSample:
    target: str
    status: int
    ok: bool
    latency_ms: float
    size_bytes: int
    error: str | None = None


def is_production_host(hostname: str | None) -> bool:
    """Return True if *hostname* points to a known production host or domain."""
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized in PRODUCTION_HOSTS:
        return True
    return any(normalized.endswith(suffix) for suffix in PRODUCTION_SUFFIXES)


def validate_base_url(base_url: str, *, allow_prod: bool) -> str:
    """Validate URL scheme/host and fail closed on production unless opted in."""
    parsed = urllib.parse.urlparse(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LoadTestConfigError(
            f"invalid --base-url {base_url!r}: expected http:// or https:// URL"
        )
    if is_production_host(parsed.hostname) and not allow_prod:
        raise LoadTestConfigError(
            f"refusing to run load test against production host {parsed.hostname!r} "
            "without --allow-prod"
        )
    return base_url.strip().rstrip("/")


def percentile(sorted_values: list[float], pct: float) -> float:
    """Linearly interpolate percentile *pct* (0..100) from pre-sorted latencies."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(sorted_values[low], 3)
    weight = rank - low
    value = sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight
    return round(value, 3)


def _load_ficha_payload(payload_path: Path | None) -> bytes:
    if payload_path is None:
        return json.dumps(DEFAULT_FICHA_PAYLOAD).encode("utf-8")
    try:
        raw = payload_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise LoadTestConfigError(f"cannot load --ficha-payload {payload_path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LoadTestConfigError("--ficha-payload JSON must be an object")
    return json.dumps(parsed).encode("utf-8")


def build_targets(
    *,
    scenario: str,
    ficha_payload_path: Path | None,
    campo_token: str | None,
    informe_id: str | None,
    bearer_token: str,
) -> list[EndpointTarget]:
    """Resolve concrete endpoint targets for the requested scenario, failing closed."""
    smoke = [
        EndpointTarget("live", "GET", "/live"),
        EndpointTarget("ready", "GET", "/ready"),
        EndpointTarget("public-layers", "GET", "/api/v2/public/layers/catalog"),
    ]
    if scenario == "smoke-public":
        return smoke

    if scenario == "analisis-zona":
        body = _load_ficha_payload(ficha_payload_path)
        return [
            EndpointTarget(
                "analisis-zona",
                "POST",
                "/api/v2/geo/analisis-zona",
                headers=(("Content-Type", "application/json"),),
                body=body,
            )
        ]

    if scenario == "campo":
        token = (campo_token or "").strip()
        if not token:
            raise LoadTestConfigError(
                "scenario 'campo' requires --campo-token or LOAD_TEST_CAMPO_TOKEN"
            )
        encoded = urllib.parse.quote(token, safe="")
        return [
            EndpointTarget(
                "campo-package",
                "GET",
                f"/api/v2/public/campo/{encoded}",
                headers=(("Accept-Encoding", "gzip"),),
            )
        ]

    if scenario == "informe-pdf":
        if not (informe_id or "").strip():
            raise LoadTestConfigError("scenario 'informe-pdf' requires --informe-id")
        if not bearer_token.strip():
            raise LoadTestConfigError(
                "scenario 'informe-pdf' requires LOAD_TEST_BEARER_TOKEN env var"
            )
        encoded_id = urllib.parse.quote(informe_id.strip(), safe="")
        return [
            EndpointTarget(
                "informe-pdf",
                "GET",
                f"/api/v2/geo/informes-area/{encoded_id}/pdf",
                headers=(("Authorization", f"Bearer {bearer_token.strip()}"),),
            )
        ]

    if scenario == "all":
        targets = [
            *smoke,
            *build_targets(
                scenario="analisis-zona",
                ficha_payload_path=ficha_payload_path,
                campo_token=campo_token,
                informe_id=informe_id,
                bearer_token=bearer_token,
            ),
        ]
        if (campo_token or "").strip():
            targets.extend(
                build_targets(
                    scenario="campo",
                    ficha_payload_path=ficha_payload_path,
                    campo_token=campo_token,
                    informe_id=informe_id,
                    bearer_token=bearer_token,
                )
            )
        if (informe_id or "").strip() and bearer_token.strip():
            targets.extend(
                build_targets(
                    scenario="informe-pdf",
                    ficha_payload_path=ficha_payload_path,
                    campo_token=campo_token,
                    informe_id=informe_id,
                    bearer_token=bearer_token,
                )
            )
        return targets

    raise LoadTestConfigError(f"unsupported scenario: {scenario!r}")


def _execute_one(
    base_url: str,
    target: EndpointTarget,
    *,
    timeout_s: float,
    allow_429: bool,
) -> RequestSample:
    url = f"{base_url}{target.path}"
    request = urllib.request.Request(url, data=target.body, method=target.method)
    for key, value in target.headers:
        request.add_header(key, value)

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            payload = response.read()
            status = int(response.status)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            ok = 200 <= status < 400
            return RequestSample(target.name, status, ok, elapsed_ms, len(payload))
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        status = int(exc.code)
        ok = allow_429 and status == 429
        return RequestSample(
            target.name,
            status,
            ok,
            elapsed_ms,
            len(body_bytes),
            error=None if ok else f"HTTP {status}",
        )
    except Exception as exc:  # noqa: BLE001 - surface transport errors cleanly in report
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return RequestSample(target.name, 0, False, elapsed_ms, 0, error=str(exc))


def summarize_samples(samples: list[RequestSample], *, elapsed_s: float) -> dict[str, Any]:
    """Aggregate per-target and overall latency, error-rate, and throughput stats."""

    def _stats(items: list[RequestSample], duration_s: float) -> dict[str, Any]:
        latencies = sorted(item.latency_ms for item in items)
        status_counts: dict[str, int] = {}
        ok_count = 0
        total_bytes = 0
        for item in items:
            key = str(item.status)
            status_counts[key] = status_counts.get(key, 0) + 1
            if item.ok:
                ok_count += 1
            total_bytes += item.size_bytes
        total = len(items)
        errors = total - ok_count
        return {
            "total": total,
            "ok": ok_count,
            "errors": errors,
            "error_rate": round((errors / total) if total else 0.0, 4),
            "status_counts": status_counts,
            "min_ms": round(latencies[0], 3) if latencies else 0.0,
            "p50_ms": percentile(latencies, 50.0),
            "p95_ms": percentile(latencies, 95.0),
            "p99_ms": percentile(latencies, 99.0),
            "max_ms": round(latencies[-1], 3) if latencies else 0.0,
            "total_bytes": total_bytes,
            "elapsed_s": round(duration_s, 3),
            "rps": round((total / duration_s) if duration_s > 0 else 0.0, 2),
        }

    by_target: dict[str, list[RequestSample]] = {}
    for sample in samples:
        by_target.setdefault(sample.target, []).append(sample)

    return {
        "overall": _stats(samples, elapsed_s),
        "targets": {name: _stats(items, elapsed_s) for name, items in by_target.items()},
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Target backend base URL")
    parser.add_argument(
        "--allow-prod",
        action="store_true",
        help="Explicitly allow targeting production hosts/domains",
    )
    parser.add_argument(
        "--scenario",
        choices=("smoke-public", "analisis-zona", "campo", "informe-pdf", "all"),
        default="smoke-public",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--max-p95-ms", type=float, default=2000.0)
    parser.add_argument("--max-error-rate", type=float, default=0.05)
    parser.add_argument("--allow-429", action="store_true")
    parser.add_argument("--ficha-payload", type=Path)
    parser.add_argument("--campo-token")
    parser.add_argument("--informe-id")
    parser.add_argument("--json-out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if not 1 <= args.concurrency <= MAX_CONCURRENCY:
            raise LoadTestConfigError(
                f"--concurrency must be between 1 and {MAX_CONCURRENCY}, got {args.concurrency}"
            )
        if not 1 <= args.requests <= MAX_REQUESTS:
            raise LoadTestConfigError(
                f"--requests must be between 1 and {MAX_REQUESTS}, got {args.requests}"
            )
        if args.timeout_s <= 0 or args.max_p95_ms <= 0:
            raise LoadTestConfigError("--timeout-s and --max-p95-ms must be positive")
        if not 0.0 <= args.max_error_rate <= 1.0:
            raise LoadTestConfigError("--max-error-rate must be between 0.0 and 1.0")

        base_url = validate_base_url(args.base_url, allow_prod=args.allow_prod)
        bearer_token = os.environ.get("LOAD_TEST_BEARER_TOKEN", "")
        campo_token = args.campo_token or os.environ.get("LOAD_TEST_CAMPO_TOKEN")
        targets = build_targets(
            scenario=args.scenario,
            ficha_payload_path=args.ficha_payload,
            campo_token=campo_token,
            informe_id=args.informe_id,
            bearer_token=bearer_token,
        )
    except LoadTestConfigError as exc:
        print(f"load test configuration error: {exc}", file=sys.stderr)
        return 2

    work_plan = [targets[index % len(targets)] for index in range(args.requests)]
    samples: list[RequestSample] = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [
            pool.submit(
                _execute_one,
                base_url,
                target,
                timeout_s=args.timeout_s,
                allow_429=args.allow_429,
            )
            for target in work_plan
        ]
        for future in as_completed(futures):
            samples.append(future.result())
    elapsed_s = time.perf_counter() - started

    report = summarize_samples(samples, elapsed_s=elapsed_s)
    report["config"] = {
        "base_url": base_url,
        "scenario": args.scenario,
        "concurrency": args.concurrency,
        "requests": args.requests,
        "max_p95_ms": args.max_p95_ms,
        "max_error_rate": args.max_error_rate,
    }

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    overall = report["overall"]
    print(
        f"load-test scenario={args.scenario} requests={overall['total']} "
        f"ok={overall['ok']} errors={overall['errors']} "
        f"error_rate={overall['error_rate']:.4f} p50_ms={overall['p50_ms']:.2f} "
        f"p95_ms={overall['p95_ms']:.2f} p99_ms={overall['p99_ms']:.2f} rps={overall['rps']:.2f}"
    )

    breaches: list[str] = []
    if overall["error_rate"] > args.max_error_rate:
        breaches.append(
            f"error_rate {overall['error_rate']:.4f} exceeds budget {args.max_error_rate:.4f}"
        )
    if overall["p95_ms"] > args.max_p95_ms:
        breaches.append(f"p95_ms {overall['p95_ms']:.2f} exceeds budget {args.max_p95_ms:.2f}")
    if breaches:
        for breach in breaches:
            print(f"BUDGET BREACH: {breach}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
