"""The six antecedent reference metrics (SDD S2a, design.md D1/D4-D9).

Pure: ``build_snapshot`` over hand-built daily series, no ``Session``, no
network. The real-PG half of this slice -- that the metrics consume the value
``tasks`` read and CONTAINED, never a second read of their own -- lives in
``test_rainfall_baseline.py`` (task 3.0), because only a database can plant the
duplicate that proves it.

D0 governs every assertion below::

    total is not None  <=>  matched_slots == expected_slots  <=>  completeness == 1.0

so no test here asserts a reason whose domain D0 proves empty. That was r1's
CRITICAL-1: a "total present AND completeness < 0.95" row that the code can
never reach, scheduled as a RED test that would have been made to pass by
adding the dead branch it asserted.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.geo.rainfall.scope import AnalysisScope

# The persisted baseline span (repository.BASELINE_SPAN_START/END, D2), passed
# to `build_snapshot` as dates. It is passed rather than imported INTO
# `compute.py` because `repository.py` imports `compute.py` (repository.py:16),
# so the reverse import would be a cycle -- and because a span inferred from
# the values themselves would promote a HOLE at the edge of the record into
# structural underivability, hiding exactly the loss D4 exists to disclose.
_SPAN = (date(1991, 1, 1), date(2021, 1, 1))

# A sentinel, because ``None`` is a MEANINGFUL value for the baseline
# arguments below (precedence row 2) and must not be read as "use the default".
_UNSET = object()

_ZONE = AnalysisScope(kind="zone", id="z1", version="v1", regional_estimate=False)
_BASIN = AnalysisScope(kind="basin", id="b1", version="v1", regional_estimate=False)

_REFERENCE_KEYS = (
    "d7_normal",
    "d7_percentile",
    "d30_normal",
    "d30_percentile",
    "d90_normal",
    "d90_percentile",
)

# The selected build: daily rows through 2024-06-14, `now` on 2024-06-15, so
# `window_end` clips to 2024-06-15T00:00 and every antecedent window ends
# there. The anchor -- the last day the windows actually cover -- is therefore
# 14 June, and a 90-day window ending 14 June starts on 17 March, inside the
# same calendar year: all thirty baseline years are derivable, which keeps the
# arithmetic below closed-form.
_NOW = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
_LAST_SELECTED_DAY = date(2024, 6, 14)
_ANCHOR = date(2024, 6, 14)
_SELECTED_MM = 5.5


def _batch(**overrides) -> dict:
    payload = {
        "source_id": "chirps-v3-final",
        "provider_revision": "v3-final",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-final"},
        "discrepancies": [],
        "checksum": "sha256:fixture",
    }
    payload.update(overrides)
    return payload


def _selected_intervals(
    *,
    first: date = date(2024, 1, 1),
    last: date = _LAST_SELECTED_DAY,
    skip: set[date] | None = None,
) -> list[tuple[datetime, datetime, float]]:
    """One daily row per day in ``[first, last]``, minus *skip*.

    *skip* plants a HOLE. Under D0 a hole anywhere inside a window makes that
    window's total ``None`` -- ``temporal.rolling_total`` demands the exact slot
    tuple -- which is the only reachable way to exercise precedence row 4.
    """
    skipped = skip or set()
    rows = []
    day = first
    while day <= last:
        if day not in skipped:
            start = datetime(day.year, day.month, day.day, tzinfo=UTC)
            rows.append((start, start + timedelta(days=1), _SELECTED_MM))
        day += timedelta(days=1)
    return rows


def _dense_baseline(
    *, drop: set[date] | None = None, years: range = range(1991, 2021)
) -> list[tuple[date, float]]:
    """A complete daily baseline over the span, one value per day.

    Year ``Y`` rains ``Y - 1990`` mm every day, so a ``days``-long window in
    year ``Y`` totals ``days * (Y - 1990)``: the normal is ``days * 15.5`` and
    every rank below is computable by hand rather than by re-running the
    implementation inside the test.
    """
    dropped = drop or set()
    rows: list[tuple[date, float]] = []
    for year in years:
        value = float(year - 1990)
        day = date(year, 1, 1)
        while day.year == year:
            if day not in dropped:
                rows.append((day, value))
            day += timedelta(days=1)
    return rows


def _snapshot(
    *,
    scope: AnalysisScope = _ZONE,
    role: str = "historical",
    source_id: str = "chirps-v3-final",
    intervals=None,
    window_baseline=_UNSET,
    window_baseline_unavailable_reason: str | None = None,
    window_baseline_span=_SPAN,
    now: datetime = _NOW,
    year: int = 2024,
) -> dict:
    from app.domains.geo.rainfall.compute import BASELINE_SCOPE_UNMAPPED, build_snapshot

    kwargs = {
        "scope": scope,
        "year": year,
        "role": role,
        "source_id": source_id,
        "intervals": _selected_intervals() if intervals is None else intervals,
        "batch": _batch(source_id=source_id),
        "now": now,
        "window_baseline": _dense_baseline() if window_baseline is _UNSET else window_baseline,
        "window_baseline_unavailable_reason": (
            BASELINE_SCOPE_UNMAPPED
            if window_baseline_unavailable_reason is None
            else window_baseline_unavailable_reason
        ),
        "window_baseline_span": window_baseline_span,
    }
    return build_snapshot(**kwargs)


# ---------------------------------------------------------------------------
# 3.12 / D1 — shape and order
# ---------------------------------------------------------------------------


def test_the_six_reference_metrics_are_flat_siblings_emitted_after_their_total():
    """3.12 (D1): flat siblings inside ``antecedents``, metric key == policy
    key, in total -> normal -> percentile order per window.

    Order is asserted, not just membership: the ``snapshot`` column is
    ``postgresql.JSON`` (models.py), not JSONB, so insertion order genuinely
    survives the round trip and is what a reader sees in the fold. Nesting the
    pair inside ``d30`` was rejected because ``MetricResult`` is
    ``extra="forbid"``, which would make the TOTAL itself
    ``metric_contract_invalid`` -- a regression on a working metric.
    """
    antecedents = _snapshot()["antecedents"]

    assert list(antecedents) == [
        "d7",
        "d7_normal",
        "d7_percentile",
        "d30",
        "d30_normal",
        "d30_percentile",
        "d90",
        "d90_normal",
        "d90_percentile",
    ]
    for name, metric in antecedents.items():
        assert metric["metric"] == name


def test_the_metric_keys_are_exactly_the_policy_keys():
    """3.12/3.13: the wire name IS the ``RAINFALL_METRIC_POLICY`` key.

    A metric with no policy entry is served as ``policy_threshold_unset``
    (policy.py:163), so a name that disagrees with the policy dict by one
    character suppresses the metric on every path with a reason that describes
    the policy rather than the evidence.
    """
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY

    for key in _REFERENCE_KEYS:
        assert key in RAINFALL_METRIC_POLICY.minimum_coverage_by_metric, key
        assert key in RAINFALL_METRIC_POLICY.minimum_quality_by_metric, key


def test_the_six_policy_entries_are_pinned_to_the_compute_floor_and_the_revision_moved():
    """3.13 (D4, LI2A-003 re-run one scale down): each of the six entries, in
    BOTH dicts, is exactly ``MIN_WINDOW_BASELINE_YEARS / 30``.

    ``quality["score"]`` for these six IS ``completeness``, which is the
    eligible/derivable baseline-YEAR fraction -- so any value above 20/30
    silently dominates the compute floor and relabels the whole reachable 20-26
    band as ``coverage_below_threshold``: a sample-size problem wearing a
    coverage label, with ``baseline_years_below_minimum`` never reaching a
    reader. Computed here rather than written as a literal, so the pin cannot
    drift from the floor it is pinned to, and asserted on BOTH dicts because
    ``apply_metric_policy`` would otherwise re-suppress the same band under
    ``quality_below_threshold`` instead -- the same misattribution, a different
    label.

    The revision bump rides along: without it, ``persist_revision``'s
    ``ON CONFLICT DO NOTHING`` discards the enriched envelope for every key
    whose evidence has not moved, and the six metrics reach nobody.
    """
    from app.domains.geo.rainfall.compute import MIN_WINDOW_BASELINE_YEARS
    from app.domains.geo.rainfall.policy import (
        RAINFALL_METRIC_POLICY,
        RAINFALL_METRIC_POLICY_REVISION,
    )

    expected = MIN_WINDOW_BASELINE_YEARS / 30
    for key in _REFERENCE_KEYS:
        assert RAINFALL_METRIC_POLICY.minimum_coverage_by_metric[key] == expected, key
        assert RAINFALL_METRIC_POLICY.minimum_quality_by_metric[key] == expected, key

    assert RAINFALL_METRIC_POLICY_REVISION == "rainfall-v2-2026-08-antecedent-ref"
    assert RAINFALL_METRIC_POLICY.revision == RAINFALL_METRIC_POLICY_REVISION


def test_the_always_visible_collapsed_header_is_not_grown_by_this_slice():
    """3.12: ``ANTECEDENT_ORDER`` (RainfallDetailPanel.tsx) drives the
    always-visible collapsed header from an explicit list of THREE. The
    answer-surface requirement holds by construction only while that list is
    not extended, so the guard lives here, in the slice that adds the keys.
    """
    from pathlib import Path

    panel = (
        Path(__file__).resolve().parents[4].parent
        / "consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx"
    )
    source = panel.read_text(encoding="utf-8")
    block = source.split("const ANTECEDENT_ORDER", 1)[1].split("];", 1)[0]
    assert block.count("{ key:") == 3, block
    for key in _REFERENCE_KEYS:
        assert key not in block, key


# ---------------------------------------------------------------------------
# 3.1 / 3.2 / 3.3 — the D0 biconditional and the reachable selected-evidence row
# ---------------------------------------------------------------------------


def test_the_d0_biconditional_binds_every_window():
    """3.1 (D6 "guard against rot"): for EVERY window,
    ``total is None`` <=> ``percentile.reason == selected_evidence_below_threshold``.

    Asserted as a biconditional over all three windows in ONE test, and over a
    snapshot where the two sides genuinely differ -- a hole 20 days back leaves
    d7 whole while d30 and d90 are not -- so a coincidence cannot satisfy it.
    If ``temporal.rolling_total``'s exactness is ever relaxed, the pair fails
    together instead of one silently outliving the other.
    """
    from app.domains.geo.rainfall.compute import SELECTED_EVIDENCE_BELOW_THRESHOLD

    hole = _LAST_SELECTED_DAY - timedelta(days=20)
    antecedents = _snapshot(intervals=_selected_intervals(skip={hole}))["antecedents"]

    outcomes = set()
    for window in ("d7", "d30", "d90"):
        total_absent = antecedents[window]["value"] is None
        percentile = antecedents[f"{window}_percentile"]
        assert total_absent == (percentile["reason"] == SELECTED_EVIDENCE_BELOW_THRESHOLD), window
        outcomes.add(total_absent)

    # Both directions were actually exercised, not just the easy one.
    assert outcomes == {True, False}


def test_a_hole_inside_the_selected_window_suppresses_the_percentile_and_never_the_normal():
    """3.2 (spec R2 S4): a hole in the MIDDLE of the selected 30-day window
    suppresses the total with ``antecedent_window_incomplete`` (compute's single
    existing reason for an absent total), suppresses the percentile with
    ``selected_evidence_below_threshold``, and leaves the NORMAL served --
    a baseline average ranks nothing, so the selected window's holes cannot
    bias it.

    This test REPLACES r1's "total present and completeness < 0.95" case, whose
    domain D0 proves empty.
    """
    hole = _LAST_SELECTED_DAY - timedelta(days=20)
    antecedents = _snapshot(intervals=_selected_intervals(skip={hole}))["antecedents"]

    assert antecedents["d30"]["state"] == "suppressed"
    assert antecedents["d30"]["value"] is None
    assert antecedents["d30"]["reason"] == "antecedent_window_incomplete"

    assert antecedents["d30_percentile"]["state"] == "suppressed"
    assert antecedents["d30_percentile"]["value"] is None
    assert antecedents["d30_percentile"]["reason"] == "selected_evidence_below_threshold"

    assert antecedents["d30_normal"]["state"] == "available"
    assert antecedents["d30_normal"]["value"] == pytest.approx(30 * 15.5)

    # d7 is whole, twenty days from the hole: its pair is untouched.
    assert antecedents["d7"]["state"] == "available"
    assert antecedents["d7_percentile"]["state"] == "available"


def test_antecedent_total_unavailable_appears_nowhere_in_the_tree():
    """3.3: r1's ``antecedent_total_unavailable`` is DELETED, not demoted.

    ``_antecedent_metric`` emits exactly one reason for an absent total
    (``antecedent_window_incomplete``), covering both the holed window and the
    unsupported-cadence path, so a second reason string would have an empty
    domain too -- and a dead branch against a hypothetical future reason is how
    r1's defect was born.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[4].parent
    offenders = [
        path
        for path in list((root / "gee-backend").rglob("*.py"))
        + list((root / "consorcio-web/src").rglob("*.ts"))
        + list((root / "consorcio-web/src").rglob("*.tsx"))
        if "venv" not in path.parts
        and "node_modules" not in path.parts
        and path.name != Path(__file__).name
        and "antecedent_total_unavailable" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# ---------------------------------------------------------------------------
# 3.4 / 3.5 — the Feb-29 structural suppression, for D5's CORRECTED reason
# ---------------------------------------------------------------------------


def test_a_february_29_anchor_suppresses_structurally_while_the_policy_entry_passes():
    """3.4 (D5, corrected): a 29 February anchor yields 8 derivable leap years;
    8 < ``MIN_WINDOW_BASELINE_YEARS`` = 20, so both reference metrics suppress
    with ``baseline_years_below_minimum``.

    And -- the half r1 got wrong -- the 20/30 POLICY entry *passes* on this
    path, because ``completeness`` here is 8/8 = 1.0. The compute floor is
    therefore the SOLE gate on 29 February. Asserted because a design that is
    right for the wrong reason is a design the next reader will "simplify".
    """
    from app.domains.geo.rainfall.compute import MIN_WINDOW_BASELINE_YEARS
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY, apply_metric_policy

    assert MIN_WINDOW_BASELINE_YEARS == 20

    antecedents = _snapshot(
        intervals=_selected_intervals(first=date(2023, 12, 1), last=date(2024, 2, 29)),
        now=datetime(2024, 3, 1, 12, 0, tzinfo=UTC),
    )["antecedents"]

    for key in _REFERENCE_KEYS:
        metric = antecedents[key]
        assert metric["state"] == "suppressed", key
        assert metric["reason"] == "baseline_years_below_minimum", key
        assert metric["quality"]["baseline_years_derivable"] == 8, key
        assert metric["completeness"] == pytest.approx(1.0), key

        # The policy entry does NOT fire here: 8/8 clears 20/30 comfortably.
        # Probed with a value substituted in, since a `None` value is
        # `metric_value_unavailable` for reasons that have nothing to do with
        # the threshold under test.
        applied = apply_metric_policy(
            RAINFALL_METRIC_POLICY,
            key,
            value=1.0,
            coverage=metric["coverage"],
            quality_score=metric["quality"]["score"],
            completeness=metric["completeness"],
        )
        assert applied.state == "available", (key, applied)


def test_the_window_floor_is_a_constant_of_its_own_and_not_the_annual_one():
    """3.5: ``MIN_WINDOW_BASELINE_YEARS`` is distinct from
    ``MIN_BASELINE_YEARS`` so the annual and window floors can never be moved
    as one by accident. They happen to share the value 20 today; they are two
    names, and the day one moves the other must not follow silently.
    """
    from app.domains.geo.rainfall import compute

    # Object identity proves nothing here -- CPython interns small ints, so any
    # comparison between two 20s is decided by the interpreter, not by the
    # source. Only the source can show two independent assignments.
    source = __import__("inspect").getsource(compute)
    assert "MIN_WINDOW_BASELINE_YEARS = 20" in source
    assert "MIN_BASELINE_YEARS = 20" in source


# ---------------------------------------------------------------------------
# 3.6 — the denominator (D4)
# ---------------------------------------------------------------------------


def test_completeness_is_the_eligible_over_derivable_year_fraction_and_coverage_equals_it():
    """3.6 (D4): ``completeness = len(eligible) / len(derivable_years)`` -- the
    eligible/derivable YEAR fraction, not ``matched_days / expected_days`` --
    and ``coverage == completeness``.

    Both are asserted, and asserted EQUAL, because ``apply_metric_policy``
    compares the threshold against BOTH (policy.py:166). Setting coverage to
    the annual path's per-year day completeness would be a constant 1.0 under
    complete-or-nothing, quietly voiding half the policy gate.

    One baseline year (1995) loses one day inside its d30 window, so under
    complete-or-nothing that whole year drops out of the numerator: 29/30. The
    day-level fraction for that year would have been 29/30 as well by
    coincidence at d30, so the drop is asserted on d7 too, where the day-level
    fraction would be 6/7 and the year fraction is again 29/30.
    """
    dropped_day = date(1995, 6, 10)
    antecedents = _snapshot(window_baseline=_dense_baseline(drop={dropped_day}))["antecedents"]

    for window in ("d7", "d30", "d90"):
        for suffix in ("normal", "percentile"):
            metric = antecedents[f"{window}_{suffix}"]
            assert metric["completeness"] == pytest.approx(29 / 30), (window, suffix)
            assert metric["coverage"] == metric["completeness"], (window, suffix)
            assert metric["quality"]["score"] == metric["completeness"], (window, suffix)
            assert 1995 not in metric["quality"]["eligible_years"], (window, suffix)
            assert metric["quality"]["baseline_years_derivable"] == 30, (window, suffix)

    # 29 eligible years still clears the floor of 20, so both are SERVED -- the
    # exclusion moves the NUMBER, which is the bias D4 exists to prevent, and
    # the disclosed completeness is where the reader can see it happened.
    assert antecedents["d7_normal"]["state"] == "available"
    assert antecedents["d7_normal"]["value"] != pytest.approx(7 * 15.5)


# ---------------------------------------------------------------------------
# 3.7 — precedence, row by row AND in order (D6)
# ---------------------------------------------------------------------------


def test_reason_precedence_is_applied_in_order_row_by_row():
    """3.7 (D6): five rows, asserted in ORDER. Each case below matches its own
    row AND at least one LATER row, so a case reporting the later reason proves
    the precedence has been reordered -- which is the failure mode a
    outcome-only test cannot see.

    | # | condition                 | normal                        | percentile                        |
    |---|---------------------------|-------------------------------|-----------------------------------|
    | 1 | scope is not `zone`       | reference_scope_unsupported   | same                              |
    | 2 | baseline unresolvable     | baseline_scope_unmapped /     | same                              |
    |   |                           | baseline_evidence_invalid     |                                   |
    | 3 | eligible years < 20       | baseline_years_below_minimum  | same                              |
    | 4 | antecedent total is None  | SERVED                        | selected_evidence_below_threshold |
    | 5 | otherwise                 | window_mean                   | seasonal Weibull rank             |
    """
    from app.domains.geo.rainfall.compute import (
        BASELINE_EVIDENCE_INVALID,
        REFERENCE_SCOPE_UNSUPPORTED,
    )

    thin = _dense_baseline(years=range(1991, 2001))  # ten years: below the floor
    holed = _selected_intervals(skip={_LAST_SELECTED_DAY - timedelta(days=20)})

    # Row 1 wins over rows 2, 3 and 4 simultaneously.
    row1 = _snapshot(
        scope=_BASIN,
        window_baseline=None,
        window_baseline_unavailable_reason=BASELINE_EVIDENCE_INVALID,
        intervals=holed,
    )["antecedents"]
    for key in _REFERENCE_KEYS:
        assert row1[key]["reason"] == REFERENCE_SCOPE_UNSUPPORTED, key

    # Row 2 wins over rows 3 and 4.
    row2 = _snapshot(
        window_baseline=None,
        window_baseline_unavailable_reason=BASELINE_EVIDENCE_INVALID,
        intervals=holed,
    )["antecedents"]
    for key in _REFERENCE_KEYS:
        assert row2[key]["reason"] == BASELINE_EVIDENCE_INVALID, key

    # Row 2's OTHER cause keeps its own name: an unmapped scope is not invalid
    # evidence, and telling a reader the wrong one is the LI2A-003 defect.
    row2b = _snapshot(window_baseline=None)["antecedents"]
    for key in _REFERENCE_KEYS:
        assert row2b[key]["reason"] == "baseline_scope_unmapped", key

    # Row 3 wins over row 4.
    row3 = _snapshot(window_baseline=thin, intervals=holed)["antecedents"]
    for key in _REFERENCE_KEYS:
        assert row3[key]["reason"] == "baseline_years_below_minimum", key

    # Row 4: the normal is SERVED while the percentile is not.
    row4 = _snapshot(intervals=holed)["antecedents"]
    assert row4["d30_normal"]["state"] == "available"
    assert row4["d30_percentile"]["reason"] == "selected_evidence_below_threshold"

    # Row 5.
    row5 = _snapshot()["antecedents"]
    for key in _REFERENCE_KEYS:
        assert row5[key]["state"] == "available", key
        assert row5[key]["reason"] is None, key


# ---------------------------------------------------------------------------
# 3.8 — D7: zone-only, per metric, no new root key
# ---------------------------------------------------------------------------


def test_off_zone_suppresses_the_reference_and_leaves_the_totals_untouched():
    """3.8 (spec R5 S2): off ``zone``, each ``normal`` and ``percentile`` is
    suppressed with ``reference_scope_unsupported`` while the antecedent
    MILLIMETRE TOTALS are unaffected -- they are not zone-limited and must not
    be degraded by a limit that does not apply to them.
    """
    antecedents = _snapshot(scope=_BASIN)["antecedents"]

    for key in _REFERENCE_KEYS:
        assert antecedents[key]["state"] == "suppressed", key
        assert antecedents[key]["reason"] == "reference_scope_unsupported", key
        assert antecedents[key]["value"] is None, key

    for window in ("d7", "d30", "d90"):
        assert antecedents[window]["state"] == "available", window
        assert antecedents[window]["value"] is not None, window
    assert antecedents["d7"]["value"] == pytest.approx(7 * _SELECTED_MM)


def test_the_zone_limit_is_declared_per_metric_and_adds_no_root_key():
    """3.8 (spec R5 S1, D7 as owner-ratified 2026-08-25): the limit is declared
    on each reference metric's own ``quality``, never as a root flag.

    ``export.py:339`` projects root flags as ANALYSIS-level workbook rows, so a
    root "reference scope: zone" row would state a limit about an analysis
    whose antecedent totals are not zone-limited -- the exact conflation the
    ambiguity named. The root key set is pinned as a literal here rather than
    compared to itself, because ``set(snapshot) <= SNAPSHOT_ROOT_KEYS`` passes
    just as happily after a new key is added to both sides.
    """
    from app.domains.geo.rainfall.service import SNAPSHOT_ROOT_KEYS

    assert SNAPSHOT_ROOT_KEYS == {
        "analysis_revision_id",
        "data_revision",
        "scope",
        "regional_estimate",
        "year",
        "comparison_end",
        "baseline",
        "annual",
        "antecedents",
        "intensity",
        "summary",
        "source_health",
        "metric_policy",
    }

    snapshot = _snapshot()
    assert set(snapshot) <= SNAPSHOT_ROOT_KEYS
    assert not any("scope_unsupported" in key or "reference" in key for key in snapshot)

    for key in _REFERENCE_KEYS:
        assert snapshot["antecedents"][key]["quality"]["reference_scope"] == "zone", key
    # The TOTALS carry no such claim: they are served for every scope.
    for window in ("d7", "d30", "d90"):
        assert "reference_scope" not in snapshot["antecedents"][window]["quality"], window


# ---------------------------------------------------------------------------
# 3.9 / 3.10 / 3.11 — the full field contract (D9), discrepancies, modes (D8)
# ---------------------------------------------------------------------------

_METRIC_FIELDS = {
    "metric",
    "value",
    "unit",
    "state",
    "reason",
    "interval_start",
    "interval_end",
    "coverage",
    "completeness",
    "quality",
    "discrepancies",
    "temporal_state",
    "revision",
    "provenance",
    "fallback_used",
}


def test_every_field_of_the_six_metrics_is_built_explicitly():
    """3.9 (D9): ``MetricResult`` is ``extra="forbid"`` AND forbids nothing
    being omitted, so every field of all six is asserted by value, not by
    presence.

    The interval bounds are the BASELINE envelope -- ``1991-01-01`` to the last
    derivable year's anchor + one day -- mirroring ``annual_normal``
    (compute.py:452-453): the interval must describe the sample the value
    speaks FOR, not the selected window it is compared against. Serving the
    selected window's own bounds here would tell a reader that a thirty-year
    climatology was measured over seven days.
    """
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.schemas import MetricResult

    antecedents = _snapshot()["antecedents"]
    envelope_start = datetime(1991, 1, 1, tzinfo=UTC).isoformat()
    envelope_end = datetime(2020, 6, 15, tzinfo=UTC).isoformat()  # 2020 anchor + 1 day

    for days, window in ((7, "d7"), (30, "d30"), (90, "d90")):
        normal = antecedents[f"{window}_normal"]
        percentile = antecedents[f"{window}_percentile"]

        assert set(normal) == _METRIC_FIELDS
        assert set(percentile) == _METRIC_FIELDS

        assert normal["metric"] == f"{window}_normal"
        assert percentile["metric"] == f"{window}_percentile"
        assert normal["unit"] == "mm"
        assert percentile["unit"] == "percentil"
        assert normal["value"] == pytest.approx(days * 15.5)
        # Selected total is `days * 5.5`, which falls strictly between the
        # k=5 and k=6 baseline years, so the 1-based rank in the combined
        # 31-member sample is 6: 100 * 6 / 32 = 18.75.
        assert percentile["value"] == pytest.approx(18.75)

        for metric in (normal, percentile):
            assert metric["state"] == "available"
            assert metric["reason"] is None
            assert metric["interval_start"] == envelope_start
            assert metric["interval_end"] == envelope_end
            assert metric["coverage"] == pytest.approx(1.0)
            assert metric["completeness"] == pytest.approx(1.0)
            assert metric["quality"] == {
                "score": 1.0,
                "eligible_years": list(range(1991, 2021)),
                "baseline_years_derivable": 30,
                "reference_scope": "zone",
            }
            assert metric["discrepancies"] == []
            assert metric["revision"] == RAINFALL_METRIC_POLICY_REVISION
            assert metric["fallback_used"] is False
            assert metric["provenance"] == {
                "source_id": "chirps-v3-final",
                "source_class": "estimated_satellite",
                "method": metric["provenance"]["method"],
                "nominal_resolution": "5500m",
                "aggregation": "daily",
                "spatial_scope": "zone",
                "freshness": _NOW.isoformat(),
                "available_through": envelope_end,
            }
            # The whole contract, validated by the schema the disclosure path
            # validates with -- extra="forbid" on both models.
            MetricResult.model_validate(metric)


def test_the_served_interval_follows_the_handed_span_not_a_local_constant():
    """D9 + D2: the envelope bounds are DERIVED from the caller's
    ``window_baseline_span``, never re-stated here.

    ``_antecedent_reference_metrics`` receives the span the caller actually
    read; a literal start date inside it would be a second copy of
    ``repository.BASELINE_SPAN_START`` living where no test of the read ever
    reaches it -- the exact duplication ``build_snapshot``'s own docstring
    refuses for the VALUES, and the failure mode is silent: move the persisted
    span and every metric keeps announcing the period it no longer ranks
    against.

    The span below is shifted at BOTH ends: the start moves the announced
    interval directly, the exclusive end moves it through the derivable year
    set (1995..2014, twenty years -- still at the sample-size floor, so the
    metrics stay ``available`` and the assertion is about the envelope, not
    about suppression).
    """
    shifted = (date(1995, 1, 1), date(2015, 1, 1))
    antecedents = _snapshot(
        window_baseline=_dense_baseline(years=range(1995, 2015)),
        window_baseline_span=shifted,
    )["antecedents"]

    expected_start = datetime(1995, 1, 1, tzinfo=UTC).isoformat()
    expected_end = datetime(2014, 6, 15, tzinfo=UTC).isoformat()  # 2014 anchor + 1 day
    for key in _REFERENCE_KEYS:
        metric = antecedents[key]
        assert metric["state"] == "available", key
        assert metric["interval_start"] == expected_start, key
        assert metric["interval_end"] == expected_end, key
        assert metric["provenance"]["available_through"] == expected_end, key
        assert metric["quality"]["baseline_years_derivable"] == 20, key


def test_a_suppressed_reference_metric_keeps_the_whole_field_contract():
    """3.9 + spec R4: a suppressed row is a full ``MetricResult``, never a
    dropped key and never a zero. The envelope and the provenance survive
    suppression, which is what lets the fold render the row with its reason
    beside the available ones.
    """
    from app.domains.geo.rainfall.schemas import MetricResult

    antecedents = _snapshot(window_baseline=None)["antecedents"]
    for key in _REFERENCE_KEYS:
        metric = antecedents[key]
        assert set(metric) == _METRIC_FIELDS, key
        assert metric["value"] is None, key
        assert metric["state"] == "suppressed", key
        assert metric["reason"], key
        MetricResult.model_validate(metric)


def test_discrepancies_disclose_a_cross_source_baseline_comparison():
    """3.10: an NRT-sourced selected window ranked against a Final-sourced
    baseline is a methodological caveat the reader cannot infer from the
    numbers, and the baseline has no disclosure channel of its own. Silence
    here would rank an NRT window against a Final baseline with nothing said.
    """
    antecedents = _snapshot(source_id="chirps-v3-sat")["antecedents"]
    for key in _REFERENCE_KEYS:
        assert antecedents[key]["discrepancies"] == [
            "cross_source_baseline=chirps-v3-final_vs_chirps-v3-sat"
        ], key

    # A Final-sourced selected window emits nothing: the caveat is emitted
    # only where it is true.
    for key in _REFERENCE_KEYS:
        assert _snapshot()["antecedents"][key]["discrepancies"] == [], key


def test_the_served_mode_is_identifiable_and_the_absolute_mode_never_reaches_a_metric():
    """3.11 (D8, spec R3 S1 + S2): ``provenance.method`` carries the MODE.

    The carrier already exists and is already rendered (``Método``,
    RainfallMetricList.tsx) and exported (export.py:291), so the two modes
    become non-interchangeable in the SERVED contract at zero new fields --
    which is what the spec requires. ``absolute_weibull_rank`` must appear on
    no served metric: substituting it for a suppressed seasonal value would
    serve a different statistic under the seasonal name.
    """
    from app.domains.geo.rainfall.climatology import (
        ABSOLUTE_WEIBULL_RANK,
        SEASONAL_WEIBULL_RANK,
        WINDOW_MEAN,
    )

    snapshot = _snapshot()
    antecedents = snapshot["antecedents"]
    for window in ("d7", "d30", "d90"):
        assert antecedents[f"{window}_normal"]["provenance"]["method"] == WINDOW_MEAN
        assert antecedents[f"{window}_percentile"]["provenance"]["method"] == SEASONAL_WEIBULL_RANK

    served_methods = {
        metric["provenance"]["method"]
        for group in ("annual", "antecedents")
        for metric in snapshot[group].values()
    }
    assert ABSOLUTE_WEIBULL_RANK not in served_methods

    # And a SUPPRESSED seasonal percentile is not backfilled: it keeps its
    # reason, its seasonal method name, and no value.
    suppressed = _snapshot(window_baseline=_dense_baseline(years=range(1991, 2001)))["antecedents"]
    assert suppressed["d30_percentile"]["value"] is None
    assert suppressed["d30_percentile"]["provenance"]["method"] == SEASONAL_WEIBULL_RANK


def test_temporal_state_is_final_for_the_normal_and_inherited_for_the_percentile():
    """3.11 (annual precedent, compute.py:475): the ``normal`` is a completed
    1991-2020 climatology and is always ``final``; the ``percentile`` ranks the
    SELECTED total, so it inherits that total's provisional state.
    """
    historical = _snapshot(role="historical")["antecedents"]
    provisional = _snapshot(role="daily")["antecedents"]

    for window in ("d7", "d30", "d90"):
        assert historical[f"{window}"]["temporal_state"] == "final"
        assert historical[f"{window}_normal"]["temporal_state"] == "final"
        assert historical[f"{window}_percentile"]["temporal_state"] == "final"

        assert provisional[f"{window}"]["temporal_state"] == "provisional"
        assert provisional[f"{window}_normal"]["temporal_state"] == "final"
        assert provisional[f"{window}_percentile"]["temporal_state"] == "provisional"


def test_baseline_values_may_not_be_handed_over_without_their_span():
    """The span is what separates a never-persisted day from a HOLE, so values
    without bounds are not a degraded input -- they are an input whose meaning
    cannot be determined. Refused loudly rather than defaulted, because a
    default would be a second copy of ``repository``'s constants living where
    no test of the read would ever reach it.
    """
    with pytest.raises(ValueError, match="span"):
        _snapshot(window_baseline_span=None)


def test_the_six_keys_are_served_even_when_no_baseline_was_wired_at_all():
    """The stable-shape invariant, which the annual pair already honours: a
    reference metric is SUPPRESSED, never omitted, so a served analysis has one
    metric shape regardless of baseline coverage.

    A caller that passes no window baseline (the default) is precedence row 2
    with its default cause, ``baseline_scope_unmapped`` -- the same reason the
    annual pair discloses when no provider asset maps to the scope. Making the
    keys conditional on the kwarg instead would put the key SET at the mercy of
    a call site, which is the one thing risk #2 exists to prevent.
    """
    from app.domains.geo.rainfall.compute import build_snapshot

    snapshot = build_snapshot(
        scope=_ZONE,
        year=2024,
        role="historical",
        source_id="chirps-v3-final",
        intervals=_selected_intervals(),
        batch=_batch(),
        now=_NOW,
    )
    antecedents = snapshot["antecedents"]
    assert list(antecedents) == [
        "d7",
        "d7_normal",
        "d7_percentile",
        "d30",
        "d30_normal",
        "d30_percentile",
        "d90",
        "d90_normal",
        "d90_percentile",
    ]
    for key in _REFERENCE_KEYS:
        assert antecedents[key]["state"] == "suppressed", key
        assert antecedents[key]["reason"] == "baseline_scope_unmapped", key


# ---------------------------------------------------------------------------
# BL-BASELINE-STRING-SOURCE — the served period NAME is derived, not restated
# ---------------------------------------------------------------------------


def test_the_served_baseline_period_moves_when_the_span_constants_move(monkeypatch):
    """The envelope's ``baseline`` string must FOLLOW the persisted span.

    It was the literal ``"1991-2020"`` in ``build_snapshot``, independent of
    ``BASELINE_SPAN_START``/``BASELINE_SPAN_END`` -- the W8 class at its
    source. Move the span and fourteen surfaces (four label cells, six sheet
    rows, four badges) keep naming a period the reference no longer ranks
    against, with nothing anywhere to reveal it.

    Patched on ``temporal``, which is where the two constants are DEFINED;
    ``repository`` re-exports them. The patch reaches ``build_snapshot``
    because it reads them through the module at call time, which is exactly
    the property a literal does not have -- against the literal this test is
    RED, and against a name imported at module scope it would be too.
    """
    from app.domains.geo.rainfall import temporal

    assert _snapshot()["baseline"] == "1991-2020"

    monkeypatch.setattr(temporal, "BASELINE_SPAN_START", datetime(1981, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(temporal, "BASELINE_SPAN_END", datetime(2011, 1, 1, tzinfo=UTC))
    assert _snapshot()["baseline"] == "1981-2010"


def test_the_annual_pairs_disclosed_interval_starts_at_the_span_start(monkeypatch):
    """The SECOND copy of the same literal: ``_normal_and_percentile_metrics``
    opened its disclosed interval at a hardcoded ``1991-01-01``.

    The antecedent path already derives its own start from the handed span and
    documents why; the annual path did not, so the two halves of one envelope
    could disagree about the period after a span move.
    """
    from app.domains.geo.rainfall import temporal

    annual = _snapshot()["annual"]
    assert annual["normal"]["interval_start"].startswith("1991-01-01")

    monkeypatch.setattr(temporal, "BASELINE_SPAN_START", datetime(1981, 1, 1, tzinfo=UTC))
    moved = _snapshot()["annual"]
    assert moved["normal"]["interval_start"].startswith("1981-01-01")


def test_the_period_label_refuses_a_span_it_cannot_name_honestly():
    """``baseline_period_label`` is only defined for a whole-calendar-year
    half-open span. A mid-year bound has no "YYYY-YYYY" name, and inventing
    one is the same silent-wrong-period defect in a new place.
    """
    from app.domains.geo.rainfall import temporal

    assert (
        temporal.baseline_period_label(
            datetime(1991, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC)
        )
        == "1991-2020"
    )
    with pytest.raises(ValueError, match="whole-calendar-year"):
        temporal.baseline_period_label(
            datetime(1991, 7, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC)
        )
    with pytest.raises(ValueError, match="baseline span is empty"):
        temporal.baseline_period_label(
            datetime(2021, 1, 1, tzinfo=UTC), datetime(1991, 1, 1, tzinfo=UTC)
        )


# ---------------------------------------------------------------------------
# BL-EMPTY-BASELINE-REASON — an empty read is not a small sample
# ---------------------------------------------------------------------------


def _annual_snapshot(*, baseline, reason: str) -> dict:
    """``build_snapshot`` with the ANNUAL baseline argument under test.

    ``_snapshot`` above drives the antecedent (window) pair and never passes
    ``baseline``; this drives the other half, so the two paths of the same
    defect are exercised through the same public entry point.
    """
    from app.domains.geo.rainfall.compute import build_snapshot

    return build_snapshot(
        scope=_ZONE,
        year=2024,
        role="historical",
        source_id="chirps-v3-final",
        intervals=_selected_intervals(),
        batch=_batch(),
        now=_NOW,
        baseline=baseline,
        baseline_unavailable_reason=reason,
    )


def test_an_annual_baseline_with_nothing_in_it_discloses_the_absent_evidence_reason():
    """An EMPTY-but-not-``None`` annual baseline served the SAMPLE-SIZE reason.

    Nothing was read, yet the disclosure said the sample was too small -- the
    reader is told the baseline is thin when the truth is that there is no
    baseline. The spec's honesty register ("the two suppression reasons MUST be
    distinguishable from each other", rainfall-analysis "Antecedent Percentile
    Anti-Bias Guards") is exactly what an empty read shipping the sample-size
    reason violates: a suppressed metric's reason is the only thing the reader
    gets, so it has to be true.

    The reason is a THIRD string, not the caller's. The caller's reason
    explains why it handed in ``None``; serving it for an empty read would
    announce "baseline_scope_unmapped" for a scope that IS mapped -- which is
    the same class of wrong sentence one branch over, and is what the first
    draft of this fix actually produced against the duplicate-slot fixture.
    """
    from app.domains.geo.rainfall.compute import (
        BASELINE_EVIDENCE_ABSENT,
        BASELINE_SCOPE_UNMAPPED,
    )

    annual = _annual_snapshot(baseline={}, reason=BASELINE_SCOPE_UNMAPPED)["annual"]
    for name in ("normal", "percentile"):
        assert annual[name]["state"] == "suppressed", name
        assert annual[name]["reason"] == BASELINE_EVIDENCE_ABSENT, (name, annual[name])


def test_an_annual_baseline_the_caller_could_not_read_keeps_the_callers_reason():
    """``None`` is UNCHANGED, and the two cases stay distinguishable.

    Pinned beside the branch above because the cheap version of this fix --
    widening ``is None`` to ``not baseline`` -- makes them identical, and the
    caller's sentence is the one that is then wrong.
    """
    from app.domains.geo.rainfall.compute import (
        BASELINE_EVIDENCE_ABSENT,
        BASELINE_EVIDENCE_INVALID,
    )

    annual = _annual_snapshot(baseline=None, reason=BASELINE_EVIDENCE_INVALID)["annual"]
    for name in ("normal", "percentile"):
        assert annual[name]["reason"] == BASELINE_EVIDENCE_INVALID, (name, annual[name])
    assert BASELINE_EVIDENCE_ABSENT != BASELINE_EVIDENCE_INVALID


def test_a_thin_but_real_annual_baseline_still_discloses_the_sample_size_reason():
    """The other side of the same distinction, so the fix cannot collapse it.

    Nineteen eligible years is one short of ``MIN_BASELINE_YEARS``: evidence
    WAS read and the sample is genuinely too small, which is the one case the
    sample-size reason is true of.
    """
    from app.domains.geo.rainfall.compute import (
        BASELINE_YEARS_BELOW_MINIMUM,
        MIN_BASELINE_YEARS,
    )

    years = range(1991, 1991 + MIN_BASELINE_YEARS - 1)
    thin = {year: (365.0, 365, 365) for year in years}
    annual = _annual_snapshot(baseline=thin, reason="baseline_evidence_invalid")["annual"]
    for name in ("normal", "percentile"):
        assert annual[name]["reason"] == BASELINE_YEARS_BELOW_MINIMUM, (name, annual[name])


@pytest.mark.parametrize("empty", [(), []], ids=["empty-tuple", "empty-list"])
def test_a_window_baseline_with_nothing_in_it_discloses_the_absent_evidence_reason(empty):
    """The MIRROR of the annual defect on the antecedent path.

    Same wrong sentence, same fix, asserted over all six reference metrics
    because the reason is set once for the pair and a per-window regression
    would otherwise hide behind d7.
    """
    from app.domains.geo.rainfall.compute import (
        BASELINE_EVIDENCE_ABSENT,
        BASELINE_SCOPE_UNMAPPED,
    )

    antecedents = _snapshot(
        window_baseline=empty,
        window_baseline_unavailable_reason=BASELINE_SCOPE_UNMAPPED,
    )["antecedents"]
    for key in _REFERENCE_KEYS:
        assert antecedents[key]["state"] == "suppressed", key
        assert antecedents[key]["reason"] == BASELINE_EVIDENCE_ABSENT, (key, antecedents[key])


def test_a_window_baseline_the_caller_could_not_read_keeps_the_callers_reason():
    """``None`` on the window path is UNCHANGED too -- the duplicate-slot
    handler in ``tasks`` hands in ``None`` with ``baseline_evidence_invalid``,
    and that sentence must survive this fix intact."""
    from app.domains.geo.rainfall.compute import BASELINE_EVIDENCE_INVALID

    antecedents = _snapshot(
        window_baseline=None,
        window_baseline_unavailable_reason=BASELINE_EVIDENCE_INVALID,
    )["antecedents"]
    for key in _REFERENCE_KEYS:
        assert antecedents[key]["reason"] == BASELINE_EVIDENCE_INVALID, key


def test_an_off_scope_empty_window_baseline_still_discloses_the_scope_reason():
    """Precedence is unchanged: the scope floor outranks the baseline one.

    A basin scope cannot have a zone reference AT ALL, so the reader is told
    that first -- the empty baseline downstream is a consequence, not the
    explanation. Pinned because the fix edits exactly the branch below it.
    """
    from app.domains.geo.rainfall.compute import (
        BASELINE_SCOPE_UNMAPPED,
        REFERENCE_SCOPE_UNSUPPORTED,
    )

    antecedents = _snapshot(
        scope=_BASIN,
        window_baseline=(),
        window_baseline_unavailable_reason=BASELINE_SCOPE_UNMAPPED,
    )["antecedents"]
    for key in _REFERENCE_KEYS:
        assert antecedents[key]["reason"] == REFERENCE_SCOPE_UNSUPPORTED, key
