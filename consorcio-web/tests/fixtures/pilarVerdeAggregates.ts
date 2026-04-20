/**
 * pilarVerdeAggregates (fixture re-export)
 *
 * Pinned copy of the real `consorcio-web/public/data/pilar-verde/aggregates.json`.
 * The JSON file next to this module is BYTE-FOR-BYTE identical to the production
 * asset at the time it was captured — any schema drift in the ETL (schema_version
 * bump, new fields, renames) MUST force a re-sync by a human.
 *
 * Re-sync protocol:
 *   1. Run `python scripts/etl_pilar_verde.py` against real IDECor.
 *   2. `cp consorcio-web/public/data/pilar-verde/aggregates.json \
 *         consorcio-web/tests/fixtures/pilarVerdeAggregates.json`
 *   3. Re-run the frontend suite. Failures here pin consumer code to the new
 *      schema — fix them explicitly, do NOT "fix the fixture" without updating
 *      the schema version literal in `src/types/pilarVerde.ts::AggregatesFile`.
 *
 * JSON disallows comments, so this .ts sibling carries the pin policy. Tests
 * import the default export (the JSON tree) OR the typed `aggregates` value
 * below — both are the same object reference at runtime.
 */
import type { AggregatesFile } from '../../src/types/pilarVerde';
import raw from './pilarVerdeAggregates.json';

/** Typed view of the pinned aggregates fixture — same reference as `raw`. */
export const pilarVerdeAggregatesFixture = raw as unknown as AggregatesFile;

export default pilarVerdeAggregatesFixture;
