# Proposal: Lluvia Insights — Rainfall v2 Product Layer

## Intent

Rainfall v2 materializes only `annual.selected` (`compute.py:71-189`). The accepted spec already MUSTs normal, percentile, d7/d30/d90 antecedents and a report-style summary (`specs/rainfall-analysis/spec.md:67,92-99`), and the archived design fixed that envelope (`archive/2026-08-07-lluvia-v2/design.md:22`). Staff get one number with no reference, so "¿llovió mucho?" is unanswerable and nothing is reportable. This closes the spec-vs-implementation gap and makes the answer legible.

## Scope

### In Scope

- **Backfill** 1991-2020 CHIRPS v3 Final daily intervals via existing `backfill_missing` (`tasks.py:947`) — one call per (scope, year), checkpointed and idempotent.
- **`annual.normal` + `annual.percentile`** (empirical Weibull rank), reusing `comparison_end`/`baseline_dates`/`baseline_years_for` verbatim (`temporal.py:10,20,98`).
- **`antecedents.{d7,d30,d90}`** via `rolling_total` (`temporal.py:70`).
- **`summary`** group (root key already allow-listed, `service.py:142-155`).
- **Policy thresholds** per new metric — without them `apply_metric_policy` force-suppresses as `policy_threshold_unset` (`policy.py:160-165,189-194`).
- **Friendly export**: NEW staff-gated two-sheet xlsx (Resumen + Serie diaria) via `openpyxl` (`requirements.txt:59`); audit CSV route untouched.
- **Frontend**: activate wired-but-dead renderers (`RainfallMetricList.tsx:63-99`) + net-new accumulated-curve chart (recharts, already used by `PrecipChart.tsx:43`).

### Out of Scope

- Basin → GEE asset mapping (see Scope Decision).
- QW9 public three-numbers header — deferred, needs its own spec delta.
- Event catalogue, return periods, ENSO/SPI, Sentinel, sub-daily intensity, gauges, recurrence, public exposure (`spec.md:517`).

## Scope Decision

- **Mode**: **Selective**
- **Justification**: The incoming scope says "backfill per zone/basin", but the provider seam maps *every* zone id to one asset and rejects DB-resolved basin ids (`adapters/gee_client.py:33-46` requires `candil|ml|noroeste|norte`; the resolver emits `zonas_operativas.id::text` UUIDs, `repository.py:132`). So the highest-value subset is the zone-asset backfill plus the spec-required metric closure — **30 distinct GEE year-reductions, one-shot**. Basin coverage is a pre-existing gap that would 5× the GEE bill and needs a DB→asset mapping decision; deferred to its own change. The xlsx export is the only non-spec-required item and is sequenced last so it stays droppable.

## Decisions (owner review — recommended, not assumed)

| Question | Recommendation |
|---|---|
| QW9 public numbers | **Staff-only here.** `spec.md:19-25` forbids exposing v2 detail to visitors; public exposure = its own delta. |
| Window vocabulary | **Reuse d7/d30/d90.** "Campaña desde 1-sep" only as a *display preset over a calendar-year analysis*, never an analysis period (`spec.md:67`). |
| Percentile method | **Empirical Weibull rank** over the 30 baseline cumulatives; no Gumbel for v1. |
| `comparison_end` | **Do not redesign.** Reuse the shipped rule; the chart MUST show both the comparison date and `available_through`. |

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `rainfall-analysis`: add a staff-gated **friendly report export** requirement (xlsx: metric summary + daily series) with CSV-parity state semantics (`spec.md:491-513`); if the campaign preset ships, clarify a campaign **display window** is not an analysis period. The metric *outcomes* need **no** spec change — already required. Judgment Day round 1 added two disclosure requirements the outcomes alone did not cover: **summary coherence** with the post-policy disclosed states (owner decision 2026-08-10: `summary` is a narrative, not a thresholded metric — the threshold list cedes) and **series/snapshot consistency** for the daily series served against a stored revision.

## Approach

1. `backfill_missing(source_id="chirps-v3-final", role="historical", scope_kind="zone", …, year=Y)` for 1991..2020; resumable via `RainfallBackfillCheckpoint`, append-only `persist_intervals`. Dedupe by provider asset — all zone ids collapse to `zona_cc_ampliada`, so per-feature invocation multiplies identical reductions.
2. `build_snapshot` grows the new keys from persisted intervals. `normalize_snapshot` needs **zero** structural change (`service.py:19,429-448` iterate `METRIC_GROUPS` generically).
3. Add policy entries; bump `RAINFALL_METRIC_POLICY_REVISION`.
4. New xlsx route beside `GET /rainfall/analyses/{revision}.csv`, same `require_admin_or_operator` boundary.
5. Frontend: populate renderers, add curve; public `PrecipChart` path untouched.

Scope population is JSONB data, not inferable from code — count at apply time:

```sql
SELECT count(DISTINCT COALESCE(f->'properties'->>'zone_id', f->>'id')) AS zone_scopes
FROM geo_approved_zonings z
CROSS JOIN LATERAL jsonb_array_elements(CAST(z.feature_collection AS jsonb)->'features') AS f
WHERE z.is_active;
SELECT count(*) AS basins FROM zonas_operativas;
```

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `geo/rainfall/compute.py` | Modified | New metric groups + percentile helper |
| `geo/rainfall/policy.py` | Modified | Thresholds per metric; revision bump |
| `geo/rainfall/temporal.py` | Modified | Reused as-is; possible pure percentile-rank fn |
| `geo/rainfall/tasks.py` | Modified | 1991-2020 backfill orchestration |
| `geo/rainfall/router.py` | New route | xlsx export (auth unchanged) |
| `consorcio-web/src/components/map2d/rainfall/` | Modified/New | Activate renderers; accumulated-curve chart |
| `openspec/specs/rainfall-analysis/spec.md` | Delta | Export requirement (+ preset clarification) |
| `PrecipChart.tsx`, `ficha_service.py`, `generate_chirps_normals.py` | Untouched | Public compact normal stays (`spec.md:11`) |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| GEE quota on backfill | Med | Bounded: 30 year-reductions for one zone asset; dedupe by asset; checkpointed; off the request path |
| New metrics self-suppress | High if missed | Policy entries are a first-class task with a test asserting no `policy_threshold_unset` |
| Percentile on tiny n (Feb-29) | Low | `baseline_years_for` yields ~7-8 leap years; suppress below a minimum n rather than publish a misleading rank |
| Campaign preset read as analysis period | Med | Display-only toggle with explicit labelling, or defer |
| Basin analysis stays unavailable | High (pre-existing) | Deferred + documented; `UnknownProviderScope` is a `ValueError` uncaught by the `ee.EEException` handler (`gee_client.py:87-92`) → backlog, not fixed here |
| Divergent date rule across the three numbers | Low | Reuse `comparison_end`/`baseline_dates` verbatim; assert by test |

## Rollback Plan

1. **Metrics**: drop the new `RAINFALL_METRIC_POLICY` entries and bump the revision → the metrics self-suppress as `policy_threshold_unset` (`policy.py:162-163`); snapshots stay valid, the UI already renders suppressed states, `annual.selected` unaffected.
2. **Export**: revert the xlsx route; audit CSV contract untouched.
3. **Frontend**: revert the chart commit; renderers degrade when the backend omits fields.
4. **Backfilled intervals**: append-only evidence — leave them; re-running is idempotent.

Impacted contracts: snapshot envelope (additive only), `RAINFALL_METRIC_POLICY_REVISION`, new export route. No migration, no breaking API change.

## Dependencies

- GEE service account + quota (`GEE_SERVICE_ACCOUNT_KEY`, `GEE_PROJECT_ID`).
- CHIRPS v3 Final eligible for the `historical` role under the evidence gate (`spec.md:435,439-444`).
- `openpyxl` and `recharts` already present — no new dependency.

## Success Criteria

- [ ] 1991-2020 daily intervals persisted for every provider-reachable zone scope; backfill resumes after interruption.
- [ ] An analysis returns `annual.{selected,normal,percentile}` and `antecedents.{d7,d30,d90}` as `available` — none `policy_threshold_unset` — plus a `summary` narrative that names the same states those metrics disclose (owner decision 2026-08-10: `summary` is a narrative, not a thresholded metric, so it carries no state of its own).
- [ ] Normal and percentile end on the same calendar date as `selected` for the current year (asserted by test).
- [ ] xlsx export delivers both sheets and preserves partial/suppressed/unavailable/provisional states; audit CSV contract unchanged.
- [ ] The panel shows the year-vs-normal curve and discloses both the comparison end and `available_through`.
- [ ] Public ficha rainfall output identical to pre-change.
