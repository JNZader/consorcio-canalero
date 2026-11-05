import { describe, expect, it } from 'vitest';

import { MAP_Z } from '../../src/components/map2d/mapZIndex';
import { readMapCss } from '../helpers/mapCss';

const css = readMapCss();

const CSS_TOKEN: Record<keyof typeof MAP_Z, string> = {
  hazard: '--z-map-hazard',
  hazardMobile: '--z-map-hazard-mobile',
  comparison: '--z-map-comparison',
  overlay: '--z-map-overlay',
  dateBadge: '--z-map-date-badge',
  divider: '--z-map-divider',
  controls: '--z-map-controls',
  measurementLabel: '--z-map-measurement-label',
  profile: '--z-map-profile',
  blocking: '--z-map-blocking',
  pageChrome: '--z-map-page-chrome',
  panel: '--z-map-panel',
  drawerOverlay: '--z-map-drawer-overlay',
  drawer: '--z-map-drawer',
  burger: '--z-map-burger',
  gesture: '--z-map-gesture',
};

describe('map z-index tokens', () => {
  it('mirrors every MAP_Z value as a CSS custom property', () => {
    for (const [key, cssName] of Object.entries(CSS_TOKEN) as [keyof typeof MAP_Z, string][]) {
      expect(css).toContain(`${cssName}: ${MAP_Z[key]};`);
    }
  });

  it('does not leave the old panel layer as a raw z-index: 1000', () => {
    expect(css).not.toMatch(/z-index:\s*1000\b/);
  });
});
