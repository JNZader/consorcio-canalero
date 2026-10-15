# Elevation profile coverage

The elevation profile must follow a road's complete trace. Today it follows one
longitudinal path chosen from the selected tramos: 38 of 83 roads (231.4 km of
740.1) have no profile coverage, one road shows 46 m of a 7.32 km trace, and
another reports 150% of its own length.

Acceptance cases measured against production data: **T027-01** (0.6% coverage),
**S331** (56.9%), **A581** (150.3%).

## Specs

- **S1** — The profile's trace must cover the selected road's tramos.
  Verbatim: "varios caminos tienen cortes...por ejemplo el s331....oel s384...
  el tema es que.....no sigue la traza completa el perfil de elevacion...."
- **S2** — The fix is judged on the whole population, not on the two examples.
  Verbatim: "ya pero te di dos ejemplos...no se si hay mas caminos con ese problema"
- **S3** — All three measured failure modes are in scope.
  Verbatim: "dale arregla todos"
- **S4** — Analyze the private road layer as a possible source for the missing
  tramos. Verbatim: "hay algo que me gustaria analices...porq hay una capa de
  caminos que es privada...quiza si completamos los tramos faltantes con esos
  seria mas facil..."

## Tasks

| ID | Specs | Route | Commit |
| --- | --- | --- | --- |
| T1 | S1, S3 | `consorcio-web/src/components/map2d/mergeLineStringTramos.ts`: the two extensions of `pathThroughEdge` now share one consumed-edge and consumed-node set, and the axis is the longest path over every edge instead of the one through `pieces[0]`. Unit tests in `tests/unit/mergeLineStringTramos.test.ts`. | `8b996390` |
| T2 | S2 | Re-ran the 83-road production sweep with the real frontend functions. Result: coverage 508.7 -> 566.2 km of 740.1 (68.7% -> 76.5%), inflated roads 2 -> 0, T027-01 0.6% -> 99.4%. Still 174.0 km uncovered across 39 roads, so mode 2 survives T1 and T3 is needed. | evidence, no commit |
| T3a | S1, S2 | Backend half: `geometry` accepts a MultiLineString, every part is sampled with one shared step, each point carries `parte`, chainage accumulates, and a single LineString keeps today's exact payload. Tests in `tests/new/test_elevation_profile_cache.py`. | `deb896c6` |
| T3b | S1, S2 | Frontend half: `mergeLineStringParts` builds one part per selected tramo (ordered by tramo id ascending, deduped), the chart accepts a MultiLineString and breaks the line at each jump, and `groupSelectionSummary` reports the whole trace km. | `5512662f` |
| T4 | S1, S2, S3 | Live verification after the deploy: POST a multi-part trace for T027-01, S331 and A581 against the production API and re-run the sweep. The multi-part backend is not live until then. | |
| T4 | S1, S2, S3 | Verify T027-01, S331 and A581 against the production API, then re-run the full sweep; report the before/after per road. | |
| T5 | S4 | Separate ticket, not part of this fix: 140 km of OSM/IGN roads are absent from the official red vial, and the local layer is a clip of the 39 127-feature provincial one. That is map completeness, not profile coverage. | |

## T3 design (multi-part profile)

Mode 2 survives T1: one longitudinal path cannot cover a branched road, so the
profile must sample every part and say where the jumps are.

- **Request**: `geometry` accepts a GeoJSON `MultiLineString` as well as a
  `LineString` (same field, one more type). The frontend builds the parts from the
  selected tramos, **ordered by the tramo id ascending** so the same selection
  always produces the same bytes.
- **Payload**: every point gains `parte` (0-based part index); `distance_m` keeps
  accumulating across parts so the X axis stays monotonic; a top-level `partes`
  count is added. The gap between two parts is a real break in the terrain, never
  a straight line sampled across it.
- **Cache key**: the canonical geometry must canonicalise a part list — parts in
  the given order, each part's coordinates canonicalised as today. Same selection,
  same key, or the cache never hits.
- **Caps**: `MAX_POINTS` applies to the total, so `paso_muestreo` is computed per
  part and the budget is allocated proportionally: 15 m while everything fits,
  coarser per part when it does not. `MAX_LENGTH_M` applies to the sum.
- **Chart**: split `puntos` by `parte` into one series per part so the line breaks
  at each jump (`connectNulls={false}` already covers a null in the terrain, but a
  part boundary must not draw a segment across the gap). The cursor and range
  features search across all parts.
- **Map trace**: the trace source takes the same multi-part geometry, so the
  highlighted trace covers every tramo instead of one path.
- **Tests**: backend (a multi-part trace samples every part, the part index is
  contiguous, the cache key ignores part order changes only when the order is
  canonical, a single LineString behaves exactly as before); frontend (the parts
  are built from the tramos and deduped, the chart splits per part).
- **Acceptance**: after T3 the sweep must report 0 roads under 99% coverage and 0
  inflated roads, with T027-01, S331 and A581 re-verified against the production
  API.

## Log

- **L1** — "hay algo q veo no esta funcionando bien...varios caminos tienen cortes...por ejemplo el s331....oel s384... el tema es que.....no sigue la traza completa el perfil de elevacion...."
- **L2** — "ya pero te di dos ejemplos...no se si hay mas caminos con ese problema"
- **L3** — "dale arregla todos...pero hay algo que me gustaria analices...porq hay una capa de caminos que es privada...quiza si completamos los tramos faltantes con esos seria mas facil..."
- **L4** (evidence, sweep with the real frontend functions via Node 26): 380 tramos, 83 roads. 38 affected, 45 OK. 740.1 km real, 508.7 km covered, 231.4 km (31%) uncovered. Buckets: <50% 8 roads (110.2 km), 50-75% 16 (99.4 km), 75-90% 11 (20.0 km), 90-99% 3 (4.4 km). Worst: T027-01 0.6%, CRN9 2.5%, T135-11 9.1%, T135-09 21.5%, T269-08 28.6%; S331 56.9%, S384 63.2%.
- **L5** (evidence, three modes): (1) anchoring — the axis is seeded at `pieces[0]`, so T027-01's stray duplicated 45.6 m piece becomes the whole profile; (2) partial coverage by design — the longest simple path through the seed, branches and disconnected leftovers excluded on purpose; (3) inflation — the axis walks two representations of the same stretch, A581 150.3% and T028-19 108.9%.
- **L6** (evidence, S4 answered): adding the provincial tramos inside the local bbox does NOT fix coverage. S331 56.9% -> 56.2% (axis 29.10 -> 31.00 km), S384 unchanged, CRN9 unchanged, T135-11 unchanged, T027-01 0.6% -> 28.7% (anchoring still broken), A581 150.3% -> 156.3% (inflation worse). The local layer is a clip of the 39 127-feature provincial layer (T135-11 is byte-identical in both: 7 tramos / 39.95 km).
- **L7** (decision): stage A first (dedupe + global axis choice, no API contract change), then measure, and only then decide on the multi-part work.
- **L8** (T1 done, commit `8b996390`): the root cause of mode 3 turned out to be the two independent searches in `pathThroughEdge`, not duplicated geometry — measured with a probe that counts axis segments which are not real edges: A581 axis 4.162 km vs 2.331 km of unique segments (1.831 km re-walked, 44%), T028-19 15.480 vs 9.363 km (40%), S331 clean. RED first: two new tests (a four-tramo loop and a stray first piece) failed on the old code for exactly those reasons; GREEN 14/14 including the twelve existing ones, so the intended "stem, not branches" behaviour is untouched. Full frontend suite: 4631 passed, 3 failed in 2 files, none of them touching this module (patchesApplied checks a node_modules patch version).
- **L9** (T2 measured, same data and two implementations side by side): T027-01 0.6% -> 99.4%, A581 150.3% -> 88.3%, T028-19 108.9% -> 85.0%, CRN9 2.5% -> 28.8%, T135-11 9.1% -> 68.1%, S384 63.2% -> 77.3%, S331 56.9% -> 58.8%. Totals 508.7 -> 566.2 km of 740.1 (68.7% -> 76.5%); inflated roads 2 -> 0. The affected count rose 38 -> 39 only because the two inflated roads used to be counted as healthy. Decision: 174.0 km remain uncovered across 39 roads, so mode 2 survives and T3 is required.
- **L10** (T3a done, commit `deb896c6`): the backend accepts a GeoJSON MultiLineString, samples every part with one shared step (MAX_POINTS is a total budget, or a 27-tramo road would ask for 27x the samples), tags every point with `parte`, accumulates chainage across parts and reports `partes`. A single LineString keeps its exact previous payload, so existing consumers and cached rows stay valid, and the part order is part of the cache key. Tests: five new (unir_perfiles, multi-part sampling, the single-line shape, the cache key) plus the existing stubs updated for the new `paso_m` parameter; 34 passed, ruff clean. Next: T3b, the frontend half.
- **L11** (T3b done, commit `5512662f`): `mergeLineStringParts` builds one part per selected tramo, ordered by tramo id ascending, and the chart breaks the line at each part boundary with a null row. Measured after the dedupe: parts total 740.1 km against 740.1 km deduped, so **100.0% coverage and no road over 101%** (five were over before the dedupe, T391-09 at 200% because the source carries the same 1.899 km twice). Acceptance cases T027-01, S331, A581, CRN9 and S384 all at 100.0%. The dedupe keeps two routes between the same ends when their lengths differ by more than 25%, because that is a real detour. Tests: 19 in the merge file, 36 in the touched files, biome clean with the same two pre-existing warnings; the full suite is 4637 passed with the same three pre-existing environment failures. The live check against production is T4, after the deploy.
