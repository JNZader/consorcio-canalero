"""Full-span extreme-rainfall detector runbook (design.md D6).

Mirrors ``backfill_cli.py``'s discipline exactly -- same ``EXIT_OK`` /
``EXIT_STOPPED`` / ``EXIT_INVALID_RANGE``, same labelled stops, same hand-run
shape inside the deployed backend container::

    docker compose exec backend python -m app.domains.geo.rainfall.detector_cli

Like that runner, this is **NOT a Beat schedule** and it is not a lazy
computation inside a request handler: ``router_gee_support``'s own docstring
records the 21-161 s tail-latency incident caused by blocking work on the event
loop in exactly the handlers that will read this catalog.

**It runs FULL-SPAN, always, and there is deliberately no incremental mode.**
Not an omission -- r1's incremental mode was CUT in review, and this paragraph
exists so a future reader does not "restore" it. The climatology span is frozen
to whole calendar years (``DETECTOR_CLIMATOLOGY_START`` / ``_END``), so every
run ranks against the same distribution and reads the same rows; advancing the
span requires a ``DETECTOR_REVISION`` bump, which regenerates the whole
generation anyway. The incremental path existed only to bound a read of ~12.7k
rows -- roughly one indexed range scan -- and it cost two of the four hardest
findings in that review (a truncated event sealed forever, and permanently lost
deferrals). A ``--since`` flag would let a run seal rows under a span it never
ranked against, which is the one thing an append-only catalog cannot take back.

**Stops are LABELLED and write NOTHING.** Every abort exits ``EXIT_STOPPED``
with a distinguishable ``reason=``, and the last of them is a catch-all so that
sentence has no exceptions:

``duplicate_baseline_slot``
    Two non-superseded rows for one day. The duplicate inflates a window total
    while leaving the window looking COMPLETE, so the rank moves and nothing
    discloses it. A snapshot metric may degrade; a permanent catalog row may
    not.
``insufficient_climatology``
    The ranked population is below ``MIN_WINDOW_SAMPLES`` (or the record is
    shorter than a requested window). An empty catalog and a catalog that could
    not be computed are different facts.
``catalog_divergence``
    A second computation disagrees with a persisted row at one identity -- or
    with itself, within a single run. ``ON CONFLICT DO NOTHING`` would convert
    that into permanent silence.
``catalog_integrity``
    A raw ``IntegrityError`` at ``commit()`` -- the shape the intra-batch
    collision takes in production, where nothing autoflushes.
``unexpected``
    Anything else. The label is what makes the sentence above true: without a
    catch-all, an ``OperationalError`` on a dropped connection left ``main`` as
    a bare traceback whose interpreter exit code is ALSO 1, indistinguishable
    from a named stop by the wrapper script that reads it.

**And one exit that is NOT a stop.** The calibration report is rendered AFTER
``commit()``, so a failure to render it happens with the rows already permanent.
Reporting that as ``EXIT_STOPPED`` would tell the operator the opposite of what
the catalog holds -- and the documented reaction to a stop is "fix it and re-run",
which is only safe because a stop wrote nothing. A post-commit rendering failure
therefore exits ``EXIT_REPORT_FAILED`` (``3``) with ``reason=report_render_failed``
and says outright that the rows WERE committed.

On every one of them the session is **rolled back before the process exits**.
That is this module's obligation and not the writer's: ``persist_events``
``db.add()``s each non-diverging event as it walks the batch, so the events
computed BEFORE an abort sit pending in the session -- unwritten, but written by
any later ``flush()`` or ``commit()``. "Zero rows written, including for events
computed before the abort" is therefore true only because of the rollback below.

**Intra-batch identities are resolved before the writer sees them**, for a
reason that is invisible in the test suite: production's ``SessionLocal`` is
``autoflush=False`` while the test ``db`` fixture is ``autoflush=True``. Under
autoflush, ``persist_events``' identity lookup finds a row added earlier in the
same batch and reports a named divergence. In production nothing flushes, the
lookup sees nothing, both rows are added, and the collision surfaces at
``commit()`` as a raw ``IntegrityError`` on ``uq_rainfall_extreme_event_identity``
-- a different type, from a different place, with no field list. So the batch is
resolved here (identical repeats collapse, disagreements stop labelled) and an
``IntegrityError`` at commit is ALSO caught and labelled, rather than trusting
one of the two.

The run prints a **calibration report** on success: firing end-days per window
length per tier, events after D1's merge, the span-edge-clipped rows, and one
explicit verdict per gold anchor. D4's ~30 / ~150 is a MODEL; this is the
measurement, and a measurement that materially disagrees with the model is a
REPORT to the owner -- a spec amendment plus a revision bump plus a digest bump,
one audited move -- never a constant quietly retuned inside a run.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import fields as dataclass_fields
from datetime import date

from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.domains.geo.rainfall.adapters.gee_client import (
    BASELINE_ASSET_VERSION,
    DEFAULT_ZONE_ASSET,
)
from app.domains.geo.rainfall.detector import (
    DETECTOR_CLIMATOLOGY_END,
    DETECTOR_CLIMATOLOGY_START,
    DETECTOR_REVISION,
    TIER_PERCENTILES,
    WINDOW_LENGTHS,
    DetectedEvent,
    InsufficientClimatologyError,
    count_firing_end_days,
    detect_events,
)
from app.domains.geo.rainfall.models import RainfallExtremeEvent
from app.domains.geo.rainfall.repository import (
    CatalogDivergenceError,
    DuplicateBaselineSlotError,
    baseline_daily_values,
    event_key,
    persist_events,
)

EXIT_OK = 0
EXIT_STOPPED = 1
EXIT_INVALID_RANGE = 2
#: NOT a stop, and deliberately outside ``backfill_cli``'s shared vocabulary:
#: this run COMMITTED and then failed to render its report. See the module
#: docstring -- "exit 1 wrote zero rows" has to hold on every path, so the one
#: failure that happens after ``commit()`` cannot borrow that code.
EXIT_REPORT_FAILED = 3

#: The span is passed EXPLICITLY on every read. ``baseline_daily_values``
#: defaults to the antecedent-reference card's own ``[1991, 2021)`` bounds,
#: which are load-bearing for the envelope that card serves and must not move;
#: a runbook that omitted these arguments would silently rank 1991-2020, drop
#: everything after it from the catalog, and report a clean run.
SPAN_START = DETECTOR_CLIMATOLOGY_START
SPAN_END = DETECTOR_CLIMATOLOGY_END

#: Strongest tier first, derived from the ratified percentiles rather than
#: written out again: detection runs once per tier and the tiers never consult
#: each other, so this is presentation order, not precedence.
TIER_ORDER: tuple[str, ...] = tuple(
    sorted(TIER_PERCENTILES, key=lambda tier: -TIER_PERCENTILES[tier])
)

#: The change's validation strategy (tasks.md 3.6), keyed exactly like the
#: curated seed so the two cannot drift into two different anchor sets. A
#: non-detection is a SURFACED finding -- the anchor is still served
#: "curated, not detector-confirmed" -- and never a skipped case.
GOLD_ANCHORS: Mapping[str, date] = {
    "mar_2015": date(2015, 3, 15),
    "feb_2017": date(2017, 2, 20),
    "sep_2025": date(2025, 9, 5),
}

_STOP_REASONS = (
    (DuplicateBaselineSlotError, "duplicate_baseline_slot"),
    (InsufficientClimatologyError, "insufficient_climatology"),
    (CatalogDivergenceError, "catalog_divergence"),
    (IntegrityError, "catalog_integrity"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="detector_cli",
        description=(
            "Full-span extreme-rainfall event detection over the persisted "
            "baseline. Always full-span: there is no --since/--from flag and "
            "the omission is deliberate (design.md D6). Idempotent -- a second "
            "run inserts, updates and deletes nothing. Stops LABELLED, never a "
            "bare traceback, and a stop writes ZERO rows. Exit codes: "
            f"{EXIT_OK}=ok, {EXIT_STOPPED}=labelled stop (zero rows written, "
            f"safe to re-run), {EXIT_INVALID_RANGE}=invalid frozen span, "
            f"{EXIT_REPORT_FAILED}=reason=report_render_failed -- the rows WERE "
            "committed and only the report failed to render, so this is NOT a "
            "stop and re-running it will find the catalog already written."
        ),
    )
    parser.add_argument(
        "--asset",
        default=DEFAULT_ZONE_ASSET,
        help=(
            "GEE asset whose persisted baseline is ranked (default: the "
            "deployment's single zone asset, %(default)r)."
        ),
    )
    parser.add_argument(
        "--source-id",
        default="chirps-v3-final",
        help="provider source id (default: %(default)r)",
    )
    return parser


def plan_events(daily: Sequence[tuple[date, float]]) -> tuple[DetectedEvent, ...]:
    """Every event at every tier, in :data:`TIER_ORDER`.

    One detection pass per tier, with no tier consulting another: an ``alta``
    span being a superset of two ``extrema`` spans is the ratified behaviour,
    which is why ``tier`` joins the identity key.
    """
    return tuple(event for tier in TIER_ORDER for event in detect_events(daily=daily, tier=tier))


def _resolve_batch(events: Sequence[DetectedEvent]) -> tuple[DetectedEvent, ...]:
    """Collapse identical repeats; STOP on a repeat that disagrees.

    See the module docstring: this cannot be left to ``persist_events``' own
    identity lookup, which only sees pending rows under the test fixture's
    ``autoflush=True``. Collapsing a DISAGREEING repeat would pick a winner by
    list position and seal it forever, so that half raises instead.
    """
    resolved: dict[tuple[str, date], DetectedEvent] = {}
    for event in events:
        identity = (event.tier, event.start_date)
        seen = resolved.get(identity)
        if seen is None:
            resolved[identity] = event
            continue
        if seen == event:
            continue
        differing = [
            field.name
            for field in dataclass_fields(event)
            if getattr(seen, field.name) != getattr(event, field.name)
        ]
        raise CatalogDivergenceError(
            "two computations of one identity disagree WITHIN A SINGLE RUN "
            f"(event_key={event_key(event)!r}, tier={event.tier!r}, "
            f"start_date={event.start_date.isoformat()}): differing fields {differing}",
            event_key=event_key(event),
            differing_fields=differing,
        )
    return tuple(resolved.values())


def anchor_verdicts(events: Sequence[DetectedEvent]) -> dict[str, dict[str, object]]:
    """One verdict per gold anchor -- for EVERY anchor, detected or not.

    Keyed unconditionally on :data:`GOLD_ANCHORS`. A comprehension that only
    recorded the anchors it found would render an all-confirmed run and a run
    that confirmed nothing identically, which is the silent drop tasks.md 3.6
    forbids.

    Coverage is inclusive at both ends: an anchor falling on an event's last day
    is inside that event.
    """
    verdicts: dict[str, dict[str, object]] = {}
    for name, anchor in GOLD_ANCHORS.items():
        covering = [event for event in events if event.start_date <= anchor <= event.end_date]
        # Strongest first, so a confirmed anchor reports the strongest tier that
        # saw it rather than whichever pass happened to run first.
        covering.sort(key=lambda event: TIER_ORDER.index(event.tier))
        if not covering:
            verdicts[name] = {
                "date": anchor,
                "detected": False,
                "tier": None,
                "span": None,
                "windows": (),
            }
            continue
        best = covering[0]
        verdicts[name] = {
            "date": anchor,
            "detected": True,
            "tier": best.tier,
            "span": (best.start_date, best.end_date),
            "windows": tuple(window.label for window in best.fired_windows),
            "event_key": event_key(best),
        }
    return verdicts


def curated_anchor_rows(db, *, source_id: str, asset: str) -> int:
    """How many ``curated`` rows the catalog holds for this scope.

    Only ever rendered as a NOTE on the anchor section (see
    :func:`format_report`): a deployment whose curated seed never ran serves
    three unconfirmed anchors and a catalog that does not contain them, and
    those are different facts that print identically otherwise.
    """
    return (
        db.query(RainfallExtremeEvent)
        .filter_by(
            provenance="curated",
            source_id=source_id,
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
        )
        .count()
    )


def calibration_report(
    daily: Sequence[tuple[date, float]],
    *,
    events: Sequence[DetectedEvent] | None = None,
    curated_rows: int | None = None,
) -> dict[str, object]:
    """The measured shape of one full-span run (tasks.md 3.9).

    Every number here is COMPUTED from *daily*. Printing the design's modelled
    ~30 / ~150 -- or any other constant -- would make the owner's calibration
    gate unable to disagree with the model it exists to check.

    *events* is the batch the run actually RESOLVED and handed to the writer.
    ``main`` passes it, and that is the point (B1c verify, F1): recomputing the
    batch here and never comparing it against the persisted one is exactly the
    class of failure this module exists to prevent -- the intra-batch resolution
    would collapse two rows into one and the report would still describe two.
    It stays optional so the calibration harness can call this on a bare series.
    """
    if events is None:
        events = plan_events(daily)
    return {
        "curated_rows": curated_rows,
        "baseline_days": len(daily),
        "span": (SPAN_START.date(), SPAN_END.date()),
        "firing_end_days": {
            tier: count_firing_end_days(daily=daily, tier=tier) for tier in TIER_ORDER
        },
        "events_after_merge": {
            tier: sum(1 for event in events if event.tier == tier) for tier in TIER_ORDER
        },
        "clipped_at_span_end": tuple(
            event_key(event) for event in events if event.clipped_at_span_end
        ),
        "anchors": anchor_verdicts(events),
    }


def format_report(report: Mapping[str, object]) -> str:
    """The report as the operator reads it on the runbook's stdout."""
    span_start, span_end = report["span"]
    lines = [
        f"span: [{span_start.isoformat()}, {span_end.isoformat()}) revision={DETECTOR_REVISION}",
        f"baseline days: {report['baseline_days']}",
        # ANNOTATED, not removed (B1c verify, F2). A window's firing end-days
        # are the days whose total ranks at or above the tier percentile, so on
        # a real record the count is ~N*(1-p) BY CONSTRUCTION -- the measured
        # run gives 31/31/31 at every window length, which carries no
        # information about the record. It stays because it is the arithmetic's
        # sanity check (a 0 or a 300 there means the ranking is broken), and it
        # is labelled so nobody reads it as a finding. The number that carries
        # the calibration is `events after merge`.
        "firing end-days (before the D1 merge) "
        "(≈N·(1−p) por construcción — control de sanidad, no señal):",
    ]
    for tier, counts in report["firing_end_days"].items():
        rendered = " ".join(f"d{days}={counts[days]}" for days in WINDOW_LENGTHS)
        lines.append(f"  {tier} {rendered}")
    lines.append("events after merge:")
    for tier, total in report["events_after_merge"].items():
        lines.append(f"  {tier}: {total}")
    clipped = report["clipped_at_span_end"]
    lines.append(f"clipped_at_span_end: {', '.join(clipped) if clipped else '(ninguno)'}")
    # An absent seed is DISCLOSED rather than inferred from three "no detectado"
    # lines, which is what an un-seeded deployment and a seeded one that
    # confirmed nothing both look like.
    if report.get("curated_rows") == 0:
        lines.append("gold anchors: (seed ausente — anclas no sembradas)")
    else:
        lines.append("gold anchors:")
    for name, verdict in report["anchors"].items():
        if not verdict["detected"]:
            lines.append(f"  {name} ({verdict['date'].isoformat()}): no detectado")
            continue
        start, end = verdict["span"]
        lines.append(
            f"  {name} ({verdict['date'].isoformat()}): detectado "
            f"tier={verdict['tier']} span={start.isoformat()}..{end.isoformat()} "
            f"windows={','.join(verdict['windows'])}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None, *, session_factory=SessionLocal) -> int:
    args = build_parser().parse_args(argv)

    # Reachable only through a defective constants block, which is exactly why
    # it is checked: an inverted frozen span reads back as an empty baseline,
    # and an empty baseline is reported by everything downstream as "no events"
    # -- a clean, non-stopped, fabricated absence on the one runbook that writes
    # permanent rows.
    if SPAN_START >= SPAN_END:
        print(
            f"invalid range: the frozen detector span [{SPAN_START.date()}, "
            f"{SPAN_END.date()}) is empty or inverted.",
            file=sys.stderr,
        )
        return EXIT_INVALID_RANGE

    with session_factory() as db:
        try:
            daily = baseline_daily_values(
                db,
                source_id=args.source_id,
                asset=args.asset,
                span_start=SPAN_START,
                span_end=SPAN_END,
            )
            events = _resolve_batch(plan_events(daily))
            written = persist_events(
                db,
                source_id=args.source_id,
                scope_kind="provider_asset",
                scope_id=args.asset,
                scope_version=BASELINE_ASSET_VERSION,
                events=events,
            )
            # The RESOLVED batch, not a third recomputation of it: the report
            # has to describe the rows this run wrote.
            report = calibration_report(
                daily,
                events=events,
                curated_rows=curated_anchor_rows(db, source_id=args.source_id, asset=args.asset),
            )
            db.commit()
        except tuple(kind for kind, _ in _STOP_REASONS) as exc:
            # THE obligation of this module (tasks.md 3.4a): everything the
            # aborted batch added is pending in this session and would be
            # written by any later flush. Rolling back is what makes "zero rows
            # written" true, and it happens BEFORE anything is printed so a
            # crash in the reporting cannot leave the batch alive.
            db.rollback()
            reason = next(label for kind, label in _STOP_REASONS if isinstance(exc, kind))
            print(f"STOPPED (reason={reason}): {exc}", file=sys.stderr)
            return EXIT_STOPPED
        except Exception as exc:  # noqa: BLE001 -- deliberate catch-all, see below
            # The parser promises "Stops LABELLED, never a bare traceback". Four
            # enumerated types do not make that true: everything else escaped
            # with the interpreter's own exit code -- also 1 -- and no reason=
            # for a wrapper script to read. Rolled back for the same reason the
            # named stops are, and the traceback still goes to stderr, because
            # labelled is not the same as swallowed.
            db.rollback()
            print(f"STOPPED (reason=unexpected): {exc!r}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return EXIT_STOPPED

    # PAST the commit. A failure here is not a stop and must not be reported as
    # one: the rows are permanent and the operator was simply never shown them.
    try:
        print(format_report(report))
        print(f"catalog: inserted={written['inserted']} skipped={written['skipped']}")
    except Exception as exc:  # noqa: BLE001 -- see EXIT_REPORT_FAILED
        print(
            f"REPORT FAILED (reason=report_render_failed): the run COMMITTED "
            f"inserted={written['inserted']} skipped={written['skipped']} and then "
            f"failed to render its report: {exc!r}. The catalog IS written; do not "
            "read this as an aborted run.",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)
        return EXIT_REPORT_FAILED
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover -- module entry point
    raise SystemExit(main())
