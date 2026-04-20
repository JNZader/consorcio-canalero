/**
 * SuggestionDetailModalCanalesMigration.test.tsx — Batch 5 (Phase 6 removals)
 *
 * Locks in the canales migration for the admin sugerencias modal:
 *   1. The modal's prop contract no longer mentions `waterways` — it now
 *      accepts a `canales` array of `{id, data, style}` objects, fed from
 *      `useCanales().relevados` by `SugerenciasPanel`.
 *   2. When given a non-empty `canales` array and a sugerencia with geometry,
 *      the modal mounts the reference backdrop without crashing.
 *   3. When given an empty `canales` array (ETL asset missing), the modal
 *      still mounts gracefully (no-op reference layer).
 *
 * The goal of these tests is contract-only: MapLibre itself is mocked via
 * `SugerenciaGeometryMap` being treated as a black box — we only assert the
 * modal renders the geometry section and receives the `canales` prop through
 * the new pathway.
 */

import { render, screen } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';

import { SuggestionDetailModal } from '../../src/components/admin/sugerencias/components/SuggestionDetailModal';

// ── Stub SugerenciaGeometryMap so the test does NOT boot MapLibre ───────────
// We capture the props it receives so assertions can pin the prop bridge.
const geometryMapSpy = vi.fn();
vi.mock('../../src/components/admin/sugerencias/components/SugerenciaGeometryMap', () => ({
  SugerenciaGeometryMap: (props: Record<string, unknown>) => {
    geometryMapSpy(props);
    return <div data-testid="sugerencia-geom-map" />;
  },
}));

// ── Helpers ──────────────────────────────────────────────────────────────────
function makeSelectedSugerencia(): any {
  return {
    id: 'test-sug-1',
    titulo: 'Canal sugerido',
    descripcion: 'Línea propuesta al Consorcio',
    categoria: 'hidrica',
    tipo: 'ciudadana',
    created_at: '2026-04-20T00:00:00Z',
    estado: 'pendiente',
    geometry: {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
          properties: {},
        },
      ],
    },
  };
}

function makeCanales(): Array<{
  id: string;
  data: import('geojson').FeatureCollection;
  style: { color?: string; weight?: number; opacity?: number };
}> {
  return [
    {
      id: 'canales_relevados',
      data: {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: [[0, 0], [1, 0]] },
            properties: { id: 'n4-readec', estado: 'relevado' },
          },
        ],
      },
      style: { color: '#1D4ED8', weight: 3, opacity: 0.9 },
    },
  ];
}

function renderModal(overrides: Partial<Parameters<typeof SuggestionDetailModal>[0]> = {}) {
  geometryMapSpy.mockClear();
  const baseProps: Parameters<typeof SuggestionDetailModal>[0] = {
    opened: true,
    onClose: vi.fn(),
    selectedSugerencia: makeSelectedSugerencia(),
    canales: makeCanales(),
    historial: [],
    loadingHistorial: false,
    showHistorial: false,
    setShowHistorial: vi.fn(),
    newEstado: 'pendiente',
    setNewEstado: vi.fn(),
    publicComment: '',
    setPublicComment: vi.fn(),
    adminNotes: '',
    setAdminNotes: vi.fn(),
    agendarFecha: null,
    setAgendarFecha: vi.fn(),
    onAgendar: vi.fn(),
    agendando: false,
    onIncorporateChannel: vi.fn(),
    incorporating: false,
    onDelete: vi.fn(),
    deleting: false,
    onUpdate: vi.fn(),
    updating: false,
    ...overrides,
  };
  return render(
    <MantineProvider>
      <SuggestionDetailModal {...baseProps} />
    </MantineProvider>,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
describe('SuggestionDetailModal — canales migration (Batch 5)', () => {
  it('renders the geometry section and forwards canales to the map backdrop', () => {
    const canales = makeCanales();
    renderModal({ canales });

    // Modal body rendered + geometry sub-map mounted
    expect(screen.getByText(/Geometría sugerida/i)).toBeInTheDocument();
    expect(screen.getByTestId('sugerencia-geom-map')).toBeInTheDocument();

    // The canales prop reaches SugerenciaGeometryMap via the new pathway
    expect(geometryMapSpy).toHaveBeenCalled();
    const lastArgs = geometryMapSpy.mock.calls.at(-1)?.[0] as
      | { canales?: unknown[] }
      | undefined;
    expect(Array.isArray(lastArgs?.canales)).toBe(true);
    expect((lastArgs?.canales as unknown[]).length).toBe(1);
  });

  it('mounts gracefully with an empty canales array (Pilar Azul asset missing)', () => {
    renderModal({ canales: [] });

    expect(screen.getByText(/Geometría sugerida/i)).toBeInTheDocument();
    expect(screen.getByTestId('sugerencia-geom-map')).toBeInTheDocument();

    const lastArgs = geometryMapSpy.mock.calls.at(-1)?.[0] as
      | { canales?: unknown[] }
      | undefined;
    expect(Array.isArray(lastArgs?.canales)).toBe(true);
    expect(lastArgs?.canales).toHaveLength(0);
  });
});
