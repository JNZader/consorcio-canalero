/**
 * mapPanelFadeClearance.test.ts — the sticky fade of the map panels.
 *
 * `.infoPanel` / `.fichaPanel` (desktop cards) and `.panelSheetBody` (mobile
 * bottom sheet) end in a sticky `::after` gradient, the affordance for "there is
 * more below". It shipped with `margin-top: -24px` on the pseudo-element plus a
 * compensating `padding-bottom` on the scroller, on the premise that the padding
 * would give the gradient somewhere empty to land. It does not: a sticky box is
 * clamped to its CONTAINING BLOCK — the scroller's CONTENT box, not its padding
 * box — so the padding raises the resting place by exactly what it adds
 * underneath. The gradient sat on the last line of every ficha tab and that read
 * as a row "cut in half" (measured: ~17.6px of overlap, the full line, in
 * Chromium and Firefox, in both shapes).
 *
 * The cure is that the pseudo-element is a REAL 24px spacer at the end of the
 * flow and the scrollers declare no bottom padding of their own.
 *
 * Asserted against the CSS source, same as `mapDockSheetClearance.test.ts` and
 * `mapSkeletonGeometry.test.ts`: happy-dom evaluates no CSS module and lays out
 * nothing, so a render-based check here would pass for any rule at all. The
 * geometry itself is measured in a real engine by
 * `tests/accessibility/mapPanelFade.spec.ts`.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(join(process.cwd(), 'src/styles/components/map.module.css'), 'utf8');

/** Body of a rule, by its exact selector list. */
function ruleBody(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s*');
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  expect(match, `falta la regla \`${selector}\``).not.toBeNull();
  return match?.[1] ?? '';
}

/** The two fades: the desktop card body shares one block, the sheet has its own. */
const FADES = [
  ['tarjetas de escritorio', '.panelCardBody::after'],
  ['bottom sheet', '.panelSheetBody::after'],
] as const;

describe('degradado sticky de los paneles del mapa', () => {
  for (const [name, selector] of FADES) {
    describe(name, () => {
      it('es un espaciador REAL: 24px sticky, sin margen negativo', () => {
        const body = ruleBody(selector);
        expect(body).toContain('position: sticky');
        expect(body).toContain('bottom: 0');
        expect(body).toContain('height: 24px');
        // El bug: `margin-top: -24px` le daba altura cero en el flujo, asi que el
        // degradado se apoyaba sobre los ultimos 24px de CONTENIDO.
        expect(body, 'un margen negativo vuelve a poner el degradado sobre el texto').not.toMatch(
          /margin-top\s*:\s*-/
        );
      });

      it('no usa un `bottom` negativo como sucedaneo', () => {
        // Tampoco sirve: el sticky se recorta contra su bloque contenedor, asi
        // que un `bottom` negativo se clampea de vuelta sobre el ultimo renglon.
        expect(ruleBody(selector)).not.toMatch(/bottom\s*:\s*-/);
      });
    });
  }

  it('las tarjetas de escritorio no declaran padding inferior compensatorio', () => {
    // `!important` sigue siendo obligatorio: `MapPanelShell` monta las tarjetas
    // como `<Paper p="md">` y Mantine 8 emite esa style prop como `padding`
    // INLINE, que ninguna hoja de estilos pisa sin `!important`.
    const body = ruleBody('.infoPanel, .fichaPanel');
    expect(body).toMatch(/padding-bottom\s*:\s*0\s*!important/);
  });

  it('el cuerpo del sheet no declara padding inferior propio', () => {
    // El despeje lo da el espaciador del `::after`; un padding aca levantaria el
    // degradado del borde visible y dejaria contenido sin velar justo debajo.
    const bodyRules = [...css.matchAll(/\.panelSheetBody\s*\{([^}]*)\}/g)].map((m) => m[1]);
    expect(bodyRules.length, 'tiene que existir alguna regla `.panelSheetBody`').toBeGreaterThan(0);
    for (const rule of bodyRules) {
      expect(rule).not.toMatch(/padding-bottom/);
    }
  });

  it('el cuerpo scrolleable de la tarjeta de escritorio no declara padding inferior propio', () => {
    // `.panelCardBody` es el scroller real; cualquier `padding-bottom` aca volveria
    // a levantar el degradado del borde visible, igual que en el sheet.
    const bodyRules = [...css.matchAll(/\.panelCardBody\s*\{([^}]*)\}/g)].map((m) => m[1]);
    expect(bodyRules.length, 'tiene que existir alguna regla `.panelCardBody`').toBeGreaterThan(0);
    for (const rule of bodyRules) {
      expect(rule).not.toMatch(/padding-bottom/);
    }
  });
});
