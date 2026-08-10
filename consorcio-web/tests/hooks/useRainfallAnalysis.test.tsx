/**
 * useRainfallAnalysis.test.tsx  (Lluvia v2 — Task 3.1 RED)
 *
 * TanStack Query hooks for the Rainfall v2 ficha detail. Locks the behavior the
 * panel relies on:
 *   - no scope / no nomenclature → no fetch (idle, like `useFichaTerritorial`);
 *   - a queued (202) analysis keeps polling on a bounded interval so the panel
 *     can show a LABELLED pending state that resolves by itself;
 *   - once the snapshot is ready the polling stops;
 *   - the query key carries scope kind/id/version + year, so switching scope or
 *     year refetches instead of showing the previous result (staleness
 *     contract of the ficha).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../src/lib/api/rainfall', () => ({
  resolveRainfallScopes: vi.fn(),
  fetchRainfallAnalysis: vi.fn(),
}));

import { fetchRainfallAnalysis, resolveRainfallScopes } from '../../src/lib/api/rainfall';
import { useRainfallAnalysis, useRainfallScopes } from '../../src/hooks/useRainfallAnalysis';

const ZONE = { kind: 'zone' as const, id: 'zona-ne', version: '3' };

/** A labelled queued (202) answer for the default scope/year. */
function queuedAnswer() {
  return {
    type: 'queued' as const,
    queued: {
      status: 'queued' as const,
      outbox_id: 'ob-1',
      scope: ZONE,
      year: 2025,
      labels: ['analysis_missing'],
    },
  };
}

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe('useRainfallScopes', () => {
  beforeEach(() => vi.clearAllMocks());

  it('does not resolve when no nomenclature is selected', () => {
    renderHook(() => useRainfallScopes(null), { wrapper: wrapper() });
    expect(resolveRainfallScopes).not.toHaveBeenCalled();
  });

  it('resolves the parcel into regional scope choices', async () => {
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: true,
    });

    const { result } = renderHook(() => useRainfallScopes('13-06-01'), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(resolveRainfallScopes).toHaveBeenCalledWith(
      { kind: 'parcel', nomenclature: '13-06-01' },
      expect.anything()
    );
    expect(result.current.data?.kind).toBe('choices');
  });
});

describe('useRainfallAnalysis', () => {
  beforeEach(() => vi.clearAllMocks());

  it('does not fetch without a resolved scope', () => {
    renderHook(() => useRainfallAnalysis(null, 2025), { wrapper: wrapper() });
    expect(fetchRainfallAnalysis).not.toHaveBeenCalled();
  });

  it('returns a ready snapshot without polling', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: { analysis_revision_id: 'r1' } as never,
    });

    const { result } = renderHook(() => useRainfallAnalysis(ZONE, 2025), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.data?.type).toBe('ready'));
    expect(result.current.queued).toBe(false);
    // No polling once ready: exactly one request.
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(1);
  });

  it('keeps polling a queued analysis until the snapshot is ready', async () => {
    // The second response is DEFERRED so the queued state is observable before
    // the poll resolves — otherwise the 5 ms poll races waitFor's own interval
    // and "queued" flips to ready before it can ever be asserted.
    let release: (value: Awaited<ReturnType<typeof fetchRainfallAnalysis>>) => void = () => {};
    vi.mocked(fetchRainfallAnalysis)
      .mockResolvedValueOnce({
        type: 'queued',
        queued: {
          status: 'queued',
          outbox_id: 'ob-1',
          scope: ZONE,
          year: 2025,
          labels: ['analysis_missing'],
        },
      })
      .mockImplementation(
        () =>
          new Promise((resolve) => {
            release = resolve;
          })
      );

    const { result } = renderHook(() => useRainfallAnalysis(ZONE, 2025, { pollIntervalMs: 5 }), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.queued).toBe(true));
    // The queued answer keeps the poll alive.
    await waitFor(() =>
      expect(vi.mocked(fetchRainfallAnalysis).mock.calls.length).toBeGreaterThanOrEqual(2)
    );

    release({ type: 'ready', snapshot: { analysis_revision_id: 'r2' } as never });
    await waitFor(() => expect(result.current.data?.type).toBe('ready'));
    expect(result.current.queued).toBe(false);
  });

  it('refetches when the selected scope or year changes (no stale result)', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: { analysis_revision_id: 'r3' } as never,
    });

    const { result, rerender } = renderHook(
      ({ year }: { year: number }) => useRainfallAnalysis(ZONE, year),
      { wrapper: wrapper(), initialProps: { year: 2025 } }
    );
    await waitFor(() => expect(result.current.data?.type).toBe('ready'));

    rerender({ year: 2024 });

    await waitFor(() =>
      expect(fetchRainfallAnalysis).toHaveBeenCalledWith(ZONE, 2024, expect.anything())
    );
  });

  it('gives up after the consecutive-queued poll cap and stops polling for good', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue(queuedAnswer());

    const { result } = renderHook(
      () => useRainfallAnalysis(ZONE, 2025, { pollIntervalMs: 5, maxQueuedPolls: 3 }),
      { wrapper: wrapper() }
    );

    // The budget is exhausted: exactly the cap of queued answers, then a label.
    await waitFor(() => expect(result.current.gaveUp).toBe(true));
    expect(result.current.queued).toBe(true);
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(3);

    // No auto-refresh afterwards — the give-up is terminal, never silent polling.
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(3);
  });

  it('retry re-runs the fetch and resets the polling budget', async () => {
    let release: (value: Awaited<ReturnType<typeof fetchRainfallAnalysis>>) => void = () => {};
    vi.mocked(fetchRainfallAnalysis)
      .mockResolvedValueOnce(queuedAnswer())
      .mockResolvedValueOnce(queuedAnswer())
      .mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }))
      .mockResolvedValue(queuedAnswer());

    const { result } = renderHook(
      () => useRainfallAnalysis(ZONE, 2025, { pollIntervalMs: 5, maxQueuedPolls: 2 }),
      { wrapper: wrapper() }
    );

    await waitFor(() => expect(result.current.gaveUp).toBe(true));
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(2);

    result.current.retry();

    // The manual retry re-runs the query; while in flight the budget is reset,
    // so the stale queued answer is no longer terminal.
    await waitFor(() => expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(3));
    expect(result.current.gaveUp).toBe(false);
    expect(result.current.queued).toBe(true);

    // A fresh queued answer restarts the budget: pending first, then give-up.
    release(queuedAnswer());
    await waitFor(() => expect(result.current.gaveUp).toBe(true));
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(4);
  });

  it('starts a fresh polling budget when the scope or year changes', async () => {
    let release: (value: Awaited<ReturnType<typeof fetchRainfallAnalysis>>) => void = () => {};
    vi.mocked(fetchRainfallAnalysis)
      .mockResolvedValueOnce(queuedAnswer())
      .mockResolvedValueOnce(queuedAnswer())
      .mockResolvedValueOnce(queuedAnswer())
      .mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }))
      .mockResolvedValue(queuedAnswer());

    const { result, rerender } = renderHook(
      ({ year }: { year: number }) =>
        useRainfallAnalysis(ZONE, year, { pollIntervalMs: 5, maxQueuedPolls: 2 }),
      { wrapper: wrapper(), initialProps: { year: 2025 } }
    );

    await waitFor(() => expect(result.current.gaveUp).toBe(true));
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(2);

    rerender({ year: 2024 });

    // A new selection is pending again (budget reset), never instantly
    // terminal; the next poll stays deferred so the intermediate state holds.
    await waitFor(() => expect(result.current.queued).toBe(true));
    expect(result.current.gaveUp).toBe(false);
    await waitFor(() => expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(4));
    expect(result.current.gaveUp).toBe(false);

    // And the fresh budget eventually gives up again.
    release(queuedAnswer());
    await waitFor(() => expect(result.current.gaveUp).toBe(true));
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(4);
  });
});
