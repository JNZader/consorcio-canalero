/**
 * LayerControlsPanelHealth.test.tsx — Batch 1 "datos honestos".
 *
 * The panel must tell the truth about what did NOT load:
 *   - an aggregate banner above the search box, counting FAILED families;
 *   - one inline row per failed family, with its own "Reintentar";
 *   - and, critically, ZERO change when the new prop is absent (back-compat with
 *     every existing caller and test).
 */

import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LayerControlsPanel } from '../../src/components/map2d/LayerControlsPanel';
import { buildLayerHealth } from '../../src/components/map2d/layerHealth';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const layerItems = [
  { id: 'basins', label: 'Subcuencas', category: 'hidrografia' as const },
  {
    id: 'soil',
    label: 'Suelos IDECOR 1:50.000',
    category: 'territorio' as const,
  },
];

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    layerItems,
    vectorVisibility: {},
    onLayerVisibilityChange: () => {},
    showIGNOverlay: false,
    onShowIGNOverlayChange: () => {},
    demEnabled: false,
    showDemOverlay: false,
    onShowDemOverlayChange: () => {},
    activeDemLayerId: null,
    onActiveDemLayerIdChange: () => {},
    demOptions: [],
    ...overrides,
  };
}

describe('<LayerControlsPanel /> — health banner', () => {
  it('renders NOTHING when the layerHealth prop is absent (back-compat)', () => {
    renderWithMantine(<LayerControlsPanel {...baseProps()} />);

    expect(screen.queryByTestId('layer-health-banner')).toBeNull();
    expect(screen.queryByTestId('layer-health-retry-all')).toBeNull();
  });

  it('renders no banner while every family is healthy', () => {
    const layerHealth = buildLayerHealth({
      basins: { error: null },
      waterways: { loading: true },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    expect(screen.queryByTestId('layer-health-banner')).toBeNull();
  });

  it('uses the SINGULAR copy for exactly one failed family', () => {
    const layerHealth = buildLayerHealth({ basins: { error: 'boom' } });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    expect(screen.getByTestId('layer-health-banner').textContent).toMatch(/1 capa no cargó/);
  });

  it('uses the PLURAL copy for several failed families', () => {
    const layerHealth = buildLayerHealth({
      basins: { error: 'boom' },
      soil: { error: 'boom' },
      canales: { error: 'boom' },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    expect(screen.getByTestId('layer-health-banner').textContent).toMatch(/3 capas no cargaron/);
  });

  it('reports a degraded raster source as FAILING, not as a layer that did not load', () => {
    const layerHealth = buildLayerHealth({
      raster_tiles: { degradedSourceIds: ['dem-tiles'] },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    const banner = screen.getByTestId('layer-health-banner');
    expect(banner.textContent).toMatch(/mosaicos de 1 capa están fallando/);
    expect(banner.textContent).not.toMatch(/no cargó/);
    // Raster tiles have no accordion home — banner only.
    expect(screen.queryByTestId('layer-health-error-territorio')).toBeNull();
  });

  it('offers NO retry button when the only failure cannot be retried', () => {
    // Tiles retry themselves on the next pan/zoom: `reload` is null, so a button
    // here would call nothing at all.
    const layerHealth = buildLayerHealth({
      raster_tiles: { degradedSourceIds: ['dem-tiles'] },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    expect(screen.getByTestId('layer-health-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('layer-health-retry-all')).toBeNull();
  });

  it('keeps the retry button when at least one failure IS retryable', () => {
    const layerHealth = buildLayerHealth({
      basins: { error: 'boom', reload: () => {} },
      raster_tiles: { degradedSourceIds: ['dem-tiles'] },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    expect(screen.getByTestId('layer-health-retry-all')).toBeInTheDocument();
  });

  it('"Reintentar" reloads every failed family and nothing else', () => {
    const reloadBasins = vi.fn();
    const reloadSoil = vi.fn();
    const reloadWaterways = vi.fn();
    const layerHealth = buildLayerHealth({
      basins: { error: 'boom', reload: reloadBasins },
      soil: { error: 'boom', reload: reloadSoil },
      waterways: { error: null, reload: reloadWaterways },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);
    fireEvent.click(screen.getByTestId('layer-health-retry-all'));

    expect(reloadBasins).toHaveBeenCalledTimes(1);
    expect(reloadSoil).toHaveBeenCalledTimes(1);
    expect(reloadWaterways).not.toHaveBeenCalled();
  });
});

describe('<LayerControlsPanel /> — inline family rows', () => {
  it('renders the failing family message inside its accordion panel', () => {
    const layerHealth = buildLayerHealth({
      // Raw slot string on purpose: the panel must render the CURATED copy from
      // the registry, never this.
      basins: { error: 'Error fetching basins: 500' },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    const row = screen.getByTestId('layer-health-error-hidrografia');
    expect(row.textContent).toBe('No se pudieron cargar las subcuencas');
  });

  it('shows the CURATED Spanish copy, never the raw technical error', () => {
    const layerHealth = buildLayerHealth({
      soil: { error: 'Error fetching soil map: 404 (/data/suelos_cu.geojson)' },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    const row = screen.getByTestId('layer-health-error-territorio');
    expect(row.textContent).toBe('No se pudo cargar la capa de suelos');
    expect(row.textContent).not.toMatch(/404|geojson|fetching/i);
  });

  it('renders the BASE (DEM) row, whose accordion branch is separate', () => {
    const layerHealth = buildLayerHealth({ geo_layers: { error: 'boom' } });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    expect(screen.getByTestId('layer-health-error-base').textContent).toBe(
      'No se pudieron cargar las capas DEM'
    );
  });

  it('still shows the Canales row when the whole index failed (no entries to list)', () => {
    // `showCanalesSection` is data-driven: with index.json down there are zero
    // toggle entries, and the accordion item used to vanish entirely.
    const layerHealth = buildLayerHealth({ canales: { error: 'boom' } });

    renderWithMantine(
      <LayerControlsPanel
        {...baseProps({
          layerHealth,
          canalesRelevadosItems: [],
          canalesPropuestosItems: [],
        })}
      />
    );

    expect(screen.getByTestId('layer-health-error-canales').textContent).toBe(
      'No se pudieron cargar los canales'
    );
  });

  it('offers a per-family retry wired to that family only', () => {
    const reloadBasins = vi.fn();
    const reloadSoil = vi.fn();
    const layerHealth = buildLayerHealth({
      basins: { error: 'cuencas caídas', reload: reloadBasins },
      soil: { error: 'suelos caídos', reload: reloadSoil },
    });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    const hidroRow = screen.getByTestId('layer-health-error-hidrografia');
    const retry = hidroRow.parentElement?.querySelector('button');
    expect(retry).toBeTruthy();
    fireEvent.click(retry as HTMLButtonElement);

    expect(reloadBasins).toHaveBeenCalledTimes(1);
    expect(reloadSoil).not.toHaveBeenCalled();
  });

  it('renders no inline row for a healthy family', () => {
    const layerHealth = buildLayerHealth({ basins: { error: null } });

    renderWithMantine(<LayerControlsPanel {...baseProps({ layerHealth })} />);

    expect(screen.queryByTestId('layer-health-error-hidrografia')).toBeNull();
  });

  it('keeps the historical Pilar Verde testid + copy when the legacy prop is used', () => {
    renderWithMantine(
      <LayerControlsPanel
        {...baseProps({
          layerItems: [
            {
              id: 'pilar_verde_agro_zonas',
              label: 'Zonas Agroforestales',
              category: 'pilar_verde' as const,
            },
          ],
          pilarVerdeLayersError: 'Pilar Verde: no se pudieron cargar agroZonas',
        })}
      />
    );

    const row = screen.getByTestId('pilar-verde-layers-error');
    expect(row.textContent).toMatch(/reintentá/i);
    expect(screen.queryByTestId('layer-health-error-pilar_verde')).toBeNull();
  });
});
