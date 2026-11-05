import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ElevationProfileDock } from '../../src/components/map2d/ElevationProfileDock';
import { HazardControlsMobile } from '../../src/components/map2d/HazardControlsMobile';
import {
  HAZARD_RISK_CLASSES,
  PRECIPITATION_PERIOD,
  type HazardControlsProps,
} from '../../src/components/map2d/hazardControls.types';
import { MapPanelShell } from '../../src/components/map2d/MapPanelShell';

vi.mock('../../src/components/map2d/ElevationProfileChart', () => ({
  ElevationProfileChart: () => <div data-testid="elevation-profile-chart-stub" />,
}));

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

function mockNarrow(narrow: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('max-width') ? narrow : !narrow,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function Sheet({
  label,
  onClose = () => {},
  withField = false,
}: {
  label: string;
  onClose?: () => void;
  withField?: boolean;
}) {
  return (
    <MapPanelShell
      sheet
      floatingClassName=""
      testId={label}
      sheetLabel={label}
      closeLabel={`Cerrar ${label}`}
      onClose={onClose}
    >
      <button type="button">Adentro {label}</button>
      {withField ? <input aria-label={`Nota ${label}`} /> : null}
    </MapPanelShell>
  );
}

const line = {
  type: 'LineString' as const,
  coordinates: [
    [-62.7, -32.6],
    [-62.6, -32.5],
  ],
};

describe('sheets móviles del mapa', () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it('la sheet abierta es diálogo modal, Escape cierra y el foco vuelve al disparador', () => {
    const opener = document.createElement('button');
    opener.type = 'button';
    opener.textContent = 'Abrir ficha';
    document.body.appendChild(opener);
    opener.focus();
    const onClose = vi.fn();
    const view = renderWithMantine(<Sheet label="ficha territorial" onClose={onClose} />);

    const dialog = screen.getByRole('dialog', { name: 'ficha territorial' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog.contains(document.activeElement)).toBe(true);

    const outside = document.createElement('button');
    outside.type = 'button';
    outside.textContent = 'fuera';
    document.body.appendChild(outside);
    outside.focus();
    expect(dialog.contains(document.activeElement)).toBe(true);

    const last = screen.getByRole('button', { name: 'Adentro ficha territorial' });
    last.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByRole('button', { name: 'Ampliar ficha territorial' })).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(last).toHaveFocus();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    view.unmount();
    expect(opener).toHaveFocus();
  });

  it('no cierra con Escape en un campo de texto ni le roba el foco a otro diálogo', () => {
    const onClose = vi.fn();
    renderWithMantine(<Sheet label="relevamiento del tramo" onClose={onClose} withField />);
    const dialog = screen.getByRole('dialog', { name: 'relevamiento del tramo' });
    const field = screen.getByRole('textbox', { name: 'Nota relevamiento del tramo' });
    field.focus();
    fireEvent.keyDown(field, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();

    const host = document.createElement('div');
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-label', 'confirmación');
    const inner = document.createElement('button');
    inner.type = 'button';
    inner.textContent = 'Confirmar';
    host.appendChild(inner);
    document.body.appendChild(host);
    inner.focus();
    expect(inner).toHaveFocus();
    expect(dialog.contains(document.activeElement)).toBe(false);
    fireEvent.keyDown(inner, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('la tarjeta de escritorio no es modal', () => {
    renderWithMantine(
      <MapPanelShell sheet={false} floatingClassName="infoPanel" testId="info" sheetLabel="panel">
        <button type="button">Adentro</button>
      </MapPanelShell>
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('solo la sheet de adelante atrapa; la de mayor prioridad gana', async () => {
    mockNarrow(true);
    const onCloseFicha = vi.fn();
    const onCloseDock = vi.fn();
    renderWithMantine(
      <>
        <Sheet label="ficha territorial" onClose={onCloseFicha} />
        <Sheet label="relevamiento del tramo" onClose={() => {}} />
        <ElevationProfileDock geometry={line} title="Perfil de elevación" onClose={onCloseDock} />
      </>
    );

    await screen.findByTestId('elevation-profile-chart-stub');
    const dialogs = screen.getAllByRole('dialog');
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0]).toHaveAttribute('aria-label', 'relevamiento del tramo');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCloseFicha).not.toHaveBeenCalled();
    expect(onCloseDock).not.toHaveBeenCalled();
  });

  it('el drawer de capas abierto deja la sheet del lienzo sin modal', async () => {
    const { rerender } = renderWithMantine(
      <div data-testid="map-workspace-root" data-drawer-open="true">
        <Sheet label="ficha territorial" />
      </div>
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    rerender(
      <MantineProvider env="test">
        <div data-testid="map-workspace-root" data-drawer-open="false">
          <Sheet label="ficha territorial" />
        </div>
      </MantineProvider>
    );
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'ficha territorial' })).toHaveAttribute(
        'aria-modal',
        'true'
      );
    });
  });

  it('el perfil en el teléfono es diálogo; en escritorio no', async () => {
    mockNarrow(true);
    const onClose = vi.fn();
    const narrow = renderWithMantine(
      <ElevationProfileDock geometry={line} title="Perfil de elevación" onClose={onClose} />
    );
    const dialog = screen.getByRole('dialog', { name: 'Perfil de elevación' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('data-sheet', 'true');
    const handle = screen.getByTestId('elevation-profile-resize');
    expect(handle.style.height).toBe('var(--cc-touch-min, 44px)');
    expect(await screen.findByTestId('elevation-profile-chart-stub')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
    narrow.unmount();

    mockNarrow(false);
    renderWithMantine(
      <ElevationProfileDock geometry={line} title="Perfil de elevación" onClose={onClose} />
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('elevation-profile-dock')).toHaveAttribute('data-sheet', 'false');
  });

  it('riesgos móvil: Escape contrae y el foco vuelve al chip', () => {
    const props: HazardControlsProps = {
      basins: [],
      selectedBasinId: null,
      onBasinChange: vi.fn(),
      visibleRiskClasses: HAZARD_RISK_CLASSES,
      onRiskClassChange: vi.fn(),
      precipitationPeriod: PRECIPITATION_PERIOD.ANNUAL,
      onPrecipitationPeriodChange: vi.fn(),
      onReset: vi.fn(),
      collapsed: true,
      onCollapsedChange: vi.fn(),
    };
    const view = renderWithMantine(<HazardControlsMobile {...props} />);
    const chip = screen.getByTestId('hazard-controls-mobile-chip');
    chip.focus();

    view.rerender(
      <MantineProvider env="test">
        <HazardControlsMobile {...props} collapsed={false} />
      </MantineProvider>
    );
    const dialog = screen.getByRole('dialog', { name: 'Controles de riesgos móviles' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog.contains(document.activeElement)).toBe(true);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(props.onCollapsedChange).toHaveBeenCalledWith(true);

    view.rerender(
      <MantineProvider env="test">
        <HazardControlsMobile {...props} collapsed />
      </MantineProvider>
    );
    expect(screen.getByTestId('hazard-controls-mobile-chip')).toHaveFocus();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
