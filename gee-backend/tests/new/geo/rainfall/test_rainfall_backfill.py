"""Historical baseline backfill orchestrator + CLI (design.md D2).

No real GEE call is ever made: every test either monkeypatches
``tasks.ingest_source_scope``/``tasks._concrete_fetch`` directly (the same
pattern ``test_ingest_ops.py::test_backfill_missing_passes_role_to_ingest_source_scope``
already uses for this exact task), or pre-opens a fake circuit-breaker store
so ``ResilientAdapterState.can_attempt()`` raises BEFORE any provider call
is ever attempted (resilience.py:262) -- the real ``ChirpsV3Adapter``/``ee``
path is never reached either way.
"""

import time

import pytest


def test_backfill_baseline_range_with_empty_years_is_a_safe_no_op(monkeypatch):
    """Boundary: an empty years iterable makes zero provider calls and
    reports a clean, non-stopped, empty completion — never a crash."""
    from app.domains.geo.rainfall import tasks

    calls = []
    monkeypatch.setattr(tasks, "ingest_source_scope", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    result = tasks.backfill_baseline_range("test-asset-empty-years", years=[])

    assert result == {"stopped": False, "completed_years": []}
    assert calls == []


def test_backfill_dedupes_shared_asset_one_fetch_per_year(monkeypatch):
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.adapters.gee_client import asset_name_for

    calls = []

    def fake_ingest(**kwargs):
        calls.append(kwargs)
        return {"intervals": 365}

    monkeypatch.setattr(tasks, "ingest_source_scope", fake_ingest)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    zone_a_asset = asset_name_for("zone", "zone-scope-a")
    zone_b_asset = asset_name_for("zone", "zone-scope-b")
    assert zone_a_asset == zone_b_asset  # two zone scopes share one provider asset

    years = [1991, 1992]
    tasks.backfill_baseline_range(zone_a_asset, years=years)
    tasks.backfill_baseline_range(zone_b_asset, years=years)

    assert len(calls) == len(years)  # fetched once per year for the shared asset, not per scope
    assert {call["year"] for call in calls} == set(years)
    assert all(call["scope_kind"] == "provider_asset" for call in calls)
    assert all(call["scope_id"] == zone_a_asset for call in calls)


def test_backfill_resumes_after_interruption_no_refetch(monkeypatch):
    from app.domains.geo.rainfall import tasks

    calls = []

    def fake_ingest(**kwargs):
        calls.append(kwargs)
        return {"intervals": 365}

    monkeypatch.setattr(tasks, "ingest_source_scope", fake_ingest)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    asset = "test-asset-resume-after-interruption"
    first = tasks.backfill_baseline_range(asset, years=[1993, 1994, 1995])
    assert first == {"stopped": False, "completed_years": [1993, 1994, 1995]}
    assert len(calls) == 3

    calls.clear()  # only NEW provider calls should be counted from here

    second = tasks.backfill_baseline_range(asset, years=[1993, 1994, 1995, 1996])
    assert second == {"stopped": False, "completed_years": [1993, 1994, 1995, 1996]}
    assert len(calls) == 1
    assert calls[0]["year"] == 1996


def test_backfill_stops_labelled_on_circuit_open(monkeypatch):
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.adapters import resilience
    from app.domains.geo.rainfall.adapters.resilience import CircuitState, ResilientAdapterState

    class _PreOpenedCircuitStore:
        """Drop-in ``CircuitStore`` with role="historical" already OPEN --
        ``can_attempt()`` raises before ``_concrete_fetch``'s real adapter
        (and therefore ``ee``) is ever invoked."""

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def read(self, role, default=None):
            del role, default
            now = time.monotonic()
            return ResilientAdapterState(
                failure_threshold=3,
                recovery_seconds=300.0,
                consecutive_failures=3,
                circuit=CircuitState.OPEN,
                opened_at=now,
                last_failure_at=now,
                next_attempt_at=now + 300.0,
            )

        def write(self, role, state) -> None:
            del role, state

    monkeypatch.setattr(resilience, "RedisCircuitStore", _PreOpenedCircuitStore)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    result = tasks.backfill_baseline_range("test-asset-circuit-open", years=[1991, 1992])

    assert result == {
        "stopped": True,
        "reason": "circuit_open",
        "year": 1991,
        "completed_years": [],
    }


def test_backfill_stops_labelled_on_adapter_error(monkeypatch):
    from app.domains.geo.rainfall import tasks

    def failing_fetch(**_kwargs):
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(tasks, "_concrete_fetch", lambda _source_id: failing_fetch)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)  # skip retry backoff + pace sleep

    result = tasks.backfill_baseline_range("test-asset-adapter-error", years=[1991, 1992])

    assert result == {
        "stopped": True,
        "reason": "adapter_error",
        "year": 1991,
        "completed_years": [],
    }


# ---------------------------------------------------------------------------
# backfill_cli.py — one-shot runner
# ---------------------------------------------------------------------------


def test_backfill_cli_main_delegates_to_backfill_baseline_range(monkeypatch):
    from app.domains.geo.rainfall import backfill_cli

    captured = {}

    def fake_backfill_baseline_range(asset, *, years, source_id):
        captured["asset"] = asset
        captured["years"] = list(years)
        captured["source_id"] = source_id
        return {"stopped": False, "completed_years": captured["years"]}

    monkeypatch.setattr(backfill_cli, "backfill_baseline_range", fake_backfill_baseline_range)

    exit_code = backfill_cli.main(
        ["--asset", "zona_cc_ampliada", "--start-year", "1991", "--end-year", "1992"]
    )

    assert exit_code == 0
    assert captured["asset"] == "zona_cc_ampliada"
    assert captured["years"] == [1991, 1992]
    assert captured["source_id"] == "chirps-v3-final"


def test_backfill_cli_main_reports_a_labelled_stop_as_nonzero_exit(monkeypatch, capsys):
    from app.domains.geo.rainfall import backfill_cli

    def fake_stop(_asset, *, years, source_id):
        del years, source_id
        return {"stopped": True, "reason": "circuit_open", "year": 1991, "completed_years": []}

    monkeypatch.setattr(backfill_cli, "backfill_baseline_range", fake_stop)

    exit_code = backfill_cli.main(["--start-year", "1991", "--end-year", "1991"])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "circuit_open" in err


def test_backfill_cli_help_documents_the_recovery_window_wait_out_rule(capsys):
    from app.domains.geo.rainfall import backfill_cli

    with pytest.raises(SystemExit):
        backfill_cli.main(["--help"])

    out = capsys.readouterr().out
    assert "300s" in out
    assert "recovery" in out.lower()
