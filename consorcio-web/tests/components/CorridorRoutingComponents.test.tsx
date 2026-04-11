import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AutoCorridorAnalysisCard } from '../../src/components/admin/canal-suggestions/components/AutoCorridorAnalysisCard';
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

const autoAnalysisPayload = {
  analysis_id: 'analysis-1',
  scope: {
    type: 'consorcio' as const,
    id: null,
    zone_count: 12,
  },
  summary: {
    mode: 'raster' as const,
    profile: 'hidraulico' as const,
    generated_candidates: 8,
    returned_candidates: 3,
    routed_candidates: 2,
    unroutable_candidates: 1,
    avg_score: 72.5,
    max_score: 86.4,
  },
  candidates: [
    {
      candidate_id: 'z1::z2',
      candidate_type: 'zone_link',
      source_zone_id: 'z1',
      source_zone_name: 'Zona Norte',
      target_zone_id: 'z2',
      target_zone_name: 'Zona Este',
      from_lon: -63,
      from_lat: -32,
      to_lon: -63.1,
      to_lat: -32.1,
      zone_pair_distance_deg: 0.11,
      priority_score: 85,
      reason: 'Conectar zonas críticas',
      status: 'routed' as const,
      score: 86.4,
      rank: 1,
      ranking_breakdown: {
        status: 'routed' as const,
        priority_score: 85,
        distance_score: 60,
        profile_score: 92,
        hydric_score: 74,
        route_distance_m: 1800,
        avg_profile_factor: 1.08,
        avg_hydric_index: 74,
        parcel_intersections: 1,
        near_parcels: 2,
        explanation: 'Conecta dos zonas de alta criticidad con costo controlado.',
      },
      routing_result: resultPayload,
    },
  ],
  ranking: ['z1::z2'],
  stats: {
    critical_zones: 4,
    scope_zone_names: ['Zona Norte'],
  },
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
          weightSlope: 0.45,
          weightHydric: 0.25,
          weightProperty: 0.3,
          weightLandcover: 0.2,
        }}
        loading={false}
        error={null}
        result={resultPayload}
        pickTarget={null}
        scenarioName="Escenario Norte"
        scenarioNotes="Notas"
        currentScenarioId={null}
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
          weightSlope: 0.45,
          weightHydric: 0.25,
          weightProperty: 0.3,
          weightLandcover: 0.2,
        }}
        loading={false}
        error={null}
        result={null}
        pickTarget={null}
        scenarioName=""
        scenarioNotes=""
        currentScenarioId={null}
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
    const onUnapprove = vi.fn();
    const onFavorite = vi.fn();

    renderWithMantine(
      <CorridorScenarioHistory
        loading={false}
        items={[
          {
            id: 'scenario-1',
            name: 'Escenario Norte',
            profile: 'hidraulico',
            notes: 'Cruce principal',
            approval_note: 'Ajustar trazado al oeste',
            is_approved: true,
            is_favorite: true,
            version: 3,
            created_at: '2026-04-10T00:00:00Z',
          },
        ]}
        onLoad={onLoad}
        onExport={onExport}
        onExportPdf={onExportPdf}
        onApprove={onApprove}
        onUnapprove={onUnapprove}
        onFavorite={onFavorite}
      />,
    );

    expect(screen.getByText('Escenario Norte')).toBeInTheDocument();
    expect(screen.getByText(/Cruce principal/i)).toBeInTheDocument();
    expect(screen.getByText(/Última nota de aprobación/i)).toBeInTheDocument();
    expect(screen.getByText('Favorito')).toBeInTheDocument();
    expect(screen.getByText('v3')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cargar escenario/i }));
    await user.click(screen.getByRole('button', { name: /volver a borrador/i }));
    await user.click(screen.getByRole('button', { name: /quitar favorito/i }));
    await user.click(screen.getByRole('button', { name: /exportar geojson/i }));
    await user.click(screen.getByRole('button', { name: /exportar pdf/i }));

    expect(onLoad).toHaveBeenCalledWith('scenario-1');
    expect(onApprove).not.toHaveBeenCalled();
    expect(onUnapprove).toHaveBeenCalledWith('scenario-1');
    expect(onFavorite).toHaveBeenCalledWith('scenario-1', false);
    expect(onExport).toHaveBeenCalledWith('scenario-1');
    expect(onExportPdf).toHaveBeenCalledWith('scenario-1');
  });

  it('renders automatic analysis ranking and opens a routed candidate', async () => {
    const user = userEvent.setup();
    const onOpenCandidate = vi.fn();

    renderWithMantine(
      <AutoCorridorAnalysisCard
        form={{
          scopeType: 'consorcio',
          scopeId: '',
          scopeParentCuenca: '',
          pointLon: '',
          pointLat: '',
          mode: 'raster',
          profile: 'hidraulico',
          maxCandidates: 5,
          weightSlope: 0.2,
          weightHydric: 0.6,
          weightProperty: 0.2,
          weightLandcover: 0.15,
          includeUnroutable: true,
        }}
        cuencaOptions={[{ value: 'Norte', label: 'Norte' }]}
        subcuencaOptions={[{ value: 'sub-1', label: 'Subcuenca 1' }]}
        loading={false}
        error={null}
        result={autoAnalysisPayload}
        selectedCandidateId={null}
        onChange={vi.fn()}
        onScopeChange={vi.fn()}
        onModeChange={vi.fn()}
        onProfileChange={vi.fn()}
        onSubmit={vi.fn()}
        onOpenCandidate={onOpenCandidate}
        pointPickActive={false}
        onStartPointPick={vi.fn()}
        onCancelPointPick={vi.fn()}
      />,
    );

    expect(screen.getByText(/Análisis automático de cuenca/i)).toBeInTheDocument();
    expect(screen.getByText('Ruteable')).toBeInTheDocument();
    expect(screen.getByText(/Zona Norte → Zona Este/i)).toBeInTheDocument();
    expect(screen.getByText('86.4')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /abrir en mapa/i }));

    expect(onOpenCandidate).toHaveBeenCalledWith(autoAnalysisPayload.candidates[0]);
  });
});
