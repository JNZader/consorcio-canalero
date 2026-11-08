# Tokens de diseño

Capa semántica sobre Mantine 9. No cambia el look de las páginas: publica
variables y deja una sola escala para breakpoints y z-index. Los dos arreglos
de color de este cambio son `institucional[9]` (antes repetía `[7]`) y
`theme-color`, que ahora es el verde primario `#2d8f68`.

El provider fusiona `cssVariablesResolver` (`src/lib/theme.ts`) con las
variables de Mantine. Los alias `--cc-*` apuntan a `--mantine-*`, así que
claro y oscuro siguen al tema.

## Colores

| Token | Variable | Apunta a |
|---|---|---|
| primary | `--cc-color-primary` | `institucional[5]` (`#2d8f68`) |
| surface | `--cc-color-surface` | `--mantine-color-body` |
| surface raised | `--cc-color-surface-raised` | gray-0 en claro, dark-6 en oscuro |
| text | `--cc-color-text` | `--mantine-color-text` |
| text muted | `--cc-color-text-muted` | `--mantine-color-dimmed` |
| border | `--cc-color-border` | `--mantine-color-default-border` |
| danger | `--cc-color-danger` | `alerta` 6 / 4 |
| warning | `--cc-color-warning` | `orange` 6 / 4 |
| success | `--cc-color-success` | `exito` 6 / 4 |

`PRIMARY_GREEN` (`#2d8f68`) es la marca. El botón filled usa el tono 6
`#16654a` con texto blanco: blanco sobre `#2d8f68` queda en 4,01:1 y no
llega a AA de texto chico. No hay que igualarlos.

`--cc-color-status-review` es el texto de «en revisión»: institucional 7
en claro e institucional 3 en oscuro, medido sobre el tint del badge.

`PRIMARY_GREEN` en `theme.ts` es el verde de `index.html` (`theme-color`,
`msapplication-TileColor`) y de `theme_color` en el manifest de
`vite.config.ts`.

## Espacio, radio, sombra, tipo, toque

Escala `xs`–`xl`, alias de Mantine:

- `--cc-space-*`, `--cc-radius-*`, `--cc-shadow-*`
- `--cc-font-family`, `--cc-font-family-heading`
- `--cc-font-size-*`, `--cc-line-height-*` (también `h1`–`h6`)
- `--cc-touch-min`: `44px`

## Z-index

`src/lib/zIndex.ts`. El mapa sigue en `MAP_Z` / `--z-map-*` y no se renombra
en este cambio.

| Token | Variable | Valor |
|---|---|---|
| base | `--z-base` | 0 |
| header | `--z-header` | 100 |
| drawer | `--z-drawer` | 1000 |
| portal | `--z-portal` | 9999 |
| popover | `--z-popover` | 10000 |
| overlay | `--z-overlay` | 10001 |
| toast | `--z-toast` | 10002 |
| skipLink | `--z-skip-link` | 100000 |

## Breakpoints

Fuente única: `src/lib/breakpoints.ts`, la escala de Mantine (`xs` 36em,
`sm` 48em, `md` 62em, `lg` 75em, `xl` 88em). El tema la declara en
`breakpoints` y el resolver publica `--cc-breakpoint-*` más
`--cc-breakpoint-sm-max` (`47.9375em`) y `--cc-breakpoint-md-above`
(`62.0625em`).

`@media` no lee custom properties. Desde TypeScript: `mediaMinWidth('sm')`
(mobile-first). En CSS el `em` queda escrito; `tests/unit/designTokens.test.ts`
exige que coincida con el token. Las hojas en `src/styles/components/map/` no se reescriben acá.

## Colores de mapa

Los hex cartográficos viven en `theme.ts` (`mapColorTokens`). El resolver
los publica como `--cc-map-<hex>` (minúsculas, sin `#`: `--cc-map-2563eb`).
Dos claves que solo cambian de mayúsculas comparten esa variable.

MapLibre no resuelve `var()` en `paint`. `src/lib/mapColorTokens.ts`
reexporta el objeto para las capas. En el DOM, `mapColorVar(token)` o
`mapChromeVars`.

Las rampas científicas (raster, pendiente Okabe–Ito, cuencas) usan el mismo
hex en claro y en oscuro: son datos. El cromo del rótulo de medición sí
sigue el esquema:

| Token | Claro | Oscuro |
|---|---|---|
| `--cc-map-label-surface` | blanco al 96% | `dark-7` al 94% |
| `--cc-map-label-text` | `#333` | `--cc-color-text` |
| `--cc-map-label-border` | `#fd7e14` | el mismo |
| `--cc-map-profile-border` | `blue-3` | `blue-4` |
| `--cc-map-profile-surface` | `blue-0` | `dark-5` |
| `--cc-map-profile-text` | `blue-6` | `blue-2` |

El logo de Google conserva sus hex de marca dentro del registro.

## Hex nuevos

`npm run lint` corre `scripts/lint-no-new-hex.mjs`. Compara literales de
string en `.ts`/`.tsx` (sin tests) contra `scripts/hex-color-baseline.json`
y falla si un archivo suma un hex. No reescribe los que ya están.

Excepciones:

- `/* hex-color-allow-file */` en las primeras 20 líneas. La paleta de UI
  y la de mapa están en `theme.ts`.
- `// hex-color-allow` en la línea del literal o en la anterior.

Para aceptar un hex nuevo a propósito:
`node scripts/lint-no-new-hex.mjs --update`.
