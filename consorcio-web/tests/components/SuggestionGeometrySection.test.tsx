import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { DrawnLineFeatureCollection } from '../../src/components/map/LineDrawControl';
import { SuggestionGeometrySection } from '../../src/components/suggestion-form/SuggestionGeometrySection';
import formStyles from '../../src/styles/components/form.module.css';

const { addReferenceLayersMock, mapInstances, mapOptions, MockMap } = vi.hoisted(() => {
  const addReferenceLayersMock = vi.fn();
  const mapOptions: Array<Record<string, unknown>> = [];
  const mapInstances: MockMap[] = [];

  class MockMap {
    readonly handlers = new Map<string, (event?: unknown) => void>();
    readonly remove = vi.fn();
    readonly flyTo = vi.fn();

    constructor(options?: Record<string, unknown>) {
      mapOptions.push(options ?? {});
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
  }

  return { addReferenceLayersMock, mapInstances, mapOptions, MockMap };
});

vi.mock('maplibre-gl', () => ({
  Map: MockMap,
  setWorkerUrl: () => {},
  default: {
    Map: MockMap,
  },
}));

vi.mock('../../src/hooks/useFormMapLayers', () => ({
  addReferenceLayers: (...args: unknown[]) => addReferenceLayersMock(...args),
  useFormMapLayers: () => ({ zonaGeoJson: null, caminosGeoJson: null, waterways: null }),
}));

vi.mock('../../src/components/map/SuggestionGeometryControl', () => ({
  default: () => <button type="button">geometry-control</button>,
}));

function renderWithMantine(ui: React.ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

const featureGeometry = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: {},
      geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
    },
    {
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.7, -32.6],
          [-62.8, -32.7],
        ],
      },
    },
  ],
} satisfies DrawnLineFeatureCollection;

describe('<SuggestionGeometrySection />', () => {
  beforeEach(() => {
    mapOptions.length = 0;
    mapInstances.length = 0;
  });

  it('labels the suggestion map and connects instructions, summary and reference text', () => {
    renderWithMantine(<SuggestionGeometrySection geometry={null} onChange={() => {}} />);

    expect(screen.getByRole('application', { name: /canal en mapa/i })).toHaveAccessibleDescription(
      /hacé un clic para marcar un punto/i,
    );
    expect(screen.getByRole('application', { name: /canal en mapa/i })).toHaveAccessibleDescription(
      /opcional: marcá un punto/i,
    );
    expect(screen.getByRole('application', { name: /canal en mapa/i })).toHaveAccessibleDescription(
      /con un dedo se desplaza la página/i,
    );
    expect(screen.getByRole('application', { name: /canal en mapa/i })).toHaveAccessibleDescription(
      /referencia: límite del consorcio/i,
    );
    expect(screen.getByRole('status')).toHaveTextContent(/opcional: marcá un punto/i);
  });

  it('announces the drawn geometry summary', () => {
    renderWithMantine(<SuggestionGeometrySection geometry={featureGeometry} onChange={() => {}} />);

    expect(screen.getByRole('status')).toHaveTextContent('1 punto · 1 línea');
    expect(screen.getByRole('application', { name: /canal en mapa/i })).toHaveAccessibleDescription(
      /1 punto · 1 línea/i,
    );
  });

  it('exposes touch-friendly GPS, undo, and clear actions (CIT-01, CIT-02)', () => {
    const onChange = vi.fn();
    renderWithMantine(
      <SuggestionGeometrySection geometry={featureGeometry} onChange={onChange} />,
    );

    const gps = screen.getByRole('button', { name: /mi ubicación \(gps\)/i });
    expect(gps).toBeEnabled();
    expect(gps).toHaveClass('touch-target-min');
    const undoBtn = screen.getByRole('button', { name: /deshacer último punto/i });
    const clearBtn = screen.getByRole('button', { name: /limpiar dibujo/i });
    expect(undoBtn).toHaveClass('touch-target-min');
    expect(clearBtn).toHaveClass('touch-target-min');

    expect(undoBtn).toBeEnabled();
    expect(clearBtn).toBeEnabled();

    undoBtn.click();
    expect(onChange).toHaveBeenCalledWith({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
        },
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'Point', coordinates: [-62.7, -32.6] },
        },
      ],
    });

    clearBtn.click();
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('collapses behind an optional toggle when category is administrative (CIT-03)', () => {
    renderWithMantine(
      <SuggestionGeometrySection
        geometry={null}
        onChange={() => {}}
        categoria="administrativo"
      />,
    );

    const toggle = screen.getByRole('button', { name: /agregar ubicación en el mapa \(opcional\)/i });
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveClass('touch-target-min');
    expect(screen.queryByRole('application', { name: /canal en mapa/i })).not.toBeInTheDocument();
  });

  it('keeps one-finger scroll on the page and shrinks the map like the report form', async () => {
    renderWithMantine(<SuggestionGeometrySection geometry={null} onChange={() => {}} />);

    const map = screen.getByRole('application', { name: /canal en mapa/i });
    expect(map).toHaveClass(formStyles.mapContainer);
    expect(map).toHaveClass(formStyles.mapContainerLarge);

    await waitFor(() => expect(mapOptions).toHaveLength(1));
    expect(mapOptions[0]?.cooperativeGestures).toBe(true);
    expect(mapOptions[0]?.attributionControl).toEqual({ compact: true });
    expect(mapOptions[0]?.locale).toMatchObject({
      'CooperativeGesturesHandler.MobileHelpText': 'Usá dos dedos para mover el mapa',
    });
  });

  it('destroys the map once on unmount', async () => {
    const { unmount } = renderWithMantine(
      <SuggestionGeometrySection geometry={null} onChange={() => {}} />,
    );
    await waitFor(() => expect(mapInstances).toHaveLength(1));
    unmount();
    expect(mapInstances[0]?.remove).toHaveBeenCalledTimes(1);
  });
});
