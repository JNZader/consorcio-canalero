import { describe, expect, it } from 'vitest';

import { buildPrecipNormalCatalogEndpoint } from '../../src/hooks/useGeoLayers';

describe('precipitation catalog role selection', () => {
  it('keeps an authenticated ciudadano on the public endpoint', () => {
    expect(buildPrecipNormalCatalogEndpoint('citizen-token', 'ciudadano')).toContain(
      '/layers/public?limit=100&tipo=precip_normal&fuente=gee'
    );
  });

  it.each(['operador', 'admin'])('keeps %s on the authenticated catalog endpoint', (role) => {
    expect(buildPrecipNormalCatalogEndpoint('operator-token', role)).toContain(
      '/layers?limit=100&tipo=precip_normal&fuente=gee'
    );
  });
});
