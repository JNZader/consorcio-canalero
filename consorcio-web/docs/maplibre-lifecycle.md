# Ciclo de vida de MapLibre

`src/lib/maplibreLifecycle.ts` es la puerta de creación y destrucción de los
mapas 2D públicos y de los formularios. El shell (paneles, sheets, overlays)
no pasa por acá.

## API

- `createMapLibreMap({ maplibre, gestures, options, signal })` espera
  `bootMapLibreWorker()` y construye el `Map`. Si `signal` ya está abortado
  al retomar el `await`, no llama a `new Map()` (el primer pase de StrictMode).
  El boot es uno solo por página:
  `setWorkerUrl` vive en `maplibreLoader` y este módulo no lo vuelve a llamar.
  `/mapa` puede disparar el mismo boot al importar el módulo, para anticipar
  la descarga del worker; no es una segunda política.
- `destroyMapLibreMap(map)` llama `remove()` una sola vez. El cleanup de React
  y la rama `cancelled` del `await` pueden pegarle a la misma instancia
  (StrictMode). La segunda llamada no relanza.
- `resolveCooperativeGestures(policy)`:
  - `embedded-form`: siempre activo. Denuncia y sugerencia scrollean con un
    dedo; dos dedos mueven el mapa.
  - `primary-surface`: activo solo con puntero fino. En táctil un dedo panea
    `/mapa` y el visor 3D.
- `swapMapStyle(map, style)` reemplaza el estilo y resuelve en `style.load`.
  Si el mapa se destruye antes, la promesa se resuelve. `/mapa` no lo usa para
  OSM/satélite: las dos bases conviven en el mismo estilo y se cambian con
  visibilidad de capa, para no perder las fuentes vectoriales.

Locale por defecto: `MAP_LOCALE_ES`. Atribución por defecto: `{ compact: true }`.
`attributionControl: false` se respeta.

## Quién lo usa

| Superficie | Gestos | Notas |
|---|---|---|
| Denuncia, `LocationSection` | `embedded-form` | Sigue cargando el chunk con `loadMapLibre` |
| Sugerencia, `SuggestionGeometrySection` | `embedded-form` | Igual que la denuncia |
| `/mapa`, `useMapInitialization` | `primary-surface` | `preserveDrawingBuffer`, `hash: 'v'`, teclado |
| Comparador de `/mapa` | — | Mapa no interactivo. Se construye en el mismo turno (el worker ya está) y se tira con `destroyMapLibreMap` |
| 3D, `createTerrainMapLibreMap` | `primary-surface` | Adaptador |

## 3D

El acoplamiento del terreno es alto: estilo DEM, pitch, caché de tiles,
controles, error de tiles GEE (un 503 de Earth Engine no tira abajo la vista),
listeners del canvas y el rebuild de `terrain-rgb`. Eso queda en
`TerrainViewer3D`. El adaptador `src/components/terrain/terrainMapLifecycle.ts`
solo unifica worker, gestos, locale, atribución apagada en el constructor y
la destrucción.

## Fuera de este módulo

Los mapas de admin (`CanalesPublicacionMap`, `SugerenciaGeometryMap`,
`useImageExplorerMap`) siguen con `bootMapLibreWorker` y `new Map` propio.
Comparten el mismo boot, no esta fachada.
