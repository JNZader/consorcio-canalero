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
  return render(<MantineProvider>{ui}</MantineProvider>);
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
      /haz un clic para marcar un punto/i,
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
});
