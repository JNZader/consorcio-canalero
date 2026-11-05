/**
 * Escala de apilado del cromo de la app.
 *
 * El mapa tiene la suya (`MAP_Z` y `--z-map-*` en `map/classNames`) y no
 * entra acá. Los números son los literales que ya usaba cada capa: este
 * módulo les pone nombre y el resolver los publica como `--z-*`.
 * Cambiar un número mueve el stacking; no es parte de definir el token.
 *
 * El header (100) queda debajo de los paneles del mapa (1000) a propósito.
 */

export const Z_INDEX = {
  /** Contenedor de Leaflet, para no tapar popovers. */
  base: 0,
  /** Header sticky del sitio. */
  header: 100,
  /** Drawer de navegación pública. */
  drawer: 1000,
  /** `.mantine-Portal`, por encima del mapa. */
  portal: 9999,
  /** Popover de Mantine y skip links inline. */
  popover: 10000,
  /** Date picker y banner de actualización. */
  overlay: 10001,
  /** Notificaciones. */
  toast: 10002,
  /** `.skip-link` enfocado, por encima de todo el cromo. */
  skipLink: 100000,
} as const;

export type ZIndexToken = keyof typeof Z_INDEX;

/** Nombres CSS. Los emite `cssVariablesResolver`. */
export const Z_INDEX_VAR = {
  base: '--z-base',
  header: '--z-header',
  drawer: '--z-drawer',
  portal: '--z-portal',
  popover: '--z-popover',
  overlay: '--z-overlay',
  toast: '--z-toast',
  skipLink: '--z-skip-link',
} as const satisfies Record<ZIndexToken, `--z-${string}`>;
