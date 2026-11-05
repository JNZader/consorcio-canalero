/**
 * Escala de breakpoints. Es la de Mantine, declarada acá para que el tema,
 * los `useMediaQuery` y las hojas de estilo compartan un solo número.
 *
 * `@media` no puede leer custom properties: en CSS el valor `em` queda
 * escrito y `tests/unit/designTokens.test.ts` exige que coincida con esta
 * escala. `map.module.css` no se reescribe en este cambio; el test es el
 * nexo. Desde TypeScript hay que usar los helpers, no un literal.
 *
 * `48em` (sm) son 768px con la raíz de 16px del navegador. El complemento
 * exclusivo (`47.9375em`) es 1px menos, para que `min-width` y `max-width`
 * no sean verdaderos a la vez en 768px exacto.
 */

export const breakpoints = {
  xs: '36em',
  sm: '48em',
  md: '62em',
  lg: '75em',
  xl: '88em',
} as const;

export type Breakpoint = keyof typeof breakpoints;

/** 1px con raíz de 16px, en em. */
export const BREAKPOINT_EXCLUSIVE_GAP_EM = 0.0625;

export function breakpointEm(token: Breakpoint): number {
  return Number.parseFloat(breakpoints[token]);
}

/** Un pixel por debajo del breakpoint. Complemento exclusivo de `min-width`. */
export function belowBreakpoint(token: Breakpoint): string {
  return `${breakpointEm(token) - BREAKPOINT_EXCLUSIVE_GAP_EM}em`;
}

/** Un pixel por encima del breakpoint. */
export function aboveBreakpoint(token: Breakpoint): string {
  return `${breakpointEm(token) + BREAKPOINT_EXCLUSIVE_GAP_EM}em`;
}

/** Mobile-first: el viewport alcanza este breakpoint. */
export function mediaMinWidth(token: Breakpoint): string {
  return `(min-width: ${breakpoints[token]})`;
}

/** El viewport está por debajo del breakpoint (exclusivo). */
export function mediaBelow(token: Breakpoint): string {
  return `(max-width: ${belowBreakpoint(token)})`;
}

/**
 * `max-width` inclusivo, en el valor del breakpoint.
 * El sheet del mapa usa `max-width: 62em` (md), pareado con
 * `min-width: 62.0625em`. Las queries nuevas van con `mediaMinWidth`.
 */
export function mediaMaxWidth(token: Breakpoint): string {
  return `(max-width: ${breakpoints[token]})`;
}

export function mediaAbove(token: Breakpoint): string {
  return `(min-width: ${aboveBreakpoint(token)})`;
}
