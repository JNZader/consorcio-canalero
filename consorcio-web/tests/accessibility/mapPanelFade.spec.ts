/**
 * mapPanelFade.spec.ts — the sticky fade must never paint over content.
 *
 * `.panelCardBody` (the scroller inside the `.infoPanel` / `.fichaPanel` desktop
 * cards) and `.panelSheetBody` (mobile bottom sheet) end in a sticky `::after`
 * gradient: the affordance that says
 * "there is more below". It shipped with `margin-top: -24px` plus a
 * compensating `padding-bottom` on the scroller, and that pair does NOT
 * compensate: a sticky box never leaves its CONTAINING BLOCK, which is the
 * scroller's CONTENT box, so the padding lifts the fade's resting place by
 * exactly what it adds underneath. Result: the gradient sat on the last line of
 * every ficha tab and that row read as "cut in half". Measured on the shipped
 * CSS: the whole 17.6px line inside the fade, and up to 144/255 of wash on its
 * pixels — worst at the baseline, which is why it looked like a cut.
 *
 * Neither `tests/unit/mapPanelFadeClearance.test.ts` (CSS as text) nor any
 * jsdom/happy-dom test can catch that: it is a LAYOUT fact. This spec measures
 * it in real engines, on the real stylesheet, with no app and no backend —
 * `setContent` builds the two panel shapes out of `map.module.css` itself.
 *
 * Two independent assertions per shape:
 *   1. geometry — at the bottom of the scroll there are >= 24px (the fade's own
 *      height) between the last line and the bottom of the content box, i.e.
 *      the fade rests on empty spacer.
 *   2. pixels — the last line renders IDENTICALLY with and without the fade.
 *      This is the user-visible symptom, and it holds the line even if the
 *      geometry rationale above ever stops being the reason.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type Page, expect, test } from '@playwright/test';

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(HERE, '../../src/styles/components/map.module.css'), 'utf8')
  // `:global(...)` is CSS-modules syntax, invalid to a browser parser. Those
  // rules target MapLibre/Mantine internals and match nothing in this harness;
  // unwrapping them just keeps the parser from dropping neighbours.
  .replace(/:global\(([^)]*)\)/g, '$1');

/** `height` of the fade in both `::after` blocks. */
const FADE = 24;

/** Enough rows that every shape overflows its cap and actually scrolls. */
const LINES = Array.from({ length: 60 }, (_, i) =>
  i === 59 ? 'Normales CHIRPS 1991-2020' : `Dato ${i + 1}`
);

type Shape =
  | { kind: 'card'; panelClass: 'infoPanel' | 'fichaPanel' }
  | { kind: 'sheet'; stage: 'peek' | 'medio' | 'alto' };

/** Extra class the shell puts on the sheet per stage (`medio` has none). */
const STAGE_CLASS = { peek: 'panelSheetPeek', medio: '', alto: 'panelSheetExpanded' } as const;

/**
 * Rebuilds what `MapPanelShell` renders, with the REAL stylesheet. The inline
 * `padding: 16px` is not decoration: Mantine 8 emits `<Paper p="md">` as an
 * inline `padding` shorthand, which is why the desktop rule needs `!important`.
 *
 * Since R3-001 the desktop card is a two-box shape: the `<Paper>` root
 * (`.infoPanel` / `.fichaPanel`) keeps `pointer-events: none` so the map stays
 * clickable through it, and the scrolling + the sticky fade moved to the inner
 * `.panelCardBody` wrapper. The scroller measured here is therefore that inner
 * wrapper, exactly as the shell mounts it (`MapPanelShell.tsx:210-215`).
 */
function harness(shape: Shape): string {
  const rows = LINES.map(
    (text, i) => `<p${i === LINES.length - 1 ? ' id="last"' : ''}>${text}</p>`
  ).join('');

  const body =
    shape.kind === 'card'
      ? `<div class="${shape.panelClass}" style="padding: 16px;">
           <div class="panelCardBody" id="scroller">${rows}</div>
         </div>`
      : `<div class="panelSheet ${STAGE_CLASS[shape.stage]}" data-stage="${shape.stage}" style="padding: 16px;">
           <div class="panelSheetHeader" style="height: 18px;"></div>
           <div class="panelSheetBody" id="scroller">${rows}</div>
         </div>`;

  return `<!doctype html>
    <style>
      html, body { margin: 0; background: #101010; }
      /* The panels read Mantine's spacing scale; nothing else here does. */
      :root { --mantine-spacing-md: 16px; }
      /* Stands in for the map canvas: the positioned ancestor the panels are
         absolutely placed in, and the 100% their max-heights resolve against. */
      #stage { position: relative; width: min(900px, 100vw); height: 650px; overflow: hidden; }
      ${CSS}
      /* Dark text on the panel's own light background — the fade is a WHITE
         wash in light mode, so light text here would hide the very defect this
         spec measures. */
      p { margin: 0 0 6px; color: #101010; font: 14px/1.2 sans-serif; }
    </style>
    <div id="stage">${body}</div>`;
}

async function mount(page: Page, shape: Shape) {
  await page.setContent(harness(shape));
  // El scroller tiene que SER un scroller dentro del stage capado. Si el CSS
  // deja de capear su alto — p. ej. un `max-height: 100%` que resuelve a `none`
  // contra un padre de alto `auto` — entonces `scrollHeight === clientHeight`,
  // el poll de "ya esta al fondo" da true sin scrollear y TODOS los asserts de
  // este spec pasan en vacio. Ese fue exactamente el bug que dejo la tarjeta de
  // escritorio sin scrollbar; este assert lo convierte en un rojo.
  const overflows = await page.evaluate(() => {
    const el = document.getElementById('scroller');
    return el ? el.scrollHeight > el.clientHeight : false;
  });
  expect(overflows, 'el scroller tiene que desbordar dentro del stage capado').toBe(true);
  await page.evaluate(() => {
    const el = document.getElementById('scroller');
    if (el) el.scrollTop = el.scrollHeight;
  });
  // The scroll has to be applied before anything is measured or captured.
  await expect
    .poll(() =>
      page.evaluate(() => {
        const el = document.getElementById('scroller');
        return el ? el.scrollTop + el.clientHeight >= el.scrollHeight - 1 : false;
      })
    )
    .toBe(true);
}

/** PNG of the last line's own box, as a data URL. */
async function lastLineShot(page: Page): Promise<string> {
  const shot = await page.locator('#last').screenshot();
  return `data:image/png;base64,${shot.toString('base64')}`;
}

/**
 * Worst per-pixel difference between two captures of the same line, 0-255.
 *
 * Deliberately NOT a luminance threshold: the gradient is transparent at its top
 * edge, so a metric over the whole box (peak, mean) barely moves even when the
 * line is fully inside the fade — the shipped bug hid from exactly that kind of
 * check. A veiled line differs from an unveiled one pixel by pixel, and a line
 * the fade never reaches is byte-identical.
 */
async function worstPixelDelta(page: Page, a: string, b: string): Promise<number> {
  return page.evaluate(
    async ([urlA, urlB]) => {
      const decode = async (url: string) => {
        const img = new Image();
        img.src = url;
        await img.decode();
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;
        ctx.drawImage(img, 0, 0);
        return ctx.getImageData(0, 0, canvas.width, canvas.height);
      };
      const imgA = await decode(urlA);
      const imgB = await decode(urlB);
      if (!imgA || !imgB) return Number.NaN;
      if (imgA.width !== imgB.width || imgA.height !== imgB.height) return Number.NaN;
      let worst = 0;
      for (let i = 0; i < imgA.data.length; i += 4) {
        for (let c = 0; c < 3; c += 1) {
          const delta = Math.abs(imgA.data[i + c] - imgB.data[i + c]);
          if (delta > worst) worst = delta;
        }
      }
      return worst;
    },
    [a, b]
  );
}

const SHAPES: ReadonlyArray<readonly [string, Shape]> = [
  ['tarjeta de escritorio — InfoPanel', { kind: 'card', panelClass: 'infoPanel' }],
  ['tarjeta de escritorio — ficha territorial', { kind: 'card', panelClass: 'fichaPanel' }],
  ['bottom sheet — peek (25%)', { kind: 'sheet', stage: 'peek' }],
  ['bottom sheet — medio (45%)', { kind: 'sheet', stage: 'medio' }],
  ['bottom sheet — alto (85%)', { kind: 'sheet', stage: 'alto' }],
];

test.describe('Degradado de los paneles del mapa', () => {
  for (const [name, shape] of SHAPES) {
    test(`${name}: el degradado descansa sobre espaciador, no sobre el ultimo renglon`, async ({
      page,
    }) => {
      await mount(page, shape);

      const gap = await page.evaluate(() => {
        const scroller = document.getElementById('scroller');
        const last = document.getElementById('last');
        if (!scroller || !last) return Number.NaN;
        const cs = getComputedStyle(scroller);
        // The fade is `position: sticky; bottom: 0` and a sticky box is clamped
        // to its containing block, i.e. this content box — never the padding
        // box. So its resting top edge is `contentBoxBottom - height`.
        const contentBoxBottom =
          scroller.getBoundingClientRect().bottom -
          Number.parseFloat(cs.paddingBottom) -
          Number.parseFloat(cs.borderBottomWidth || '0');
        return contentBoxBottom - last.getBoundingClientRect().bottom;
      });

      expect(
        gap,
        'el ultimo renglon tiene que quedar por encima del degradado'
      ).toBeGreaterThanOrEqual(FADE);
    });

    test(`${name}: el ultimo renglon se pinta igual con y sin degradado`, async ({ page }) => {
      await mount(page, shape);
      const withFade = await lastLineShot(page);

      // Se apaga el DIBUJO del degradado, no el pseudo-elemento: sacarlo con
      // `content: none` se llevaria tambien el espaciador y el renglon se
      // moveria, que es cambiar dos cosas a la vez. Asi la caja, el alto
      // scrolleable y la posicion del renglon quedan clavados y lo unico que
      // cambia entre las dos capturas es si el degradado pinta o no.
      await page.addStyleTag({
        content: '.panelCardBody::after, .panelSheetBody::after { background: none !important; }',
      });
      const withoutFade = await lastLineShot(page);

      // Con la misma geometria en las dos capturas, un degradado que no toca el
      // renglon da diferencia CERO; el margen de 1 es solo por redondeo de
      // composicion. El bug daba 144-229.
      const delta = await worstPixelDelta(page, withFade, withoutFade);
      expect(delta, 'el degradado esta pintando encima del ultimo renglon').toBeLessThanOrEqual(1);
    });
  }
});
