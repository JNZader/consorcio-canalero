"""Tests for dual-host WFS fallback in ``fetch_layer``.

IDECor exposes the same WFS layers on two hosts:

- ``gn-idecor.mapascordoba.gob.ar`` — primary (validated during exploration,
  responsive in ~5s).
- ``idecor-ws.mapascordoba.gob.ar`` — fallback (observed flaky, 504 Gateway
  Timeout during the first real ETL run on 2026-04-20).

Contract for dual-host fallback (design drift captured in task 0.24a):

- ``WFS_HOSTS`` is iterated in order within EACH tenacity-style attempt.
- Per attempt: host 1 is tried first; on HTTP/connection error, host 2 is
  tried immediately — no backoff between hosts inside the same attempt.
- Only after BOTH hosts fail within an attempt does the failure count toward
  the 3-attempt budget; the existing 2s / 4s exponential backoff is preserved
  BETWEEN attempts.
- The successful host is recorded in the structured log line so operators can
  spot a silent degradation of host 1 before it becomes a total outage.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
import requests

from scripts.etl_pilar_verde.constants import WFS_HOSTS, build_wfs_url
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


class TestWfsHostCatalog:
    def test_primary_host_is_gn_idecor(self):
        """gn-idecor must be FIRST — exploration validated it as the live host."""
        assert WFS_HOSTS[0] == "gn-idecor.mapascordoba.gob.ar"

    def test_fallback_host_is_idecor_ws(self):
        """idecor-ws is the historical default — kept as fallback."""
        assert WFS_HOSTS[1] == "idecor-ws.mapascordoba.gob.ar"

    def test_exactly_two_hosts(self):
        assert len(WFS_HOSTS) == 2

    def test_build_wfs_url_shape(self):
        url = build_wfs_url("gn-idecor.mapascordoba.gob.ar")
        assert url == "https://gn-idecor.mapascordoba.gob.ar/geoserver/idecor/ows"


class TestFetchLayerDualHost:
    def test_primary_host_succeeds_fallback_not_called(self, mocker):
        ok_payload = {"type": "FeatureCollection", "features": []}
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            return_value=_ok_response(ok_payload),
        )
        mocker.patch("scripts.etl_pilar_verde.wfs.time.sleep", return_value=None)

        result = fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert result == ok_payload
        assert mock_get.call_count == 1
        called_url = mock_get.call_args_list[0][0][0]
        assert "gn-idecor.mapascordoba.gob.ar" in called_url

    def test_primary_504_fallback_200_same_attempt(self, mocker, caplog):
        """Host 1 504s, host 2 returns 200 — single attempt, no backoff."""
        ok_payload = {"type": "FeatureCollection", "features": [{"id": 1}]}
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            side_effect=[
                _error_response(504),
                _ok_response(ok_payload),
            ],
        )
        sleep_mock = mocker.patch(
            "scripts.etl_pilar_verde.wfs.time.sleep", return_value=None
        )

        with caplog.at_level(logging.INFO, logger="scripts.etl_pilar_verde.wfs"):
            result = fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert result == ok_payload
        # Two HTTP calls total, both inside the FIRST attempt.
        assert mock_get.call_count == 2
        # Host order: gn-idecor first, idecor-ws second.
        first_url = mock_get.call_args_list[0][0][0]
        second_url = mock_get.call_args_list[1][0][0]
        assert "gn-idecor.mapascordoba.gob.ar" in first_url
        assert "idecor-ws.mapascordoba.gob.ar" in second_url
        # NO backoff between hosts inside the same attempt.
        assert sleep_mock.call_count == 0
        # The success log line must mention the host that actually served us.
        success_logs = [rec.message for rec in caplog.records if "ok" in rec.message]
        assert any("idecor-ws" in msg for msg in success_logs), success_logs

    def test_both_hosts_fail_attempt_counts_once(self, mocker):
        """Both hosts 504 on a single attempt → 1 attempt consumed, 2s backoff applied."""
        ok_payload = {"type": "FeatureCollection", "features": []}
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            side_effect=[
                _error_response(504),  # attempt 1, host 1
                _error_response(504),  # attempt 1, host 2
                _ok_response(ok_payload),  # attempt 2, host 1 OK
            ],
        )
        sleep_mock = mocker.patch(
            "scripts.etl_pilar_verde.wfs.time.sleep", return_value=None
        )

        result = fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert result == ok_payload
        assert mock_get.call_count == 3
        # 2s backoff once (between attempts 1 and 2) — NOT between hosts.
        assert [c.args[0] for c in sleep_mock.call_args_list] == [2]

    def test_both_hosts_fail_all_attempts_raises(self, mocker):
        """3 attempts × 2 hosts = 6 HTTP calls total before raising."""
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            side_effect=[_error_response(504)] * 6,
        )
        sleep_mock = mocker.patch(
            "scripts.etl_pilar_verde.wfs.time.sleep", return_value=None
        )

        with pytest.raises(requests.HTTPError):
            fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert mock_get.call_count == 6
        # Backoff between full attempts: 2s, 4s (no backoff between hosts inside an attempt).
        assert [c.args[0] for c in sleep_mock.call_args_list] == [2, 4]

    def test_connection_error_on_primary_falls_back(self, mocker):
        ok_payload = {"type": "FeatureCollection", "features": []}
        mock_get = mocker.patch(
            "scripts.etl_pilar_verde.wfs.requests.get",
            side_effect=[
                requests.ConnectionError("DNS failure on gn-idecor"),
                _ok_response(ok_payload),
            ],
        )
        mocker.patch("scripts.etl_pilar_verde.wfs.time.sleep", return_value=None)

        result = fetch_layer("idecor:bpa_2025", bbox_22174=(0, 0, 100, 100))

        assert result == ok_payload
        assert mock_get.call_count == 2
        assert "idecor-ws" in mock_get.call_args_list[1][0][0]
