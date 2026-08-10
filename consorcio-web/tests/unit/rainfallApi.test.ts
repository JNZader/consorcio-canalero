/**
 * rainfallApi.test.ts  (Lluvia v2 — Task 3.1 RED)
 *
 * Contract tests for `src/lib/api/rainfall.ts`, the authenticated Rainfall v2
 * client. The wire contract mirrors the backend router
 * (`gee-backend/app/domains/geo/rainfall/router.py`):
 *   - POST /geo/rainfall/scopes:resolve — parcel → ordered zone/basin choices
 *     flagged as regional estimates; zone/basin → one executable scope.
 *   - POST /geo/rainfall/analyses — 200 snapshot OR 202 queued-with-labels; the
 *     client must surface the queued state as data, never as an infinite
 *     spinner (spec "Supported Analysis Scope", design "missing work is queued
 *     and labelled").
 *   - GET  /geo/rainfall/analyses/{revision}.csv — authorized CSV export; the
 *     bearer token travels in the header, never in the URL.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../src/lib/api/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../src/lib/api/core')>();
  return { ...actual, apiFetch: vi.fn(), getAuthToken: vi.fn() };
});

import { apiFetch, getAuthToken } from '../../src/lib/api/core';
import {
  type RainfallAnalysisSnapshot,
  downloadRainfallCsv,
  fetchRainfallAnalysis,
  resolveRainfallScopes,
} from '../../src/lib/api/rainfall';

const ZONE = { kind: 'zone' as const, id: 'zona-ne', version: '3' };
const BASIN = { kind: 'basin' as const, id: 'zo-12', version: 'abc123' };

// Annotated on purpose: the return type is the contract under test, so an
// object literal carrying a field the interface does not declare is a
// compile-time error rather than an untyped extra that silently survives.
function snapshot(): RainfallAnalysisSnapshot {
  return {
    analysis_revision_id: '11111111-2222-3333-4444-555555555555',
    // The revision's own content address (backend design.md D3): the /series
    // response echoes it, so a tab holding this snapshot can detect that the
    // daily data moved underneath the analysis it drew.
    data_revision: 'ab'.repeat(32),
    scope: ZONE,
    regional_estimate: true,
    year: 2025,
    comparison_end: '2025-12-31',
    baseline: '1991-2020',
    annual: {},
    summary: 'Año húmedo.',
    source_health: { 'chirps-v3-final': 'ok' },
  };
}

describe('resolveRainfallScopes', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.clearAllMocks());

  it('POSTs the parcel nomenclature to scopes:resolve', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ choices: [ZONE, BASIN], regional_estimate: true });

    const result = await resolveRainfallScopes({ kind: 'parcel', nomenclature: '13-06-01' });

    expect(apiFetch).toHaveBeenCalledWith('/geo/rainfall/scopes:resolve', {
      method: 'POST',
      body: JSON.stringify({ kind: 'parcel', nomenclature: '13-06-01' }),
      signal: undefined,
    });
    expect(result).toEqual({ kind: 'choices', choices: [ZONE, BASIN], regional_estimate: true });
  });

  it('returns a single executable scope for a zone/basin request', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ scope: ZONE, regional_estimate: false });

    const result = await resolveRainfallScopes({ kind: 'zone', id: 'zona-ne', version: '3' });

    expect(result).toEqual({ kind: 'scope', scope: ZONE, regional_estimate: false });
  });

  it('strips the server-embedded regional_estimate flag from a single scope', async () => {
    // Same leak as the choices branch: the backend serializes the full
    // AnalysisScope dataclass for a direct zone/basin request too, so the
    // resolved scope carries a nested `regional_estimate` flag that /analyses
    // rejects (extra="forbid"). The client must normalize before re-sending.
    const serverScope = { ...ZONE, regional_estimate: true };
    vi.mocked(apiFetch).mockResolvedValue({ scope: serverScope, regional_estimate: true });

    const result = await resolveRainfallScopes({ kind: 'zone', id: 'zona-ne', version: '3' });

    expect(result).toEqual({ kind: 'scope', scope: ZONE, regional_estimate: true });
    if (result.kind === 'scope') {
      expect(result.scope).not.toHaveProperty('regional_estimate');
    }
  });

  it('strips the server-embedded regional_estimate flag from each choice', async () => {
    // The backend serializes the full AnalysisScope dataclass, so each choice
    // carries a nested `regional_estimate` flag. The wire contract for a scope
    // reference is flat {kind,id,version} and /analyses forbids extra fields
    // (extra="forbid"), so the client must normalize before re-sending.
    const serverChoices = [
      { ...ZONE, regional_estimate: true },
      { ...BASIN, regional_estimate: true },
    ];
    vi.mocked(apiFetch).mockResolvedValue({ choices: serverChoices, regional_estimate: true });

    const result = await resolveRainfallScopes({ kind: 'parcel', nomenclature: '13-06-01' });

    expect(result).toEqual({ kind: 'choices', choices: [ZONE, BASIN], regional_estimate: true });
    for (const choice of result.kind === 'choices' ? result.choices : []) {
      expect(choice).not.toHaveProperty('regional_estimate');
    }
  });
});

describe('fetchRainfallAnalysis', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs the resolved scope and year, returning a ready snapshot', async () => {
    vi.mocked(apiFetch).mockResolvedValue(snapshot());

    const result = await fetchRainfallAnalysis(ZONE, 2025);

    expect(apiFetch).toHaveBeenCalledWith('/geo/rainfall/analyses', {
      method: 'POST',
      body: JSON.stringify({ scope: ZONE, year: 2025 }),
      signal: undefined,
    });
    expect(result.type).toBe('ready');
    if (result.type !== 'ready') throw new Error('expected ready');
    expect(result.snapshot.analysis_revision_id).toBe(snapshot().analysis_revision_id);
    expect(result.snapshot.regional_estimate).toBe(true);
  });

  it('snapshot type carries data_revision', async () => {
    // Task 3a.14: the server-side pin on /series is authoritative, but the
    // cheap client cross-check ("does the series I just fetched still belong
    // to the snapshot this tab is holding?") needs the snapshot's own
    // `data_revision` to be part of the typed contract, not an untyped extra.
    vi.mocked(apiFetch).mockResolvedValue(snapshot());

    const result = await fetchRainfallAnalysis(ZONE, 2025);

    if (result.type !== 'ready') throw new Error('expected ready');
    const served: RainfallAnalysisSnapshot = result.snapshot;
    expect(served.data_revision).toBe('ab'.repeat(32));
  });

  it('maps a 202 queued body to a labelled queued result (never silent)', async () => {
    const queued = {
      status: 'queued',
      outbox_id: 'ob-1',
      scope: ZONE,
      year: 2025,
      labels: ['analysis_missing', 'role:historical'],
    };
    vi.mocked(apiFetch).mockResolvedValue(queued);

    const result = await fetchRainfallAnalysis(ZONE, 2025);

    expect(result).toEqual({ type: 'queued', queued });
  });
});

describe('downloadRainfallCsv', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getAuthToken).mockResolvedValue('token-123');
  });

  function csvResponse(ok: boolean, body: unknown, status = 200): Response {
    return {
      ok,
      status,
      json: async () => body,
      blob: async () => new Blob(['metric,value'], { type: 'text/csv' }),
    } as unknown as Response;
  }

  it('GETs the revision CSV with the bearer token in the header and downloads it', async () => {
    const fetchMock = vi.fn().mockResolvedValue(csvResponse(true, {}));
    global.fetch = fetchMock as unknown as typeof fetch;

    const clicked: string[] = [];
    const createObjectURL = vi.fn().mockReturnValue('blob:csv');
    const revokeObjectURL = vi.fn();
    window.URL.createObjectURL = createObjectURL;
    window.URL.revokeObjectURL = revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      clicked.push(this.download);
    });

    await downloadRainfallCsv('rev-1');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v2/geo/rainfall/analyses/rev-1.csv');
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer token-123');
    expect(clicked).toHaveLength(1);
    expect(clicked[0]).toContain('.csv');
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:csv');
    clickSpy.mockRestore();
  });

  it('throws the server detail on a denied export without disclosing data', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(
        csvResponse(false, { detail: 'No autorizado' }, 403)
      ) as unknown as typeof fetch;

    await expect(downloadRainfallCsv('rev-x')).rejects.toThrow('No autorizado');
  });
});
