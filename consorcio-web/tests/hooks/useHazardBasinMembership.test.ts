import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HAZARD_BASIN_FILTER_ALL } from '../../src/components/map2d/hazardBasinFilter';
import { useHazardBasinMembership } from '../../src/hooks/useHazardBasinMembership';
import { apiFetch } from '../../src/lib/api/core';
import { useAuthStore } from '../../src/stores/authStore';
import { createQueryWrapper } from '../test-utils';

vi.mock('../../src/lib/api/core', () => ({ apiFetch: vi.fn() }));

const mockedApiFetch = vi.mocked(apiFetch);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((currentResolve) => {
    resolve = currentResolve;
  });
  return { promise, resolve };
}

beforeEach(() => {
  act(() => {
    useAuthStore.setState({
      user: { id: 'operator-1', email: 'operator@example.com' },
      loading: false,
      initialized: true,
    });
  });
});

afterEach(() => {
  vi.clearAllMocks();
  act(() => {
    useAuthStore.setState({ user: null, loading: true, initialized: false });
  });
});

describe('useHazardBasinMembership', () => {
  it('maps the protected wire response to HazardBasinMembership', async () => {
    mockedApiFetch.mockResolvedValue({
      basin_id: 'basin-a',
      feature_id_property: 'nomenclatura',
      intersecting_feature_ids: ['19-01-002', '19-01-001'],
    });

    const { result } = renderHook(() => useHazardBasinMembership('basin-a'), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApiFetch).toHaveBeenCalledWith('/geo/basins/basin-a/catastro-membership');
    expect(result.current.membership).toEqual({
      featureIdProperty: 'nomenclatura',
      intersectingFeatureIds: ['19-01-002', '19-01-001'],
    });
  });

  it('does not fetch for null or all-basin selection', () => {
    const wrapper = createQueryWrapper();
    const { result, rerender } = renderHook(
      ({ basinId }: { basinId: string | null | typeof HAZARD_BASIN_FILTER_ALL }) =>
        useHazardBasinMembership(basinId),
      { initialProps: { basinId: null }, wrapper }
    );

    expect(result.current.membership).toBeNull();
    rerender({ basinId: HAZARD_BASIN_FILTER_ALL });
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it('surfaces request errors instead of treating them as empty membership evidence', async () => {
    mockedApiFetch.mockRejectedValue(new Error('Forbidden'));

    const { result } = renderHook(() => useHazardBasinMembership('basin-a'), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.membership).toBeNull();
    expect(result.current.error).toEqual(new Error('Forbidden'));
  });

  it('keeps the current basin membership when a prior basin response settles late', async () => {
    const basinA = deferred<{
      basin_id: string;
      feature_id_property: 'nomenclatura';
      intersecting_feature_ids: string[];
    }>();
    const basinB = deferred<typeof basinA extends { promise: Promise<infer T> } ? T : never>();
    mockedApiFetch.mockImplementation((endpoint: string) =>
      endpoint.includes('/basin-a/') ? basinA.promise : basinB.promise
    );
    const wrapper = createQueryWrapper();
    const { result, rerender } = renderHook(
      ({ basinId }: { basinId: string }) => useHazardBasinMembership(basinId),
      { initialProps: { basinId: 'basin-a' }, wrapper }
    );

    rerender({ basinId: 'basin-b' });
    basinB.resolve({
      basin_id: 'basin-b',
      feature_id_property: 'nomenclatura',
      intersecting_feature_ids: ['B-01'],
    });
    await waitFor(() => expect(result.current.membership?.intersectingFeatureIds).toEqual(['B-01']));

    basinA.resolve({
      basin_id: 'basin-a',
      feature_id_property: 'nomenclatura',
      intersecting_feature_ids: ['A-01'],
    });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(result.current.membership?.intersectingFeatureIds).toEqual(['B-01']);
  });
});
