import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode, RefObject } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MapBaseSelectorPanel } from '../../src/components/map2d/MapBaseSelectorPanel';
import { MapVistaSection } from '../../src/components/map2d/MapVistaSection';
import { MapWorkspace } from '../../src/components/map2d/MapWorkspace';
import {
  MapPageViewProvider,
  type MapPageViewValue,
} from '../../src/components/map2d/mapPageViewContext';
import { MeasurementToolbar } from '../../src/components/map2d/measurement/MeasurementToolbar';
import { useMapWorkspaceStore } from '../../src/stores/mapWorkspaceStore';

function wrap(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function pageView(overrides: Partial<MapPageViewValue> = {}): MapPageViewValue {
  return {
    mode: '2d',
    setMode: vi.fn(),
    terrainReady: true,
    terrainHint: null,
    terrainStatus: 'ready',
    ...overrides,
  };
}

beforeEach(() => {
  useMapWorkspaceStore.setState({ showCursorReadout: false, sidebarCollapsed: false });
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

describe('MapVistaSection', () => {
  it('omits the 2D/3D control and the base row outside the page provider', () => {
    wrap(<MapVistaSection showCursorToggle={false} />);
    expect(screen.getByText('Vista')).toBeInTheDocument();
    expect(screen.queryByLabelText('Vista del mapa')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Seleccionar capa base')).not.toBeInTheDocument();
    expect(screen.queryByTestId('map-cursor-toggle')).not.toBeInTheDocument();
  });

  it('switches mode, shows the terrain hint, and retries a failed DEM', async () => {
    const user = userEvent.setup();
    const setMode = vi.fn();
    const onRetryTerrain = vi.fn();
    wrap(
      <MapPageViewProvider
        value={pageView({
          setMode,
          mode: '3d',
          terrainReady: false,
          terrainHint: 'No pudimos cargar el relieve.',
          terrainStatus: 'error',
          onRetryTerrain,
        })}
      >
        <MapVistaSection />
      </MapPageViewProvider>
    );

    expect(screen.getByTestId('map-3d-status')).toHaveTextContent('No pudimos cargar el relieve.');
    expect(screen.getByRole('radio', { name: '3D' })).toBeDisabled();
    await user.click(screen.getByRole('radio', { name: '2D' }));
    expect(setMode).toHaveBeenCalledWith('2d');
    await user.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(onRetryTerrain).toHaveBeenCalledOnce();
  });

  it('changes the base layer and the cursor readout from the section', async () => {
    const user = userEvent.setup();
    const onBaseLayerChange = vi.fn();
    wrap(
      <MapPageViewProvider value={pageView()}>
        <MapVistaSection
          baseLayer="osm"
          onBaseLayerChange={onBaseLayerChange}
          viewModePanel={<span>Vista satelital</span>}
        />
      </MapPageViewProvider>
    );

    await user.click(screen.getByRole('radio', { name: '3D' }));
    await user.click(screen.getByRole('radio', { name: 'Satélite' }));
    expect(onBaseLayerChange).toHaveBeenCalledWith('satellite');
    expect(screen.getByText('Vista satelital')).toBeInTheDocument();

    await user.click(screen.getByTestId('map-cursor-toggle'));
    expect(useMapWorkspaceStore.getState().showCursorReadout).toBe(true);
  });
});

describe('MapBaseSelectorPanel', () => {
  it('keeps the floating paper when it is not embedded in the panel', async () => {
    const user = userEvent.setup();
    const onBaseLayerChange = vi.fn();
    wrap(
      <MapBaseSelectorPanel baseLayer="satellite" onBaseLayerChange={onBaseLayerChange} />
    );
    await user.click(screen.getByRole('radio', { name: 'OSM' }));
    expect(onBaseLayerChange).toHaveBeenCalledWith('osm');
  });
});

describe('MapWorkspace header search', () => {
  it('pins the search in the header and hides it when the sidebar collapses', async () => {
    const user = userEvent.setup();
    wrap(
      <MapWorkspace
        canvas={<div>lienzo</div>}
        controls={<div>capas</div>}
        headerSlot={<input aria-label="Buscar canal o cuenta" />}
      />
    );
    expect(screen.getByLabelText('Buscar canal o cuenta')).toBeInTheDocument();
    await user.click(screen.getByTestId('map-workspace-collapse'));
    expect(screen.queryByLabelText('Buscar canal o cuenta')).not.toBeInTheDocument();
  });
});

describe('Herramientas extra branches', () => {
  it('portals the measuring bar onto the canvas', () => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const portalTarget = { current: host } as RefObject<HTMLElement | null>;
    wrap(
      <MeasurementToolbar
        mode="measuring-distance"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
        portalTarget={portalTarget}
      />
    );
    expect(host.querySelector('[data-testid="measurement-action-bar"]')).not.toBeNull();
    host.remove();
  });

  it('falls back to onClear when Cancelar has no dedicated handler', async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    wrap(
      <MeasurementToolbar
        mode="measuring-area"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={onClear}
      />
    );
    await user.click(screen.getByRole('button', { name: 'Cancelar medición' }));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it('offers the point tool, redraw, delete and export from the menu', async () => {
    const user = userEvent.setup();
    const onTogglePoiPlace = vi.fn();
    const onRedrawPolygon = vi.fn();
    const onDeletePolygon = vi.fn();
    const onOpenExportPng = vi.fn();
    const onExportApprovedZonesPdf = vi.fn();
    const onExportKmz = vi.fn();
    const onExportMenuOpen = vi.fn();
    wrap(
      <MeasurementToolbar
        mode="ficha-dibujo"
        hasMeasurements={false}
        onStartDistance={() => {}}
        onStartArea={() => {}}
        onClear={() => {}}
        fichaDrawActive
        onToggleFichaDraw={() => {}}
        onRedrawPolygon={onRedrawPolygon}
        onDeletePolygon={onDeletePolygon}
        poiPlaceActive
        onTogglePoiPlace={onTogglePoiPlace}
        hasApprovedZones
        onOpenExportPng={onOpenExportPng}
        onExportApprovedZonesPdf={onExportApprovedZonesPdf}
        onExportKmz={onExportKmz}
        onExportMenuOpen={onExportMenuOpen}
      />
    );

    await user.click(screen.getByTestId('ficha-draw-new-polygon'));
    await user.click(screen.getByTestId('ficha-draw-delete-polygon'));
    await user.click(screen.getByRole('button', { name: 'Marcar punto de interés' }));
    expect(onRedrawPolygon).toHaveBeenCalledOnce();
    expect(onDeletePolygon).toHaveBeenCalledOnce();
    expect(onTogglePoiPlace).toHaveBeenCalledOnce();

    await user.click(screen.getByRole('button', { name: 'Herramientas' }));
    expect(onExportMenuOpen).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('menuitem', { name: 'Marcar punto de interés' }));
    expect(onTogglePoiPlace).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole('button', { name: 'Herramientas' }));
    await user.click(screen.getByText('Exportar PNG'));
    await user.click(screen.getByRole('button', { name: 'Herramientas' }));
    await user.click(screen.getByText('Exportar PDF'));
    await user.click(screen.getByRole('button', { name: 'Herramientas' }));
    await user.click(screen.getByText('Exportar KMZ'));
    await user.click(screen.getByRole('button', { name: 'Herramientas' }));
    await user.click(screen.getByTestId('map-share-qr'));
    expect(onOpenExportPng).toHaveBeenCalledOnce();
    expect(onExportApprovedZonesPdf).toHaveBeenCalledOnce();
    expect(onExportKmz).toHaveBeenCalledOnce();
    expect(screen.getByText('Link para el campo')).toBeInTheDocument();
  });
});
