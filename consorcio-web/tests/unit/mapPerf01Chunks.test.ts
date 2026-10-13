/**
 * PERF-01 first-paint guards: /mapa must not statically pull recharts or
 * MapboxDraw, and must not dns-prefetch the retired OSM tile host.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));

describe('PERF-01 first-paint chunks', () => {
  it('does not statically import ElevationProfileChart from InfoPanel', () => {
    const info = readFileSync(join(here, '../../src/components/map2d/InfoPanel.tsx'), 'utf8');
    expect(info).not.toMatch(/import \{ ElevationProfileChart \}/);
    expect(info).toMatch(/lazy\(async/);
  });

  it('does not statically import MapboxDraw in measurementDrawModes', () => {
    const modes = readFileSync(
      join(here, '../../src/components/map2d/measurement/measurementDrawModes.ts'),
      'utf8'
    );
    expect(modes).not.toMatch(/import MapboxDraw from '@mapbox\/mapbox-gl-draw'/);
    expect(modes).toMatch(/import\('@mapbox\/mapbox-gl-draw'\)/);
  });

  it('does not statically import DrawControl from MapaMapLibre', () => {
    const mapa = readFileSync(join(here, '../../src/components/MapaMapLibre.tsx'), 'utf8');
    const view = readFileSync(join(here, '../../src/components/map2d/MapaMapLibreView.tsx'), 'utf8');
    expect(mapa).not.toMatch(/import DrawControl,/);
    expect(mapa).not.toMatch(/lazy\(\(\) => import\('\.\/map\/DrawControl'\)\)/);
    expect(view).toMatch("lazy(() => import('../map/DrawControl'))");
  });

  it('dns-prefetches Esri streets, not CARTO or tile.openstreetmap.org', () => {
    const html = readFileSync(join(here, '../../index.html'), 'utf8');
    expect(html).not.toMatch('tile.openstreetmap.org');
    expect(html).not.toMatch('basemaps.cartocdn.com');
    expect(html).toMatch('server.arcgisonline.com');
  });
});
