/**
 * mapa-ctrl-glyph-centering.spec.ts — el glifo está centrado en su botón DE VERDAD.
 *
 * Este archivo existe por un fallo de método, no por una regresión suelta.
 * `tests/unit/MapCtrlTouchTargets.test.tsx` fija el CSS de la columna de
 * controles con REGEX SOBRE EL TEXTO de `map.module.css`, y el texto no tiene
 * cascada: una declaración presente y una declaración que GANA se leen igual.
 * Así se shippeó un `display: flex` muerto en `.mapCtrlButton` — nuestros
 * botones viven dentro del `.maplibregl-ctrl-group` de MapLibre, cuya regla
 * `button` es (0,1,1) y le gana a una clase pelada (0,1,0) — con la suite en
 * verde y los glifos corridos 5,5px en horizontal y 3,4px en vertical.
 *
 * Acá se mide GEOMETRÍA COMPUTADA REAL en un navegador: centro del glifo contra
 * centro del botón, para cada control de la columna, en escritorio y en
 * teléfono. Un `display` que no aplica no tiene dónde esconderse.
 *
 * ── QUÉ ES "EL GLIFO" SEGÚN EL BOTÓN ────────────────────────────────────────
 *   · Custom (`.mapCtrlButton`, Exportar / Medir…): el `<svg>` de Tabler.
 *   · Nativos (zoom, brújula, pantalla completa): MapLibre pinta un
 *     `span.maplibregl-ctrl-icon` que ocupa el content box entero, y el dibujo
 *     sale de un `mask-image` centrado dentro de ese span. El centro del span es
 *     entonces el centro de la tinta, y se verifica aparte que la máscara siga
 *     centrada (`mask-position`) y al tamaño del token.
 *   · Con caption visible (puntero grueso): el ícono se sube a propósito, y lo
 *     que centra es el BLOQUE ícono+caption. Se mide la unión de las dos cajas,
 *     que es lo que el ojo lee como "el contenido del botón".
 *
 * Requiere un entorno vivo: `E2E_APP_URL` lo declara y convierte los gates
 * estructurales en fallo (ver `helpers/strictGate.ts`).
 */

import { expect, test, type Page } from '@playwright/test';

import { MAP_CTRL_GLYPH_SIZE } from '../../src/components/map2d/map2dConfig';
import { gotoMapWorkspace } from './helpers/mapWorkspace';
import { requireCondition } from './helpers/strictGate';

/**
 * Tolerancia del centrado, en px CSS.
 *
 * Sub-pixel a propósito: los dos defectos que este archivo blinda medían 3,4px y
 * 5,5px (puntero fino) y hasta 13px (grueso), o sea dos órdenes de magnitud por
 * encima. El margen absorbe el redondeo de layout de un viewport escalado sin
 * dejar pasar nada que un humano vea.
 *
 * El medio pixel del separador de grupo NO se cubre acá — 0,5 < 0,75 — sino con
 * el test de concentricidad del content box, que lo mide exacto.
 */
const TOLERANCE = 0.75;

/** Los cuatro controles que MapLibre pinta en la columna, por su clase modificadora. */
const NATIVE_CTRLS = ['zoom-in', 'zoom-out', 'compass', 'fullscreen'] as const;

/**
 * El tamaño del glifo sale del MISMO módulo que se lo pasa a los iconos Tabler,
 * no de un literal copiado: `--map-ctrl-glyph-size` (CSS) y `MAP_CTRL_GLYPH_SIZE`
 * (TS) ya están atados por `MapCtrlTouchTargets`, y esto cierra el triángulo
 * midiendo que el `mask-size` de los sprites nativos también los siga.
 */
const GLYPH_SIZE = MAP_CTRL_GLYPH_SIZE;

interface CtrlSample {
  /** Identidad estable: la clase modificadora de la librería o nuestro aria-label. */
  id: string;
  kind: 'native' | 'custom' | 'unknown';
  /** Centro de la caja del glifo menos centro del border box del botón. */
  offset: [number, number];
  /** Caption pintado bajo el ícono (sólo en puntero grueso). */
  captioned: boolean;
  /** Separador de grupo de MapLibre y el padding que lo compensa. */
  borderTop: number;
  paddingBottom: number;
  /** Centro del content box menos centro del border box, en el eje vertical. */
  contentSkew: number;
  /** Geometría computada de la máscara; `null` en los botones custom. */
  maskPosition: string | null;
  maskSize: string | null;
}

/**
 * Mide todos los botones VISIBLES de los `.maplibregl-ctrl-group` de la página.
 *
 * Todo dentro de un solo `evaluate`: las cajas tienen que salir del mismo layout,
 * y un ida y vuelta por botón dejaría que un reflow intermedio moviera la
 * referencia contra la que se compara.
 */
async function measureCtrlColumn(page: Page): Promise<CtrlSample[]> {
  // Las captions entran en la caja que se mide, y su ancho depende de la
  // tipografía: medir antes de que Inter esté lista compara contra la métrica
  // del fallback.
  await page.evaluate(() => document.fonts.ready);

  return page.evaluate<CtrlSample[]>(() => {
    const samples: CtrlSample[] = [];

    for (const button of document.querySelectorAll('.maplibregl-ctrl-group button')) {
      const rect = button.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      const native = [...button.classList].find((c) => c.startsWith('maplibregl-ctrl-'));
      const id = native ?? button.getAttribute('aria-label') ?? button.className;

      const span = button.querySelector('.maplibregl-ctrl-icon');
      const svg = button.querySelector('svg');
      const glyph = span ?? svg;
      const kind = span ? 'native' : svg ? 'custom' : 'unknown';

      // El bloque que centra: el glifo solo, o glifo+caption cuando la caption
      // se pinta (puntero grueso). La unión, no el ícono, es lo que el ojo lee.
      let top = Number.POSITIVE_INFINITY;
      let left = Number.POSITIVE_INFINITY;
      let bottom = Number.NEGATIVE_INFINITY;
      let right = Number.NEGATIVE_INFINITY;
      const absorb = (box: DOMRect) => {
        top = Math.min(top, box.top);
        left = Math.min(left, box.left);
        bottom = Math.max(bottom, box.bottom);
        right = Math.max(right, box.right);
      };
      if (glyph) absorb(glyph.getBoundingClientRect());

      const caption = button.querySelector('[class*="mapCtrlButtonLabel"]');
      const captionBox = caption?.getBoundingClientRect();
      const captioned = !!captionBox && captionBox.width > 0 && captionBox.height > 0;
      if (captionBox && captioned) absorb(captionBox);

      const styles = getComputedStyle(button);
      const px = (value: string) => Number.parseFloat(value) || 0;
      // Concentricidad del content box: `border-top` + `padding-top` lo bajan,
      // `padding-bottom` lo sube. `clientHeight` es la caja de padding (sin
      // bordes), así que el content box se despeja restando los dos paddings.
      const paddingTop = px(styles.paddingTop);
      const paddingBottom = px(styles.paddingBottom);
      const borderTop = px(styles.borderTopWidth);
      const contentHeight = button.clientHeight - paddingTop - paddingBottom;
      const contentSkew = borderTop + paddingTop + contentHeight / 2 - rect.height / 2;

      // `getPropertyValue` y no la propiedad camelCase: `mask-*` sigue siendo
      // prefijado en parte del parque, y la forma por string devuelve lo que el
      // motor realmente resolvió sin depender de qué alias tipa lib.dom.
      const spanStyles = span ? getComputedStyle(span) : null;
      const maskProp = (name: string) =>
        spanStyles
          ? spanStyles.getPropertyValue(`mask-${name}`) ||
            spanStyles.getPropertyValue(`-webkit-mask-${name}`)
          : null;

      // Sin glifo el bloque queda en ±Infinity y el desvío sale NaN, que ninguna
      // comparación con la tolerancia acepta: un botón sin ícono FALLA, no pasa.
      samples.push({
        id,
        kind,
        offset: [
          (left + right) / 2 - (rect.left + rect.right) / 2,
          (top + bottom) / 2 - (rect.top + rect.bottom) / 2,
        ],
        captioned,
        borderTop,
        paddingBottom,
        contentSkew,
        maskPosition: maskProp('position'),
        maskSize: maskProp('size'),
      });
    }

    return samples;
  });
}

/**
 * Abre /mapa y espera a que la columna esté montada y con layout.
 *
 * Los gates son estructurales a propósito: una columna que no aparece dejaría
 * este archivo midiendo cero botones y reportando verde, que es exactamente el
 * modo de fallo que vino a cerrar.
 */
async function gotoMapWithControls(page: Page) {
  const ready = await gotoMapWorkspace(page);
  requireCondition(ready, 'El shell del mapa no montó (dev server no disponible)');

  // Nativos: los agrega `useMapInitialization` al construir el mapa.
  await expect(page.locator('button.maplibregl-ctrl-zoom-in')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('button.maplibregl-ctrl-fullscreen')).toBeVisible();
  // Custom: nuestros docks. Sin login sólo se pintan estos dos (dibujar / canal
  // / multi-selección están gateados por sesión y no se renderizan).
  await expect(page.getByRole('button', { name: 'Exportar' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Medir' })).toBeVisible();
}

/** Las tres afirmaciones, contra el viewport que el `describe` haya fijado. */
function declareCentringSuite(label: string, tags: string[]) {
  test(
    `${label}: cada glifo de la columna está centrado en su botón`,
    { tag: tags },
    async ({ page }) => {
      await gotoMapWithControls(page);
      const samples = await measureCtrlColumn(page);

      // Guarda anti-vacío: sin esto un cambio que deje de montar los docks haría
      // pasar el test midiendo nada.
      for (const ctrl of NATIVE_CTRLS) {
        expect(
          samples.some((s) => s.id === `maplibregl-ctrl-${ctrl}`),
          `el control nativo ${ctrl} tiene que estar en la columna`
        ).toBe(true);
      }
      expect(samples.filter((s) => s.kind === 'custom').length).toBeGreaterThanOrEqual(2);
      expect(samples.every((s) => s.kind !== 'unknown')).toBe(true);

      for (const sample of samples) {
        const detail = `${sample.id} (${sample.kind}${sample.captioned ? ', con caption' : ''})`;
        expect(Math.abs(sample.offset[0]), `${detail} — desvío horizontal`).toBeLessThanOrEqual(
          TOLERANCE
        );
        expect(Math.abs(sample.offset[1]), `${detail} — desvío vertical`).toBeLessThanOrEqual(
          TOLERANCE
        );
      }
    }
  );

  test(
    `${label}: el separador de grupo no descentra el content box`,
    { tag: tags },
    async ({ page }) => {
      await gotoMapWithControls(page);
      const samples = await measureCtrlColumn(page);

      // `.maplibregl-ctrl-group button + button { border-top: 1px }` con
      // `box-sizing: border-box` se come 1px del content box POR ARRIBA: sin
      // compensarlo, todo lo centrado adentro cae 0,5px y la columna se lee
      // dispareja. Medio pixel pasa por debajo de TOLERANCE, así que se mide
      // exacto acá.
      const divided = samples.filter((s) => s.borderTop > 0);
      expect(divided.length, 'algún botón tiene que llevar el separador').toBeGreaterThan(0);

      for (const sample of divided) {
        // El acoplamiento que documenta `map.module.css`: lo que el borde saca
        // arriba se devuelve abajo, o el desvío cambia de signo.
        expect(sample.paddingBottom, `${sample.id} — padding que compensa el separador`).toBe(
          sample.borderTop
        );
      }
      for (const sample of samples) {
        expect(Math.abs(sample.contentSkew), `${sample.id} — content box concéntrico`).toBeLessThan(
          0.05
        );
      }
    }
  );

  test(
    `${label}: la máscara de los sprites nativos sigue centrada en su span`,
    { tag: tags },
    async ({ page }) => {
      await gotoMapWithControls(page);
      const samples = await measureCtrlColumn(page);

      // El span nativo ocupa el content box entero, así que su centro sólo vale
      // como centro de la TINTA si la máscara está centrada dentro de él. Se
      // afirma también el tamaño: es el mismo token que pinta los `<svg>`
      // custom, y si se despareja la columna vuelve a leerse dispareja.
      const native = samples.filter((s) => s.kind === 'native');
      expect(native.length).toBe(NATIVE_CTRLS.length);

      for (const sample of native) {
        expect(sample.maskPosition, `${sample.id} — mask-position`).toBe('50% 50%');
        expect(sample.maskSize, `${sample.id} — mask-size`).toBe(`${GLYPH_SIZE}px ${GLYPH_SIZE}px`);
      }
    }
  );
}

/**
 * Escritorio, puntero fino: la columna son 29×29 y el glifo 18px, sin captions.
 * Es el caso donde el `text-align: left` de `UnstyledButton` de Mantine pegaba
 * el ícono al borde izquierdo (−5,5px) y la línea base lo subía 3,4px.
 */
test.describe('Columna de controles del mapa — escritorio (1280×800)', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  declareCentringSuite('escritorio', ['@e2e', '@mapa', '@iconos']);
});

/**
 * Teléfono parado, puntero grueso: los botones crecen a 44px y los custom
 * revelan su caption. El desvío del ícono solo era de 13px acá, y además es el
 * único viewport donde la caja que centra es la unión ícono+caption.
 */
test.describe('Columna de controles del mapa — teléfono (390×844)', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  declareCentringSuite('teléfono', ['@e2e', '@mapa', '@iconos', '@movil']);
});
