import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as maplibregl from 'maplibre-gl';
import { describe, expect, it } from 'vitest';
import { bootMapLibreWorker, loadMapLibre } from '../../src/lib/maplibreLoader';

const here = dirname(fileURLToPath(import.meta.url));

describe('MapLibre GL JS v6', () => {
  it('exports Map and setWorkerUrl on the namespace, not as default', () => {
    expect(typeof maplibregl.Map).toBe('function');
    expect(typeof maplibregl.setWorkerUrl).toBe('function');
    expect(typeof maplibregl.GPUInitializationError).toBe('function');
    expect(maplibregl).not.toHaveProperty('default');
  });

  it('loadMapLibre returns the namespace (no default export)', async () => {
    const mod = await loadMapLibre();
    expect(typeof mod.Map).toBe('function');
    expect(mod).not.toHaveProperty('default');
  });

  it('does not read module.default in maplibreLoader', () => {
    const src = readFileSync(join(here, '../../src/lib/maplibreLoader.ts'), 'utf8');
    expect(src).toMatch(/asModule\(\(module as \{ default\?: unknown \}\)\.default\)/);
    expect(src).toMatch(/bootMapLibreWorker/);
    expect(src).toMatch(/setWorkerUrl/);
  });

  it('bootMapLibreWorker is idempotent', () => {
    bootMapLibreWorker();
    bootMapLibreWorker();
  });

  it('every remaining Map boot awaits the worker (or the shared lifecycle)', () => {
    const direct = [
      'components/admin/CanalesPublicacionMap.tsx',
      'components/admin/sugerencias/components/SugerenciaGeometryMap.tsx',
      'components/admin/images/useImageExplorerMap.tsx',
    ];
    const shared = [
      'components/terrain/TerrainViewer3D.tsx',
      'components/map2d/useMapInitialization.ts',
      'components/report-form/LocationSection.tsx',
      'components/suggestion-form/SuggestionGeometrySection.tsx',
    ];
    const fireAndForget = /bootMapLibreWorker\(\);\s*\n\s*(?:const|let) map = new /;
    const directNew = /new maplibregl\.Map\(|new maplibre\.Map\(/;
    for (const rel of direct) {
      const src = readFileSync(join(here, '../../src', rel), 'utf8');
      expect(src, rel).not.toMatch(fireAndForget);
      expect(src, rel).toMatch(/await bootMapLibreWorker\(/);
    }
    for (const rel of shared) {
      const src = readFileSync(join(here, '../../src', rel), 'utf8');
      expect(src, rel).not.toMatch(directNew);
      expect(src, rel).toMatch(
        /await (?:loadMapLibre|createMapLibreMap|createTerrainMapLibreMap)\(/
      );
    }
    const lifecycle = readFileSync(join(here, '../../src/lib/maplibreLifecycle.ts'), 'utf8');
    expect(lifecycle).toMatch(/await bootMapLibreWorker\(/);
    expect(lifecycle).not.toMatch(/setWorkerUrl\s*\(/);
    expect(lifecycle.match(/new maplibre\.Map\(/g)).toHaveLength(1);
    const terrainAdapter = readFileSync(
      join(here, '../../src/components/terrain/terrainMapLifecycle.ts'),
      'utf8'
    );
    expect(terrainAdapter).toMatch(/createMapLibreMap\(/);
    expect(terrainAdapter).not.toMatch(directNew);
  });
});
