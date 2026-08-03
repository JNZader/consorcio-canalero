/**
 * mapSkeletonGeometry.test.ts — T3c fix 5a.
 *
 * The lazy-load skeleton used `.mapWrapper` (16/9 aspect, max 700px) while the
 * mounted canvas uses `--map-canvas-height`, so the page visibly jumped the
 * moment MapLibre finished loading. The skeleton now shares the canvas height
 * budget at BOTH breakpoints.
 *
 * This is a stylesheet contract, asserted against the CSS source: jsdom does not
 * evaluate CSS modules or media queries, so a render-based check would pass for
 * any class name at all.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const cssPath = join(process.cwd(), 'src/styles/components/map.module.css');
const css = readFileSync(cssPath, 'utf8');
const componentPath = join(process.cwd(), 'src/components/MapaInteractivo.tsx');
const component = readFileSync(componentPath, 'utf8');

/** All `--map-canvas-height` declaration blocks, desktop first then media queries. */
function budgetSelectorBlocks(): string[] {
  return [...css.matchAll(/([^{}]+)\{[^{}]*--map-canvas-height:[^{}]*\}/g)].map((m) => m[1]);
}

describe('map skeleton geometry (T3c fix 5a)', () => {
  it('the skeleton no longer uses the 16/9 .mapWrapper box', () => {
    const skeleton = component.slice(
      component.indexOf('function MapaLoadingSkeleton'),
      component.indexOf('function MapaErrorFallback')
    );
    expect(skeleton).toContain('styles.mapSkeletonWrapper');
    expect(skeleton).not.toContain('styles.mapWrapper');
    // The error fallback keeps `.mapWrapper` on purpose: it is a terminal
    // message card, not a placeholder that gets replaced by the canvas, so it
    // cannot cause a load-time layout shift.
    expect(component).toContain('styles.mapWrapper');
  });

  it('declares .mapSkeletonWrapper with the shared canvas height var', () => {
    const block = css.match(/\.mapSkeletonWrapper\s*\{([^}]*)\}/);
    expect(block).not.toBeNull();
    expect(block?.[1]).toContain('height: var(--map-canvas-height)');
  });

  it('shares the height budget with .mapCanvasWrapper at EVERY breakpoint', () => {
    const blocks = budgetSelectorBlocks();
    // Desktop + the 62em media query.
    expect(blocks.length).toBeGreaterThanOrEqual(2);
    for (const selectors of blocks) {
      expect(selectors).toContain('.mapCanvasWrapper');
      expect(selectors).toContain('.mapSkeletonWrapper');
    }
  });
});
