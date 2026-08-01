/**
 * InfoPanelPurity.test.tsx
 *
 * Spec "Ficha data is fetched by a container, never by InfoPanel" (A4.8):
 * `InfoPanel` must render with NO data provider (no QueryClientProvider) and
 * must issue NO network request. The ficha fetch lives in the container, so
 * InfoPanel stays a pure UI atom.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { Feature } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import { InfoPanel } from '../../src/components/map2d/InfoPanel';

describe('InfoPanel purity', () => {
  it('renders without a data provider and issues no request', () => {
    const fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
    const feature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
      properties: { nombre: 'Algo', localidad: 'Monte Leña' },
    };

    // No QueryClientProvider on purpose — InfoPanel must not call any data hook.
    render(
      <MantineProvider env="test">
        <InfoPanel features={[feature]} onClose={() => {}} />
      </MantineProvider>
    );

    expect(screen.getByText('Informacion')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
