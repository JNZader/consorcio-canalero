/**
 * mapDockSheetClearance.test.ts — portrait rework.
 *
 * The measurement toolbar and the bottom sheet share the canvas' bottom edge.
 * The sheet (z-index 1000) used to simply cover the toolbar, and that was
 * documented as accepted. It is not: at `peek` (25%) and `medio` (45%) the sheet
 * is a PARTIAL cover on purpose — most of the map stays live so the user can
 * keep working it — and the toolbar is the tool for that work. The dock now
 * rides above the sheet at those two stages, by geometry (`:has()` + a bottom
 * offset), never by z-index.
 *
 * `alto` (85%) stays a plain cover: no map left to operate, and lifting the dock
 * to 85% would push it into the page header.
 *
 * Asserted against the CSS source and the component source: jsdom evaluates
 * neither CSS modules nor media queries, so a render-based check would pass for
 * any rule at all.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(join(process.cwd(), 'src/styles/components/map.module.css'), 'utf8');
const shell = readFileSync(
  join(process.cwd(), 'src/components/map2d/MapPanelShell.tsx'),
  'utf8'
);

/** The narrow-touch block is the only place the sheet and the dock coexist. */
function coarseNarrowBlock(): string {
  const match = css.match(
    /@media \(pointer: coarse\) and \(max-width: 62em\)\s*\{([\s\S]*?)\n\}/
  );
  expect(match, 'el bloque coarse + 62em tiene que existir').not.toBeNull();
  return match?.[1] ?? '';
}

describe('measurement dock vs bottom sheet (portrait rework)', () => {
  it('lifts the dock clear of a PEEK sheet (25%)', () => {
    const body = coarseNarrowBlock();
    const rule = body.match(
      /\.mapCanvasWrapper:has\(\.panelSheet\[data-stage='peek'\]\)\s+\.measurementDock\s*\{([^}]*)\}/
    );
    expect(rule, 'falta la regla de despeje para peek').not.toBeNull();
    expect(rule?.[1]).toContain('bottom: calc(25% + 12px');
    // Se conserva el inset de area segura del sheet, o los dos se desalinean.
    expect(rule?.[1]).toContain('env(safe-area-inset-bottom, 0px)');
  });

  it('lifts the dock clear of a MEDIO sheet (45%)', () => {
    const body = coarseNarrowBlock();
    const rule = body.match(
      /\.mapCanvasWrapper:has\(\.panelSheet\[data-stage='medio'\]\)\s+\.measurementDock\s*\{([^}]*)\}/
    );
    expect(rule, 'falta la regla de despeje para medio').not.toBeNull();
    expect(rule?.[1]).toContain('bottom: calc(45% + 12px');
    expect(rule?.[1]).toContain('env(safe-area-inset-bottom, 0px)');
  });

  it('does NOT lift the dock for the ALTO sheet (85%)', () => {
    // Decidido: a 85% no queda mapa que operar, y 85% + 12px meteria el dock
    // dentro de la cabecera de la pagina.
    expect(css).not.toContain("data-stage='alto'");
  });

  it('keys on data-stage, NOT on the modifier class', () => {
    // `medio` es la forma BASE de `.panelSheet` y no tiene clase modificadora
    // (MapPanelShell: solo `peek` y `alto` agregan una), asi que un selector por
    // clase no podria distinguirlo. El atributo esta en las tres etapas.
    expect(css).not.toContain('panelSheetMedio');
    expect(shell).toContain('data-stage={stage}');
  });

  it('MapPanelShell still emits data-stage (public CSS contract)', () => {
    expect(shell).toContain('data-stage={stage}');
    // Las tres etapas que el CSS distingue.
    for (const stage of ['peek', 'medio', 'alto']) {
      expect(shell).toContain(stage);
    }
  });
});
