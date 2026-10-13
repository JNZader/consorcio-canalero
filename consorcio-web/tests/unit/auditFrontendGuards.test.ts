import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { isConfiguredSupportPhone } from '../../src/constants';
import { loadReportDraft, saveReportDraft } from '../../src/lib/formDrafts';
import { parseLoginSearch } from '../../src/lib/loginSearch';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, '../..');

describe('login search', () => {
  it('keeps only the register mode', () => {
    expect(parseLoginSearch({ modo: 'registro', extra: '1' })).toEqual({ modo: 'registro' });
    expect(parseLoginSearch({ modo: 'login' })).toEqual({});
  });
});

describe('support phone', () => {
  it('rejects the published placeholder and empty values', () => {
    expect(isConfiguredSupportPhone('')).toBe(false);
    expect(isConfiguredSupportPhone('+543534000000')).toBe(false);
    expect(isConfiguredSupportPhone('+54 353 400-0000')).toBe(false);
    expect(isConfiguredSupportPhone('+543534111222')).toBe(true);
  });
});

describe('report draft', () => {
  it('round-trips text and coordinates without a photo', () => {
    saveReportDraft({ tipo: 'desborde', descripcion: 'Agua en el camino', lat: -32.1, lng: -62.2 });
    expect(loadReportDraft()).toEqual({
      tipo: 'desborde',
      descripcion: 'Agua en el camino',
      lat: -32.1,
      lng: -62.2,
    });
  });
});

describe('public SEO and offline basemap', () => {
  it('ships the sitemap advertised by robots.txt', () => {
    const robots = readFileSync(join(webRoot, 'public/robots.txt'), 'utf8');
    const match = robots.match(/^Sitemap:\s*(\S+)/m);
    expect(match?.[1]).toBe('https://consorcio-canalero.pages.dev/sitemap.xml');
    const sitemap = readFileSync(join(webRoot, 'public/sitemap.xml'), 'utf8');
    expect(sitemap).toContain('https://consorcio-canalero.pages.dev/mapa');
    expect(sitemap).toContain('https://consorcio-canalero.pages.dev/participacion');
    expect(sitemap).not.toContain('/admin');
    expect(sitemap).not.toContain('/login');
  });

  it('caches opaque Esri tiles and leaves map chunks out of precache', () => {
    const vite = readFileSync(join(webRoot, 'vite.config.ts'), 'utf8');
    const arcgis = vite.slice(vite.indexOf('arcgis-tiles'), vite.indexOf('arcgis-tiles') + 500);
    expect(arcgis).toContain('statuses: [0, 200]');
    expect(vite).toContain('**/vendor-maplibre-*.js');
    expect(vite).toContain('**/MapaMapLibre-*.js');
    expect(vite).toContain('**/TerrainViewer3D-*.js');
  });
});
