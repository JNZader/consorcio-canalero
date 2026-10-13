"""OBS-02 / GEE-02: 429 counter, per-route latency, and GEE call histogram."""

from __future__ import annotations

from app.core.metrics import (
    observe_gee_call,
    observe_http_request,
    render_prometheus,
    reset_metrics,
    route_label,
)


def setup_function() -> None:
    reset_metrics()


def test_route_label_collapses_ids() -> None:
    raw = "/api/v2/denuncias/11111111-1111-1111-1111-111111111111/fotos/42"
    assert route_label(raw) == "/api/v2/denuncias/{id}/fotos/{n}"


def test_429_and_latency_are_scrapable() -> None:
    observe_http_request("GET", "/api/v2/public/layers/catalog", 200, 0.02)
    observe_http_request("POST", "/api/v2/auth/jwt/login", 429, 0.01)
    observe_gee_call("getInfo", 1.2)

    body = render_prometheus()
    assert 'http_responses_429_total{method="POST",path="/api/v2/auth/jwt/login"} 1' in body
    assert (
        'http_requests_total{method="GET",path="/api/v2/public/layers/catalog",status="200"} 1'
        in body
    )
    assert "http_request_duration_seconds_bucket{" in body
    assert 'gee_call_duration_seconds_bucket{operation="getInfo",le="2.5"}' in body
    assert 'gee_call_duration_seconds_bucket{operation="getInfo",le="+Inf"} 1' in body
    assert "gee_call_duration_seconds_count{" in body


def test_histogram_buckets_are_cumulative() -> None:
    observe_http_request("GET", "/live-not-really", 200, 0.2)
    body = render_prometheus()
    assert (
        'http_request_duration_seconds_bucket{method="GET",path="/live-not-really",le="0.1"} 0'
        in body
    )
    assert (
        'http_request_duration_seconds_bucket{method="GET",path="/live-not-really",le="0.25"} 1'
        in body
    )
    assert (
        'http_request_duration_seconds_bucket{method="GET",path="/live-not-really",le="+Inf"} 1'
        in body
    )
