"""The READ MODEL of the extreme-event catalog: rows in, served records out.

Everything here runs at READ time and stores nothing. That is the design
choice, not an implementation detail:

* **name and description are synthesized, never stored** (D10). A wording fix
  is then a code change rather than a migration, and no stored copy can drift
  from the statistics it describes. It also removes the failure r1 shipped:
  `isHistoricFlood` (`useImageExplorerController.tsx:48-56`) requires
  `name: string` and silently DROPS any record without one, so a nameless
  detected row does not render wrong -- it disappears, with no error anywhere.
* **confirmation is derived, never stored** (D8). Storing it would require the
  detector to UPDATE a curated row on every run -- a mutation of an append-only
  table, refused at flush by `_IMMUTABLE_TYPES` -- and the value would go stale
  the instant the served generation moved.
* **`clipped_at_span_end` is derived** from the span sealed ON the row, for the
  same reason: a later generation at a wider span is a different row.

Why this module rather than `router_gee_support.py` (where design.md's file
table put it): the composition below is a pure function of catalog rows and is
the SAME derivation the imagery bridge needs in B2b to resolve an id against
the served generation. Two renderings of one served contract is how the list
and the bridge begin to disagree about which events exist -- the failure D12
calls BLOCKER-1, arriving through the other door.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from app.domains.geo.rainfall.detector import (
    CHIRPS_DISCLOSURE,
    DetectedEvent,
    FiredWindow,
    synthesize_description,
    synthesize_name,
)

#: Tier -> the wire `severity` (D9). The frontend styles exactly `alta` -> red
#: and `media` -> orange, and EVERYTHING ELSE -> the palest yellow available
#: (`ImageExplorerInfoPanels.tsx:214-225`), so serving the true tier `extrema`
#: would paint the most extreme events the faintest colour on the card. The
#: true tier travels in the separate `tier` field, which the current frontend
#: ignores and a later one can style.
WIRE_SEVERITY_BY_TIER: Mapping[str, str] = {"extrema": "alta", "alta": "media"}

#: The default served tier (spec R3). `alta` is ~144 events against `extrema`'s
#: ~36 at the ratified constants (measured 2026-08-26): the wide tier is
#: reachable, never the default.
DEFAULT_TIER = "extrema"
TIER_DOMAIN = ("extrema", "alta")

DEFAULT_LIMIT = 200
MAX_LIMIT = 500

#: `typeGuards.ts:406-411` rejects a restored selection whose `days_buffer`
#: falls outside [1, 30], and the rejection is SILENT -- the persisted selection
#: simply stops restoring, with nothing anywhere to notice. A curated payload is
#: hand-written data, so the ceiling is enforced here rather than trusted.
MIN_DAYS_BUFFER = 1
MAX_DAYS_BUFFER = 30

#: Sentinel-2A from 2015, Sentinel-1A from 2014 (`explore.md:87-96`); before
#: that only Landsat 5/7 at a 16-day revisit, cloudy and with no SAR. The
#: cutoff is a claim about SENSORS, so it is pinned to that table rather than
#: derived from anything in this repository.
IMAGERY_CUTOFF = date(2015, 1, 1)
IMAGERY_GOLDEN_WINDOW = (date(2017, 1, 1), date(2021, 12, 31))

PRE_2015_IMAGERY_NOTE = (
    "Sin imagen satelital util: antes de 2015 solo Landsat 5/7 cada 16 dias, con nubes y sin SAR."
)
GOLDEN_WINDOW_IMAGERY_NOTE = "Ventana dorada: Sentinel-2 (5 dias) + Sentinel-1 (6 dias)."
CANDIDATE_IMAGERY_NOTE = "Candidato a imagen satelital: Sentinel-2 y Sentinel-1 disponibles."

#: On EVERY event, curated included (spec R5). The same sentence is inside the
#: synthesized description because the picker renders prose only, and a machine
#: -readable field because the spec requires the disclosure to be readable
#: without parsing Spanish.
DATASET_DISCLOSURE = (
    "CHIRPS ordena de forma relativa y acota la ventana de busqueda satelital; "
    "no es una medicion en milimetros."
)

#: Owner-ratified 2026-08-26 from the real calibration: `feb_2017`'s rain fired
#: on 02-18 (54.57 mm, p99.68) while the curated anchor is dated 02-20 -- the
#: downstream-flooding date institutional memory kept. A strict same-date rule
#: hides a real confirmation behind a dating technicality; a loose one confirms
#: `mar_2015` from 8 days away, where CHIRPS saw nothing at all. Three days is
#: the ratified line, and the anchor KEEPS its curated date either way.
CONFIRMATION_TOLERANCE_DAYS = 3

CONFIRMED = "detector_confirmed"
NOT_CONFIRMED = "not_confirmed"
NOT_CONFIRMED_LABEL = "curated, not detector-confirmed"

#: Spec R6's vocabulary, in full. `scope_unsupported` has no branch today and
#: that is stated rather than hidden: the served contract exposes no scope
#: selector -- coverage is the single zone asset, declared at the root -- so the
#: reason becomes reachable only when BL-BASIN-SCOPE-BROKEN is picked up and a
#: caller can ask for a scope this catalog does not hold.
ABSENCE_REASONS = ("no_qualifying_window", "incomplete_evidence", "scope_unsupported")

#: The coverage claim (D11). `scope_kind: "zone"` is the SERVED vocabulary --
#: the persisted key spells the same thing `provider_asset`, because the row is
#: keyed by the provider's asset -- and `basin_coverage: false` is explicit
#: because the basin scope is broken end to end (`gee_client.py:52-57`) and
#: silence would read as support.
SERVED_COVERAGE = {
    "scope_kind": "zone",
    "scope_id": "zona_cc_ampliada",
    "basin_coverage": False,
}


def _fired_windows(payload: Mapping[str, Any] | None) -> tuple[FiredWindow, ...]:
    """The persisted JSON back into the dataclass the synthesis reads.

    Sorted by length so a description lists `d1, d3, d7` in the order a reader
    expects rather than in whatever order the JSON round trip preserved.
    """
    windows = [
        FiredWindow(
            days=int(label.lstrip("d")),
            peak_end=date.fromisoformat(entry["peak_end"]),
            peak_total_mm=float(entry["peak_total_mm"]),
            percentile=float(entry["percentile"]),
        )
        for label, entry in (payload or {}).items()
    ]
    return tuple(sorted(windows, key=lambda window: window.days))


def event_from_row(row) -> DetectedEvent:
    """A persisted detected row as the dataclass the synthesis functions take.

    The span comes off the ROW, never off the module constants: a row ranked
    against 1991-2025 has to keep saying 1991-2025 after a later revision
    widens the span, or the bump silently relabels every already-persisted
    generation with a span it was never ranked against.
    """
    return DetectedEvent(
        tier=row.tier,
        start_date=row.start_date,
        end_date=row.end_date,
        peak_date=row.peak_date,
        max_percentile=row.max_percentile,
        fired_windows=_fired_windows(row.fired_windows),
        climatology_span_start=row.climatology_span_start,
        climatology_span_end=row.climatology_span_end,
    )


def _imagery(end_day: date) -> tuple[bool, str]:
    if end_day < IMAGERY_CUTOFF:
        return False, PRE_2015_IMAGERY_NOTE
    golden_start, golden_end = IMAGERY_GOLDEN_WINDOW
    if golden_start <= end_day <= golden_end:
        return True, GOLDEN_WINDOW_IMAGERY_NOTE
    return True, CANDIDATE_IMAGERY_NOTE


def confirmation_offset_days(anchor: date, row) -> int:
    """Days between *anchor* and the nearest edge of *row*'s span; 0 if inside.

    Inclusive at both ends, like the runbook's own anchor verdicts: an anchor
    falling on an event's last day is inside that event, not one day outside it.
    """
    if row.start_date <= anchor <= row.end_date:
        return 0
    if anchor < row.start_date:
        return (row.start_date - anchor).days
    return (anchor - row.end_date).days


def confirming_rows(anchor: date, detected: Sequence[Any]) -> list[Any]:
    """EVERY detected row within the tolerance of *anchor*, nearest first.

    Plural on purpose. One storm produces rows at BOTH tiers by construction --
    an ``alta`` span is a superset of the ``extrema`` spans inside it, which is
    the whole reason ``repository.EVENT_KEY_PREFIXES`` has to keep their keys
    apart -- and a long wet spell can also split into several spans at one
    tier. Treating only the nearest row as "the confirmation" is correct for
    NAMING it and wrong for SUPPRESSING it: every other row of the same storm
    then survives into the list as a second card for one flood, which is the
    r1 failure D8's precedence exists to remove.

    Nearest span wins; ties go to the strongest tier and then to the higher
    percentile, so the answer does not depend on row order.
    """
    candidates = [
        (confirmation_offset_days(anchor, row), row)
        for row in detected
        if confirmation_offset_days(anchor, row) <= CONFIRMATION_TOLERANCE_DAYS
    ]
    candidates.sort(
        key=lambda pair: (
            pair[0],
            TIER_DOMAIN.index(pair[1].tier) if pair[1].tier in TIER_DOMAIN else len(TIER_DOMAIN),
            -(pair[1].max_percentile or 0.0),
        )
    )
    return [row for _offset, row in candidates]


def confirming_row(anchor: date, detected: Sequence[Any]):
    """The detected row that NAMES *anchor*'s confirmation, or ``None``.

    The nearest of :func:`confirming_rows`. Returning the ROW rather than a
    boolean is what lets the served confirmation name the confirming event,
    which the ratified requirement demands: "confirmed" with nothing behind it
    cannot be checked against the catalog it claims to summarize.
    """
    rows = confirming_rows(anchor, detected)
    return rows[0] if rows else None


def _detected_record(row) -> dict[str, Any]:
    event = event_from_row(row)
    candidate, note = _imagery(row.end_date)
    return {
        "id": row.event_key,
        "name": synthesize_name(event),
        # The imagery target is the PEAK day, not the span's first: the picker
        # centres its search window on `date`, and centring it on a wet spell's
        # first day points the sensor at the day before the water arrived.
        "date": row.peak_date.isoformat(),
        "description": synthesize_description(event),
        "severity": WIRE_SEVERITY_BY_TIER[row.tier],
        "tier": row.tier,
        "provenance": "detected",
        "curated": False,
        "confirmation": None,
        "confirmed_by": None,
        "start_date": row.start_date.isoformat(),
        "end_date": row.end_date.isoformat(),
        "peak_date": row.peak_date.isoformat(),
        "max_percentile": row.max_percentile,
        "fired_windows": row.fired_windows,
        "clipped_at_span_end": event.clipped_at_span_end,
        "imagery_candidate": candidate,
        "imagery_note": note,
        "dataset_disclosure": DATASET_DISCLOSURE,
        # NO `days_buffer`, deliberately (D9's ceiling): `typeGuards.ts:406-411`
        # rejects a restored selection outside [1, 30], so a buffer derived from
        # a long wet spell's duration would emit 40 and break the restore path.
        # The epoch default at `router_gee_support.py:502` applies instead.
    }


def _curated_record(row, confirming) -> dict[str, Any]:
    """One curated anchor, carrying its confirmation evidence when it has any.

    D8's precedence: when an anchor IS confirmed, the CURATED row wins the card
    -- its id, name, description and severity, the ones institutional memory
    knows -- and the detected row's tier, windows and percentile ride along as
    evidence. One card, not two: r1 served both into a picker with no dedup.
    """
    payload = dict(row.curated_payload or {})
    candidate, note = _imagery(row.end_date)
    for required in ("name", "description"):
        # LOUD, deliberately. `payload.get("name")` answering None recreates
        # CRITICAL-7 exactly: `isHistoricFlood` requires `name: string` and
        # DROPS the record silently, so a broken payload vanishes an anchor
        # from the picker with a 200 and no error anywhere. Every seeded anchor
        # (`lluvia_ext_002`) carries both fields, so their absence is a
        # violated assumption -- and a violated assumption should raise rather
        # than serve a card the frontend will delete on arrival.
        value = payload.get(required)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"curated event {row.event_key!r} has no usable {required!r} in its payload "
                f"(got {value!r}); the frontend drops a record without one silently"
            )
    record: dict[str, Any] = {
        "id": row.event_key,
        "name": payload["name"],
        "date": row.start_date.isoformat(),
        "description": payload["description"],
        # Verbatim from the payload (D8): `sep_2025` keeps `media` without
        # implying a tier for a row that was never ranked.
        "severity": payload.get("severity"),
        "tier": None,
        "provenance": "curated",
        "curated": True,
        "confirmation": NOT_CONFIRMED,
        "confirmed_by": None,
        "confirmation_label": NOT_CONFIRMED_LABEL,
        "start_date": row.start_date.isoformat(),
        "end_date": row.end_date.isoformat(),
        "peak_date": None,
        "max_percentile": None,
        "fired_windows": None,
        "imagery_candidate": candidate,
        "imagery_note": note,
        "dataset_disclosure": DATASET_DISCLOSURE,
    }
    for optional in ("sensor", "max_cloud", "days_buffer"):
        if optional in payload:
            record[optional] = payload[optional]
    if "days_buffer" in record:
        record["days_buffer"] = max(
            MIN_DAYS_BUFFER, min(MAX_DAYS_BUFFER, int(record["days_buffer"]))
        )

    if confirming is not None:
        offset = confirmation_offset_days(row.start_date, confirming)
        record.update(
            {
                "provenance": "detected",
                "tier": confirming.tier,
                "max_percentile": confirming.max_percentile,
                "fired_windows": confirming.fired_windows,
                "peak_date": confirming.peak_date.isoformat(),
                "confirmation": CONFIRMED,
                "confirmed_by": confirming.event_key,
                "confirmation_offset_days": offset,
                "confirmation_tolerance_days": CONFIRMATION_TOLERANCE_DAYS,
                "confirmation_label": (
                    f"curated, detector-confirmed by {confirming.event_key} "
                    f"({offset} day(s) from the curated date)"
                ),
            }
        )
    return record


def _descending(record: Mapping[str, Any]) -> int:
    """A sort key that puts the NEWEST `start_date` first inside a sort key
    tuple, where `reverse=True` would flip the other fields too."""
    return -date.fromisoformat(record["start_date"]).toordinal()


def _intersects_year(row, year: int | None) -> bool:
    if year is None:
        return True
    return row.start_date.year <= year <= row.end_date.year


def build_catalog_response(
    generation,
    *,
    tier: str = DEFAULT_TIER,
    year: int | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """The served payload for one generation, per D8/D9/D10/D11/D12.

    Order of operations is load-bearing. Confirmation is derived against the
    WHOLE served generation, not against the filtered page, or an anchor would
    read "confirmed" or "not confirmed" depending on which tier the caller
    asked for. Precedence then removes EVERY confirming detected row from the
    list -- one card per flood, at every tier -- and only afterwards is the
    result filtered, ordered and paginated.
    """
    detected = [row for row in generation.detected if row.tier == tier]
    confirming = {
        curated.event_key: confirming_rows(curated.start_date, generation.detected)
        for curated in generation.curated
    }

    # Only the anchors this response actually SERVES suppress anything. An
    # anchor filtered out by `year` carries no evidence into the payload, so
    # suppressing its confirming rows would delete the detector's own record of
    # that storm from the year the caller asked about -- a silent drop with a
    # 200, which is the failure this whole module is written against.
    served_curated = [row for row in generation.curated if _intersects_year(row, year)]
    suppressed = {
        row.event_key for anchor in served_curated for row in confirming[anchor.event_key]
    }

    curated_records = [
        _curated_record(row, confirming_row(row.start_date, generation.detected))
        for row in served_curated
    ]
    in_page = [row for row in detected if _intersects_year(row, year)]
    detected_records = [_detected_record(row) for row in in_page if row.event_key not in suppressed]
    # Rows merged INTO a curated card are still evidence the detector produced;
    # they are simply not their own card. `_absence` has to see them or it will
    # announce "no qualifying window" beside the very window it is denying.
    merged_into_a_card = [row for row in in_page if row.event_key in suppressed]
    # `max_percentile DESC, start_date DESC` (D12) as ONE key: two successive
    # `sort` calls would work by stability, and a later reader "simplifying"
    # them into the wrong order would silently reverse the tie-break.
    detected_records.sort(key=lambda record: (-record["max_percentile"], _descending(record)))

    # Curated rows are PINNED ahead of the page. An anchor that fell off page
    # two of a 144-row `alta` list would have been dropped by pagination, which
    # spec R4 forbids exactly as firmly as dropping it by filter.
    curated_records.sort(key=_descending)
    records = curated_records + detected_records

    return {
        "floods": records[offset : offset + limit],
        # UNCAPPED (D12): a `total` equal to `len(page)` makes every page look
        # like the last one, which is the bug this field exists to prevent.
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "tier": tier,
        "year": year,
        "coverage": dict(SERVED_COVERAGE),
        "imagery_golden_window": {
            "start": IMAGERY_GOLDEN_WINDOW[0].isoformat(),
            "end": IMAGERY_GOLDEN_WINDOW[1].isoformat(),
        },
        "catalog_span": _catalog_span(generation),
        "detector_revision": generation.revision,
        "revision_state": generation.revision_state,
        "absence": _absence(
            generation, has_detector_evidence=bool(detected_records or merged_into_a_card)
        ),
        "dataset_disclosure": DATASET_DISCLOSURE,
        "chirps_disclosure": CHIRPS_DISCLOSURE,
    }


def _catalog_span(generation) -> dict[str, str] | None:
    """The span the SERVED ROWS were ranked against, off their sealed columns.

    Never the module constants (the same rule :func:`event_from_row` states and
    every synthesized description already follows). A stale generation served
    after a constants bump -- exactly D12's rule-2 case, the one the deploy
    ordering makes routine -- would otherwise announce at the response root a
    span its own rows never saw, while each card underneath printed the true
    one. The root claim and the cards would disagree, and the root is the one a
    reader trusts for coverage.

    ``None`` when there is no generation to speak for: an empty catalog has no
    ranked span, and naming the constants would claim a catalog that does not
    exist yet.

    Uniform within a generation by construction -- D5 seals one constants block
    per ``detector_revision``, and :func:`repository.persist_events` refuses a
    row that disagrees with a persisted one at the same identity -- so more
    than one span here means the catalog is broken in a way no served payload
    can describe honestly. It raises rather than picking one.
    """
    spans = {
        (row.climatology_span_start, row.climatology_span_end)
        for row in generation.detected
        if row.climatology_span_start is not None and row.climatology_span_end is not None
    }
    if not spans:
        return None
    if len(spans) > 1:
        raise ValueError(
            f"generation {generation.revision!r} holds rows ranked against "
            f"{len(spans)} different climatology spans ({sorted(spans)}); "
            "no single catalog_span can describe it"
        )
    start, end = next(iter(spans))
    return {
        "start": start.isoformat(),
        # The frozen span is half-open; the served claim names the last day
        # that is actually IN it.
        "end": (end - timedelta(days=1)).isoformat(),
    }


def resolve_event(generation, event_key: str) -> dict[str, Any] | None:
    """The served record for one id inside *generation*, or ``None`` (D12).

    This is the imagery bridge's whole lookup, and it lives HERE rather than in
    the router for the reason this module's docstring gives: the list and the
    bridge answering "which events exist" from two renderings of the same
    contract is BLOCKER-1 arriving through the other door. Both callers get the
    same dict, built by the same two functions.

    Revision scoping is structural, not a filter written twice: *generation* is
    whatever ``read_events`` decided to serve -- current, or the previous one
    labelled stale -- so an id from a superseded generation is simply not in it,
    and the bridge can never hand out tiles for a card the list does not show.

    Curated first, matching D8's precedence: when an anchor is confirmed the
    curated row wins the card, and the bridge has to use the same record the
    picker rendered or the tiles would be searched around a different date.
    """
    for row in generation.curated:
        if row.event_key == event_key:
            return _curated_record(row, confirming_row(row.start_date, generation.detected))
    for row in generation.detected:
        if row.event_key == event_key:
            return _detected_record(row)
    return None


def _absence(generation, *, has_detector_evidence: bool) -> dict[str, str] | None:
    """Spec R6: an empty result is never a bare success.

    The absence is about the DETECTOR's evidence, which is why curated rows can
    be served beside one: "no detected event for this year" and "nothing at all
    for this year" are different statements, and collapsing them would let a
    year covered only by institutional memory read as a year the detector
    examined and cleared.

    *has_detector_evidence* counts rows SUPPRESSED into a curated card as
    evidence, not only the rows that kept their own card. Computing it from the
    post-suppression list instead reports `no_qualifying_window` while the
    window it denies is being served, merged, one field away -- a false reason
    beside a non-empty list, which R6 rates worse than no field at all.
    """
    if has_detector_evidence:
        return None
    if generation.revision_state == "empty":
        return {
            "reason": "incomplete_evidence",
            "detail": (
                "no detector generation has been persisted for this scope yet; "
                "run the full-span detector runbook"
            ),
        }
    return {
        "reason": "no_qualifying_window",
        "detail": (
            "no window in the served generation reached the requested tier for this selection"
        ),
    }
