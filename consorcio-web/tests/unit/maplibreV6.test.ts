import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import * as maplibregl from 'maplibre-gl';
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
    expect(src).not.toMatch(/module\.default/);
    expect(src).toMatch(/bootMapLibreWorker/);
    expect(src).toMatch(/setWorkerUrl/);
  });

  it('bootMapLibreWorker is idempotent', () => {
    bootMapLibreWorker();
    bootMapLibreWorker();
  });
});
