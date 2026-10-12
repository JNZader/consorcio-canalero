import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const MAPA_PAGE = readFileSync(resolve(process.cwd(), 'src/components/MapaPage.tsx'), 'utf-8');
const TERRAIN = readFileSync(
  resolve(process.cwd(), 'src/components/terrain/TerrainViewer3D.tsx'),
  'utf-8',
);

describe('I18N-03 microcopy (vos, no tú / no jargon)', () => {
  it('asks the operator to run the DEM pipeline in Rioplatense', () => {
    expect(MAPA_PAGE).toContain('terrainAvailabilityHint');
    expect(MAPA_PAGE).not.toContain('ejecuta el pipeline primero');
    expect(TERRAIN).toContain('Ejecutá el pipeline de terreno');
    expect(TERRAIN).not.toContain('Ejecuta el pipeline DEM primero');
  });
});
