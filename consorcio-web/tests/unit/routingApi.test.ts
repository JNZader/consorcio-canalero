import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.stubGlobal('import', {
  meta: {
    env: {
      PUBLIC_API_URL: 'http://localhost:8000',
    },
  },
});

describe('routingApi', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.resetModules();
    global.fetch = mockFetch;
    mockFetch.mockReset();
  });

  it('posts corridor routing payload', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          source: { id: 1 },
          target: { id: 2 },
          summary: {
            mode: 'raster',
            profile: 'hidraulico',
            total_distance_m: 1234,
            edges: 4,
            corridor_width_m: 50,
            penalty_factor: 2,
            cost_breakdown: {
              profile: 'hidraulico',
              edge_count_with_profile_factor: 3,
              avg_profile_factor: 0.84,
              max_profile_factor: 1,
              min_profile_factor: 0.72,
            },
          },
          centerline: { type: 'FeatureCollection', features: [] },
          corridor: null,
          alternatives: [],
        }),
    });

    const { routingApi } = await import('../../src/lib/api/routing');
    const result = await routingApi.getCorridor({
      from_lon: -63,
      from_lat: -32,
      to_lon: -63.1,
      to_lat: -32.1,
      mode: 'raster',
      profile: 'hidraulico',
      corridor_width_m: 50,
      alternative_count: 2,
      weight_slope: 0.35,
      weight_hydric: 0.55,
      weight_property: 0.1,
      weight_landcover: 0.15,
    });

    expect(result.summary.total_distance_m).toBe(1234);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v2/geo/routing/corridor',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          from_lon: -63,
          from_lat: -32,
          to_lon: -63.1,
          to_lat: -32.1,
          mode: 'raster',
          profile: 'hidraulico',
          corridor_width_m: 50,
          alternative_count: 2,
          weight_slope: 0.35,
          weight_hydric: 0.55,
          weight_property: 0.1,
          weight_landcover: 0.15,
        }),
      }),
    );
  });

  it('posts automatic corridor analysis payload', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          analysis_id: 'analysis-1',
          scope: { type: 'consorcio', id: null, zone_count: 12 },
          summary: {
            mode: 'raster',
            profile: 'hidraulico',
            generated_candidates: 8,
            returned_candidates: 5,
            routed_candidates: 4,
            unroutable_candidates: 1,
            avg_score: 71.2,
            max_score: 83.4,
          },
          candidates: [],
          ranking: [],
          stats: {
            critical_zones: 3,
            scope_zone_names: ['Zona 1'],
          },
        }),
    });

    const { routingApi } = await import('../../src/lib/api/routing');
    const result = await routingApi.getAutoAnalysis({
      scope_type: 'cuenca',
      scope_id: 'Cuenca Norte',
      mode: 'raster',
      profile: 'hidraulico',
      max_candidates: 6,
      weight_slope: 0.2,
      weight_hydric: 0.6,
      weight_property: 0.2,
      weight_landcover: 0.1,
      include_unroutable: true,
    });

    expect(result.analysis_id).toBe('analysis-1');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v2/geo/routing/auto-analysis',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          scope_type: 'cuenca',
          scope_id: 'Cuenca Norte',
          mode: 'raster',
          profile: 'hidraulico',
          max_candidates: 6,
          weight_slope: 0.2,
          weight_hydric: 0.6,
          weight_property: 0.2,
          weight_landcover: 0.1,
          include_unroutable: true,
        }),
      }),
    );
  });

  it('polls canal analysis task status', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          task_id: 'task-1',
          status: 'completed',
          total_suggestions: 0,
          batch_id: 'batch-1',
        }),
    });

    const { canalSuggestionsApi } = await import('../../src/lib/api');
    const result = await canalSuggestionsApi.getAnalyzeStatus('task-1');

    expect(result.status).toBe('completed');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v2/geo/intelligence/suggestions/analyze/status/task-1',
      expect.any(Object),
    );
  });

  it('saves and fetches corridor scenarios', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 'scenario-1',
            name: 'Escenario Norte',
            profile: 'balanceado',
            request_payload: {},
            result_payload: {
              source: { id: 1 },
              target: { id: 2 },
              summary: {
                mode: 'network',
                profile: 'balanceado',
                total_distance_m: 1234,
                edges: 4,
                corridor_width_m: 50,
              },
              centerline: { type: 'FeatureCollection', features: [] },
              corridor: null,
              alternatives: [],
            },
            created_at: '2026-04-10T00:00:00Z',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            items: [
              {
                id: 'scenario-1',
                name: 'Escenario Norte',
                profile: 'balanceado',
                created_at: '2026-04-10T00:00:00Z',
              },
            ],
            total: 1,
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 'scenario-1',
            name: 'Escenario Norte',
            profile: 'balanceado',
            request_payload: { from_lon: -63 },
            result_payload: {
              source: { id: 1 },
              target: { id: 2 },
              summary: {
                mode: 'network',
                profile: 'balanceado',
                total_distance_m: 1234,
                edges: 4,
                corridor_width_m: 50,
              },
              centerline: { type: 'FeatureCollection', features: [] },
              corridor: null,
              alternatives: [],
            },
            created_at: '2026-04-10T00:00:00Z',
          }),
      });

    const { routingApi } = await import('../../src/lib/api/routing');
    const saved = await routingApi.saveScenario({
      name: 'Escenario Norte',
      profile: 'balanceado',
      request_payload: { from_lon: -63, from_lat: -32, to_lon: -63.1, to_lat: -32.1 },
      result_payload: {
        source: { id: 1 },
        target: { id: 2 },
        summary: {
          mode: 'network',
          profile: 'balanceado',
          total_distance_m: 1234,
          edges: 4,
          corridor_width_m: 50,
        },
        centerline: { type: 'FeatureCollection', features: [] },
        corridor: null,
        alternatives: [],
      },
    });
    const listed = await routingApi.listScenarios();
    const scenario = await routingApi.getScenario('scenario-1');

    expect(saved.id).toBe('scenario-1');
    expect(listed.total).toBe(1);
    expect(scenario.name).toBe('Escenario Norte');
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/api/v2/geo/routing/corridor/scenarios',
      expect.any(Object),
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      3,
      'http://localhost:8000/api/v2/geo/routing/corridor/scenarios/scenario-1',
      expect.any(Object),
    );
  });

  it('exports a saved scenario as geojson', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          type: 'FeatureCollection',
          features: [],
        }),
    });

    const { routingApi } = await import('../../src/lib/api/routing');
    const result = await routingApi.exportScenarioGeoJson('scenario-1');

    expect(result.type).toBe('FeatureCollection');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v2/geo/routing/corridor/scenarios/scenario-1/geojson',
      expect.any(Object),
    );
  });

  it('approves, favorites and exports a saved scenario as pdf', async () => {
    const blob = new Blob(['pdf']);
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 'scenario-1',
            name: 'Escenario Norte',
            profile: 'balanceado',
            is_approved: true,
            approval_note: 'Validado en comité',
            request_payload: {},
            result_payload: {
              source: { id: 1 },
              target: { id: 2 },
              summary: {
                mode: 'network',
                profile: 'balanceado',
                total_distance_m: 1234,
                edges: 4,
                corridor_width_m: 50,
              },
              centerline: { type: 'FeatureCollection', features: [] },
              corridor: null,
              alternatives: [],
            },
            created_at: '2026-04-10T00:00:00Z',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 'scenario-1',
            name: 'Escenario Norte',
            profile: 'balanceado',
            is_favorite: true,
            request_payload: {},
            result_payload: {
              source: { id: 1 },
              target: { id: 2 },
              summary: {
                mode: 'network',
                profile: 'balanceado',
                total_distance_m: 1234,
                edges: 4,
                corridor_width_m: 50,
              },
              centerline: { type: 'FeatureCollection', features: [] },
              corridor: null,
              alternatives: [],
            },
            created_at: '2026-04-10T00:00:00Z',
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        blob: () => Promise.resolve(blob),
      });

    const { routingApi } = await import('../../src/lib/api/routing');
    const approved = await routingApi.approveScenario('scenario-1', 'Validado en comité');
    const favorite = await routingApi.favoriteScenario('scenario-1', true);
    const pdf = await routingApi.exportScenarioPdf('scenario-1');

    expect(approved.is_approved).toBe(true);
    expect(favorite.is_favorite).toBe(true);
    expect(pdf).toBe(blob);
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      'http://localhost:8000/api/v2/geo/routing/corridor/scenarios/scenario-1/approve',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ note: 'Validado en comité' }),
      }),
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/api/v2/geo/routing/corridor/scenarios/scenario-1/favorite',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ is_favorite: true }),
      }),
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      3,
      'http://localhost:8000/api/v2/geo/routing/corridor/scenarios/scenario-1/pdf',
      expect.any(Object),
    );
  });
});
