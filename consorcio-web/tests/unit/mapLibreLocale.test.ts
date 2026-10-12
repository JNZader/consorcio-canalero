import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { MAP_LOCALE_ES } from '../../src/components/map2d/mapLibreLocale';

const DEFAULT_LOCALE = readFileSync(
  resolve(process.cwd(), 'node_modules/maplibre-gl/src/ui/default_locale.ts'),
  'utf-8'
);

describe('MAP_LOCALE_ES (I18N-01)', () => {
  it('covers every MapLibre defaultLocale key', () => {
    const keys = [...DEFAULT_LOCALE.matchAll(/'([^']+)':/g)].map((match) => match[1]);
    expect(keys.length).toBeGreaterThan(10);
    for (const key of keys) {
      expect(MAP_LOCALE_ES).toHaveProperty(key);
    }
  });

  it('does not leave navigation chrome in English', () => {
    expect(MAP_LOCALE_ES['NavigationControl.ZoomIn']).toBe('Acercar');
    expect(MAP_LOCALE_ES['NavigationControl.ZoomOut']).toBe('Alejar');
    expect(MAP_LOCALE_ES['FullscreenControl.Enter']).toBe('Pantalla completa');
    expect(MAP_LOCALE_ES['Map.Title']).toBe('Mapa');
  });
});
