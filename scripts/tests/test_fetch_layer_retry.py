"""Tests for ``fetch_layer`` — WFS fetch with exponential backoff.

Per design §3 + task 0.24a: exactly 3 attempts with 2s / 4s waits BETWEEN
attempts, and within each attempt we iterate ``WFS_HOSTS`` (gn-idecor →
idecor-ws) with no backoff between hosts.  These tests exercise the
single-host happy path and the 3-attempt exhaustion.  Dual-host behaviour has
its own suite in ``test_fetch_layer_dual_host.py``.

We do NOT install ``requests-mock`` (not in venv); instead we stub
``requests.get`` via ``pytest-mock`` and assert call count.  Because each
attempt now fires up to 2 HTTP calls (one per host), a "single attempt
exhausted" scenario must produce TWO error responses to reach the backoff.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
import requests

from scripts.etl_pilar_verde.wfs import fetch_layer


def _ok_response(payload: dict) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    return response


def _error_response(status_code: int) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = status_code

    def _raise():
        raise requests.HTTPError(f"HTTP {status_code}", response=response)

    response.raise_for_status = _raise
    response.json.side_effect = AssertionError(
        "json() should not be called on errored response"
    )
    return response


class TestFetchLayerRetry:
    def test_happy_path_calls_once(self, mocker):
        ok_payload = {"type": "FeatureCollection", "features": []}
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            return_value=_ok_response(ok_payload),
        )
        # Disable sleep so tests run fast.
        mocker.patch("scripts.etl_pilar_verde.wfs.time.sleep", return_value=None)

        result = fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert result == ok_payload
        assert mock_get.call_count == 1

    def test_503_then_success_retries_and_returns_payload(self, mocker):
        """Attempt 1: both hosts 503; attempt 2: host 1 succeeds.

        Sleep budget is one 2s wait — the single inter-attempt backoff.  The
        per-attempt host fallback is silent (no sleep between hosts).
        """
        ok_payload = {"type": "FeatureCollection", "features": [{"id": 1}]}
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            side_effect=[
                _error_response(503),  # attempt 1, host 1 (gn-idecor)
                _error_response(503),  # attempt 1, host 2 (idecor-ws)
                _ok_response(ok_payload),  # attempt 2, host 1
            ],
        )
        sleep_mock = mocker.patch(
            "scripts.etl_pilar_verde.wfs.time.sleep", return_value=None
        )

        result = fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert result == ok_payload
        assert mock_get.call_count == 3
        # Only the inter-attempt backoff fires (between attempts 1 and 2).
        assert sleep_mock.call_args_list == [call(2)]

    def test_exhausts_retries_and_raises(self, mocker):
        """3 attempts × 2 hosts = 6 error responses before we give up."""
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            side_effect=[_error_response(503)] * 6,
        )
        mocker.patch("scripts.etl_pilar_verde.wfs.time.sleep", return_value=None)

        with pytest.raises(requests.HTTPError):
            fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert mock_get.call_count == 6

    def test_connection_error_also_retries(self, mocker):
        ok_payload = {"type": "FeatureCollection", "features": []}
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            side_effect=[
                requests.ConnectionError("DNS failure"),
                _ok_response(ok_payload),
            ],
        )
        mocker.patch("scripts.etl_pilar_verde.wfs.time.sleep", return_value=None)

        result = fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert result == ok_payload
        assert mock_get.call_count == 2

    def test_builds_bbox_cql_filter_in_epsg_22174(self, mocker):
        ok_payload = {"type": "FeatureCollection", "features": []}
        captured_params: dict[str, str] = {}

        def _capture(url, params=None, timeout=None):
            captured_params.update(params or {})
            return _ok_response(ok_payload)

        mocker.patch("scripts.etl_pilar_verde.wfs.requests.get", side_effect=_capture)
        mocker.patch("scripts.etl_pilar_verde.wfs.time.sleep", return_value=None)

        fetch_layer("idecor:bpa_2025", bbox_22174=(4400000, 6400000, 4500000, 6500000))

        # Follows memory #733 pattern: CQL_FILTER with BBOX(geom,...,'EPSG:22174').
        assert "CQL_FILTER" in captured_params
        cql = captured_params["CQL_FILTER"]
        assert cql.startswith("BBOX(geom,")
        assert "EPSG:22174" in cql
        # Response is reprojected back to EPSG:4326 for the static bundle.
        assert captured_params.get("srsName") == "EPSG:4326"
        assert captured_params.get("typeNames") == "idecor:bpa_2025"
        assert captured_params.get("outputFormat") == "application/json"
