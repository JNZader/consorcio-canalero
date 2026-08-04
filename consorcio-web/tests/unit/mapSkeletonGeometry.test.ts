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

import { MAP_DESKTOP_MEDIA_QUERY } from '../../src/components/map2d/MapWorkspace';

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
    // Desktop + the 62em media query + the landscape-phone query (B2-2.1) +
    // the portrait-phone query (portrait rework).
    expect(blocks.length).toBeGreaterThanOrEqual(4);
    for (const selectors of blocks) {
      expect(selectors).toContain('.mapCanvasWrapper');
      expect(selectors).toContain('.canvasHeightBudget');
      expect(selectors).toContain('.mapSkeletonWrapper');
      expect(selectors).toContain('.workspaceSidebar');
    }
  });

  /**
   * B2-2.1 — landscape phones. A block that redefines the budget for FEWER than
   * the four consumers silently desyncs 2D from 3D (or the skeleton from the
   * canvas) at that breakpoint only; the loop above is what catches it.
   */
  it('gives landscape phones their own budget and a reachable floor', () => {
    const query = css.match(
      /@media \(pointer: coarse\) and \(orientation: landscape\) and \(max-height: 30em\)\s*\{([\s\S]*?)\n\}/
    );
    expect(query).not.toBeNull();
    const body = query?.[1] ?? '';

    expect(body).toContain('--map-canvas-height: calc(100dvh - 84px)');
    // El piso de 420/380px no entra en un viewport acostado.
    expect(body).toContain('min-height: 260px');
    // El titulo baja debajo del mapa; nada se oculta.
    expect(body).toContain('order: 2');
    expect(body).not.toContain('display: none');
  });

  /**
   * Portrait rework — the same reflow landscape got in B2-2.1, for the case the
   * first honest e2e run measured: at 360x800 the canvas started at y~442 and
   * ran 142px past the fold.
   */
  it('gives portrait phones their own budget and drops the header below the map', () => {
    const query = css.match(
      /@media \(pointer: coarse\) and \(orientation: portrait\) and \(max-width: 47\.9375em\)\s*\{([\s\S]*?)\n\}/
    );
    expect(query).not.toBeNull();
    const body = query?.[1] ?? '';

    // 61 header + 12 container-py + 12 Paper mb + 11 slack.
    expect(body).toContain('--map-canvas-height: calc(100dvh - 96px)');
    // El titulo, el banner satelital y Reportar bajan DEBAJO del mapa.
    expect(body).toContain('order: 2');
    // Nada se oculta: el reflow es `order`, no `display: none`.
    expect(body).not.toContain('display: none');
  });

  /**
   * GUARD — the portrait breakpoint must NOT collide with `isDesktop`.
   *
   * `MapWorkspace` enters desktop mode at `MAP_DESKTOP_MEDIA_QUERY`'s min-width.
   * A portrait query written with the SAME value would also match at exactly
   * that width, so a viewport that still renders the floating top bar would get
   * the top-bar-less height budget (96px of chrome instead of ~158px) and the
   * canvas would overflow again — at one single width, i.e. the kind of bug
   * nobody reproduces.
   *
   * READ-002 — the expected value is DERIVED from the TS constant, never
   * hardcoded. The stylesheet cannot import it, so this is the only place the
   * two sides are tied together: bump the constant without bumping the CSS and
   * this fails with the mismatch spelled out, instead of staying green while the
   * 1px overlap silently reopens. The complement is one CSS pixel below the
   * min-width, expressed in em (0.0625em = 1px at the 16px root).
   */
  it('derives the portrait breakpoint from MAP_DESKTOP_MEDIA_QUERY', () => {
    const minWidth = MAP_DESKTOP_MEDIA_QUERY.match(/min-width:\s*([\d.]+)em/);
    expect(minWidth, `la constante tiene que declarar un min-width en em, es «${MAP_DESKTOP_MEDIA_QUERY}»`).not.toBeNull();

    const desktopFloorEm = Number.parseFloat(minWidth?.[1] ?? '');
    expect(Number.isFinite(desktopFloorEm)).toBe(true);
    // 1px at the 16px root. Exactly representable in binary, so no rounding.
    const expectedPortraitCeiling = `${desktopFloorEm - 0.0625}em`;

    const prelude = css.match(
      /@media \(pointer: coarse\) and \(orientation: portrait\) and \(max-width: ([^)]+)\)/
    );
    expect(prelude, 'falta el bloque portrait en map.module.css').not.toBeNull();
    expect(
      prelude?.[1],
      `el max-width de portrait tiene que ser el complemento exacto de ${desktopFloorEm}em (el min-width de MAP_DESKTOP_MEDIA_QUERY); si moviste la constante, movi tambien map.module.css`
    ).toBe(expectedPortraitCeiling);

    // Y el complemento NO puede ser el propio piso de escritorio: ahi las dos
    // queries darian verdadero al mismo tiempo.
    expect(prelude?.[1]).not.toBe(`${desktopFloorEm}em`);
    // 62em would swallow portrait tablets, which ARE desktop mode.
    expect(prelude?.[1]).not.toBe('62em');
  });
});
