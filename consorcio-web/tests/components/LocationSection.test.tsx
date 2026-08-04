import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocationSection } from '../../src/components/report-form/LocationSection';

const { addReferenceLayersMock, mapInstances, markerInstances, MockMap, MockMarker } = vi.hoisted(
  () => {
  const addReferenceLayersMock = vi.fn();
  const mapInstances: MockMap[] = [];
  const markerInstances: MockMarker[] = [];

  class MockMap {
    readonly handlers = new Map<string, (event?: unknown) => void>();
    readonly remove = vi.fn();
    readonly flyTo = vi.fn();

    constructor() {
      mapInstances.push(this);
    }

    on(event: string, handler: (event?: unknown) => void) {
      this.handlers.set(event, handler);
      if (event === 'load') handler();
      return this;
    }

    isStyleLoaded() {
      return true;
    }

    getZoom() {
      return 12;
    }

    // El componente real lee `map.getBounds().contains(...)` para
    // decidir si hace `flyTo` (sólo cuando el punto está fuera del
    // viewport). Devolvemos un bounds que dice "todo está adentro" —
    // así el mock no dispara `flyTo` y los assertions del test no
    // dependen del estado de la cámara.
    getBounds() {
      return { contains: () => true };
    }

    flyTo() {
      // no-op
    }
  }

  class MockMarker {
    readonly setLngLat = vi.fn(() => this);
    readonly addTo = vi.fn(() => this);
    readonly remove = vi.fn();

    constructor() {
      markerInstances.push(this);
    }
  }

  return { addReferenceLayersMock, mapInstances, markerInstances, MockMap, MockMarker };
  },
);

vi.mock('maplibre-gl', () => ({
  default: {
    Map: MockMap,
    Marker: MockMarker,
  },
}));

vi.mock('../../src/hooks/useFormMapLayers', () => ({
  addReferenceLayers: (...args: unknown[]) => addReferenceLayersMock(...args),
  isInsideZona: () => true,
  useFormMapLayers: () => ({ zonaGeoJson: null, caminosGeoJson: null, waterways: null }),
}));

vi.mock('../../src/components/ui/accessibility', () => ({
  CoordinatesInput: ({
    onCoordinatesChange,
  }: {
    onCoordinatesChange: (lat: number, lng: number) => void;
  }) => (
    <button type="button" onClick={() => onCoordinatesChange(-32.6, -62.7)}>
      set-coordinates
    </button>
  ),
}));

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const baseProps = {
  ubicacion: null,
  mostrarInputManual: false,
  obteniendoUbicacion: false,
  onObtenerGPS: () => {},
  onToggleInputManual: () => {},
  onLocationSelect: () => {},
  onCoordinatesChange: () => {},
  onClearLocation: () => {},
} satisfies React.ComponentProps<typeof LocationSection>;

describe('<LocationSection />', () => {
  it('describes the map and exposes manual coordinates state', async () => {
    const onToggleInputManual = vi.fn();
    const onCoordinatesChange = vi.fn();
    const user = userEvent.setup();

    renderWithMantine(
      <>
        <span id="ubicacion-label">Ubicación del incidente</span>
        <LocationSection
          {...baseProps}
          mostrarInputManual
          onToggleInputManual={onToggleInputManual}
          onCoordinatesChange={onCoordinatesChange}
        />
      </>,
    );

    expect(screen.getByRole('application', { name: /mapa interactivo/i })).toHaveAccessibleDescription(
      /haz clic dentro del área del consorcio/i,
    );

    const manualToggle = screen.getByRole('button', { name: /ocultar entrada manual/i });
    expect(manualToggle).toHaveAttribute('aria-expanded', 'true');
    expect(manualToggle).toHaveAttribute('aria-controls', 'input-coordenadas-manual');
    expect(screen.getByRole('region', { name: /ubicación del incidente/i })).toHaveAttribute(
      'id',
      'input-coordenadas-manual',
    );

    await user.click(screen.getByRole('button', { name: /set-coordinates/i }));
    expect(onCoordinatesChange).toHaveBeenCalledWith(-32.6, -62.7);
  });

  it('announces selected coordinates and labels the clear action', async () => {
    const onClearLocation = vi.fn();
    const user = userEvent.setup();

    renderWithMantine(
      <LocationSection
        {...baseProps}
        ubicacion={{ lat: -32.61234, lng: -62.74567 }}
        onClearLocation={onClearLocation}
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('-32.61234, -62.74567');
    expect(screen.getByRole('application', { name: /mapa interactivo/i })).toHaveAccessibleDescription(
      /-32\.61234, -62\.74567/,
    );

    await user.click(
      screen.getByRole('button', {
        name: /limpiar ubicación seleccionada -32\.61234, -62\.74567/i,
      }),
    );
    expect(onClearLocation).toHaveBeenCalledTimes(1);
  });

  it('marks the GPS button as busy while geolocation is running', () => {
    renderWithMantine(<LocationSection {...baseProps} obteniendoUbicacion />);

    expect(screen.getByRole('button', { name: /usar mi ubicacion gps/i })).toHaveAttribute(
      'aria-busy',
      'true',
    );
  });

  it('does not submit the parent report form from location helper actions', async () => {
    const onSubmit = vi.fn((event: React.FormEvent<HTMLFormElement>) => event.preventDefault());
    const onObtenerGPS = vi.fn();
    const onToggleInputManual = vi.fn();
    const onClearLocation = vi.fn();
    const user = userEvent.setup();

    renderWithMantine(
      <form onSubmit={onSubmit}>
        <LocationSection
          {...baseProps}
          ubicacion={{ lat: -32.61234, lng: -62.74567 }}
          onObtenerGPS={onObtenerGPS}
          onToggleInputManual={onToggleInputManual}
          onClearLocation={onClearLocation}
        />
      </form>,
    );

    await user.click(screen.getByRole('button', { name: /usar mi ubicacion gps/i }));
    await user.click(screen.getByRole('button', { name: /ingresar coordenadas manualmente/i }));
    await user.click(
      screen.getByRole('button', {
        name: /limpiar ubicación seleccionada -32\.61234, -62\.74567/i,
      }),
    );

    expect(onObtenerGPS).toHaveBeenCalledTimes(1);
    expect(onToggleInputManual).toHaveBeenCalledTimes(1);
    expect(onClearLocation).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

/**
 * PERF-005 — `maplibre-gl` is imported dynamically so `/participacion` does
 * not pay for the ~215 KB map engine before the user reaches the location
 * step. These tests pin the observable consequences of that decision.
 */
describe('<LocationSection /> lazy map engine', () => {
  beforeEach(() => {
    mapInstances.length = 0;
    markerInstances.length = 0;
  });

  it('does not construct the map synchronously and builds it once the chunk resolves', async () => {
    renderWithMantine(<LocationSection {...baseProps} />);

    // The dynamic import has not resolved yet on the first commit.
    expect(mapInstances).toHaveLength(0);
    expect(screen.getByRole('application', { name: /mapa interactivo/i })).toHaveAttribute(
      'aria-busy',
      'true',
    );
    expect(screen.getByText(/cargando mapa/i)).toBeInTheDocument();

    await waitFor(() => expect(mapInstances).toHaveLength(1));

    await waitFor(() =>
      expect(screen.getByRole('application', { name: /mapa interactivo/i })).toHaveAttribute(
        'aria-busy',
        'false',
      ),
    );
    expect(screen.queryByText(/cargando mapa/i)).not.toBeInTheDocument();
  });

  it('places the marker after the module is available', async () => {
    renderWithMantine(
      <LocationSection {...baseProps} ubicacion={{ lat: -32.6, lng: -62.7 }} />,
    );

    await waitFor(() => expect(markerInstances).toHaveLength(1));
    expect(markerInstances[0].setLngLat).toHaveBeenCalledWith([-62.7, -32.6]);
    expect(markerInstances[0].addTo).toHaveBeenCalledWith(mapInstances[0]);
  });

  it('keeps the click handler wiring once the engine finished loading', async () => {
    const onLocationSelect = vi.fn();
    renderWithMantine(<LocationSection {...baseProps} onLocationSelect={onLocationSelect} />);

    await waitFor(() => expect(mapInstances).toHaveLength(1));

    mapInstances[0].handlers.get('click')?.({ lngLat: { lng: -62.7, lat: -32.6 } });
    expect(onLocationSelect).toHaveBeenCalledWith(-32.6, -62.7);
  });

  it('never builds a map when the section unmounts before the chunk resolves', async () => {
    const { unmount } = renderWithMantine(<LocationSection {...baseProps} />);
    unmount();

    // Let the in-flight dynamic import settle: the `cancelled` guard must
    // swallow it instead of constructing a map on a detached container.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mapInstances).toHaveLength(0);
    expect(markerInstances).toHaveLength(0);
  });
});
