import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DrawnLineFeatureCollection } from '../../src/components/map/LineDrawControl';
import { SuggestionGeometrySection } from '../../src/components/suggestion-form/SuggestionGeometrySection';

const { addReferenceLayersMock, MockMap } = vi.hoisted(() => {
  const addReferenceLayersMock = vi.fn();

  class MockMap {
    readonly handlers = new Map<string, (event?: unknown) => void>();
    readonly remove = vi.fn();

    on(event: string, handler: (event?: unknown) => void) {
      this.handlers.set(event, handler);
      if (event === 'load') handler();
      return this;
    }

    isStyleLoaded() {
      return true;
    }
  }

  return { addReferenceLayersMock, MockMap };
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
  it('labels the suggestion map and connects instructions, summary and reference text', () => {
    renderWithMantine(<SuggestionGeometrySection geometry={null} onChange={() => {}} />);

    expect(screen.getByRole('application', { name: /canal en mapa/i })).toHaveAccessibleDescription(
      /hacé un clic para marcar un punto/i,
    );
    expect(screen.getByRole('application', { name: /canal en mapa/i })).toHaveAccessibleDescription(
      /opcional: marcá un punto/i,
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

    expect(screen.getByRole('button', { name: /mi ubicación \(gps\)/i })).toBeEnabled();
    const undoBtn = screen.getByRole('button', { name: /deshacer último punto/i });
    const clearBtn = screen.getByRole('button', { name: /limpiar dibujo/i });

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

    expect(
      screen.getByRole('button', { name: /agregar ubicación en el mapa \(opcional\)/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('application', { name: /canal en mapa/i })).not.toBeInTheDocument();
  });
});
