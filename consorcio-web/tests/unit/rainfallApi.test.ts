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
  downloadRainfallCsv,
  fetchRainfallAnalysis,
  resolveRainfallScopes,
} from '../../src/lib/api/rainfall';

const ZONE = { kind: 'zone' as const, id: 'zona-ne', version: '3' };
const BASIN = { kind: 'basin' as const, id: 'zo-12', version: 'abc123' };

function snapshot() {
  return {
    analysis_revision_id: '11111111-2222-3333-4444-555555555555',
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
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
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
      .mockResolvedValue(csvResponse(false, { detail: 'No autorizado' }, 403)) as unknown as typeof fetch;

    await expect(downloadRainfallCsv('rev-x')).rejects.toThrow('No autorizado');
  });
});
