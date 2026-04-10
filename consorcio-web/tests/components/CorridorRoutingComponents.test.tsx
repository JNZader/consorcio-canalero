import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CorridorRoutingCard } from '../../src/components/admin/canal-suggestions/components/CorridorRoutingCard';
import { CorridorScenarioHistory } from '../../src/components/admin/canal-suggestions/components/CorridorScenarioHistory';

const resultPayload = {
  source: { id: 1 },
  target: { id: 2 },
  summary: {
    mode: 'raster' as const,
    profile: 'balanceado' as const,
    total_distance_m: 1530,
    edges: 6,
    corridor_width_m: 75,
    penalty_factor: 3,
    cost_breakdown: {
      profile: 'balanceado' as const,
      edge_count_with_profile_factor: 2,
      avg_profile_factor: 1.15,
      max_profile_factor: 1.3,
      min_profile_factor: 1,
      parcel_intersections: 1,
      near_parcels: 2,
      avg_hydric_index: 63.5,
      hydraulic_edge_count: 2,
      profile_edge_count: 2,
    },
  },
  centerline: { type: 'FeatureCollection' as const, features: [] },
  corridor: null,
  alternatives: [
    {
      rank: 1,
      total_distance_m: 1700,
      edges: 7,
      edge_ids: [1, 2],
      geojson: { type: 'FeatureCollection' as const, features: [] },
    },
  ],
};

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe('Corridor routing components', () => {
  it('renders corridor summary breakdown and alternatives', () => {
    renderWithMantine(
      <CorridorRoutingCard
        form={{
          mode: 'raster',
          profile: 'balanceado',
          fromLon: -63,
          fromLat: -32,
          toLon: -63.1,
          toLat: -32.1,
          corridorWidthM: 75,
          alternativeCount: 2,
        }}
        loading={false}
        error={null}
        result={resultPayload}
        pickTarget={null}
        scenarioName="Escenario Norte"
        scenarioNotes="Notas"
        onChange={vi.fn()}
        onModeChange={vi.fn()}
        onProfileChange={vi.fn()}
        onSubmit={vi.fn()}
        onStartPick={vi.fn()}
        onCancelPick={vi.fn()}
        onScenarioNameChange={vi.fn()}
        onScenarioNotesChange={vi.fn()}
        onSaveScenario={vi.fn()}
      />,
    );

    expect(screen.getAllByText('Balanceado').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Raster multi-criterio').length).toBeGreaterThan(0);
    expect(screen.getByText('1.53 km')).toBeInTheDocument();
    expect(screen.getByText('63.5')).toBeInTheDocument();
    expect(screen.getByText('Alternativa #1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /guardar escenario/i })).toBeInTheDocument();
  });

  it('calls profile change when selecting another routing profile', async () => {
    const user = userEvent.setup();
    const onProfileChange = vi.fn();

    renderWithMantine(
      <CorridorRoutingCard
        form={{
          mode: 'network',
          profile: 'balanceado',
          fromLon: '',
          fromLat: '',
          toLon: '',
          toLat: '',
          corridorWidthM: 50,
          alternativeCount: 2,
        }}
        loading={false}
        error={null}
        result={null}
        pickTarget={null}
        scenarioName=""
        scenarioNotes=""
        onChange={vi.fn()}
        onModeChange={vi.fn()}
        onProfileChange={onProfileChange}
        onSubmit={vi.fn()}
        onStartPick={vi.fn()}
        onCancelPick={vi.fn()}
        onScenarioNameChange={vi.fn()}
        onScenarioNotesChange={vi.fn()}
        onSaveScenario={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('textbox', { name: /perfil de routing/i }));
    await user.click(screen.getByRole('option', { name: /Hidráulico/i, hidden: true }));

    expect(onProfileChange).toHaveBeenCalledWith('hidraulico');
  });

  it('renders saved scenario history and triggers load/export actions', async () => {
    const user = userEvent.setup();
    const onLoad = vi.fn();
    const onExport = vi.fn();
    const onExportPdf = vi.fn();
    const onApprove = vi.fn();

    renderWithMantine(
      <CorridorScenarioHistory
        loading={false}
        items={[
          {
            id: 'scenario-1',
            name: 'Escenario Norte',
            profile: 'hidraulico',
            notes: 'Cruce principal',
            is_approved: false,
            created_at: '2026-04-10T00:00:00Z',
          },
        ]}
        onLoad={onLoad}
        onExport={onExport}
        onExportPdf={onExportPdf}
        onApprove={onApprove}
      />,
    );

    expect(screen.getByText('Escenario Norte')).toBeInTheDocument();
    expect(screen.getByText(/Cruce principal/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cargar escenario/i }));
    await user.click(screen.getByRole('button', { name: /marcar aprobado/i }));
    await user.click(screen.getByRole('button', { name: /exportar geojson/i }));
    await user.click(screen.getByRole('button', { name: /exportar pdf/i }));

    expect(onLoad).toHaveBeenCalledWith('scenario-1');
    expect(onApprove).toHaveBeenCalledWith('scenario-1');
    expect(onExport).toHaveBeenCalledWith('scenario-1');
    expect(onExportPdf).toHaveBeenCalledWith('scenario-1');
  });
});
