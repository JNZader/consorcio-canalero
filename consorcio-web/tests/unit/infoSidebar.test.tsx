import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { Feature } from 'geojson';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { featureKindLabel, InfoPanel } from '../../src/components/map2d/InfoPanel';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

describe('featureKindLabel', () => {
  it('prefers the road class over the layer id', () => {
    expect(featureKindLabel('map2d-roads-hit', { gna: 'Camino Provincial' })).toBe(
      'Camino Provincial'
    );
  });

  it('names IDECOR layers, canals, parcels and a fallback', () => {
    expect(featureKindLabel('idecor_cursos-line', { nombre: 'Río' })).toBe('Curso de agua');
    expect(featureKindLabel('idecor_canales_riego-line', {})).toBe('Canal de riego');
    expect(featureKindLabel('idecor_consorcios-fill', {})).toBe('Consorcio');
    expect(featureKindLabel('idecor_cuencas-fill', {})).toBe('Cuenca');
    expect(featureKindLabel('canales_relevados-line', { estado: 'relevado' })).toBe('Canal');
    expect(featureKindLabel('map2d-catastro-fill', { tipo_parcela: 'Rural' })).toBe('Rural');
    expect(featureKindLabel('escuelas-symbol', {})).toBe('Escuela');
    expect(featureKindLabel(undefined, {})).toBe('Elemento');
  });
});

describe('<InfoPanel embedded>', () => {
  it('shows the feature name and kind inside the sidebar, without a floating close', () => {
    const feature = {
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
      properties: {
        nombre: 'Camino Provincial T269-03',
        gna: 'Camino Provincial',
        fna: 'C. C. 269 - SAN MARCOS SUD',
      },
      layer: { id: 'map2d-roads-hit' },
    } as Feature & { layer: { id: string } };

    renderWithMantine(<InfoPanel embedded features={[feature]} onClose={() => {}} />);

    expect(screen.getByTestId('info-panel-heading')).toHaveTextContent('Camino Provincial T269-03');
    expect(screen.getByTestId('info-panel-kind')).toHaveTextContent('Camino Provincial');
    expect(screen.getByRole('region', { name: 'Información del elemento' })).toBeInTheDocument();
    expect(screen.queryByTestId('map-2d-info-panel-close')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Perfil de elevación' })).toBeInTheDocument();
  });
});
