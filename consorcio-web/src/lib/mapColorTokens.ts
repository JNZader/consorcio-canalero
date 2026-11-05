/**
 * Reexport tipado de la paleta cartográfica.
 *
 * Los hex y las variables `--cc-map-*` viven en `theme.ts`. MapLibre no
 * resuelve `var()` dentro de `paint`: las capas leen el hex en
 * `mapColorTokens`. El DOM (leyendas, rótulos) usa `mapColorVar` o
 * `mapChromeVars`, que sí siguen a Río limpio y al oscuro.
 */
export {
  type MapColorToken,
  mapChromeVars,
  mapColorTokens,
  mapColorVar,
  mapCssVariable,
} from './theme';
