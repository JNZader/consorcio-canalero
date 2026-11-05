import type { Map as MapLibreMap, MapOptions } from 'maplibre-gl';
import { MAP_LOCALE_ES } from '../components/map2d/mapLibreLocale';
import { bootMapLibreWorker } from './maplibreLoader';

/**
 * Ciclo de vida compartido de MapLibre.
 *
 * Una sola política de worker (`bootMapLibreWorker` → `setWorkerUrl`),
 * de gestos y de destrucción. El shell del mapa (paneles, sheets,
 * overlays) no pasa por acá.
 *
 * `setWorkerUrl` vive solo en `maplibreLoader`. Este módulo lo espera;
 * no lo vuelve a configurar.
 */

/**
 * `embedded-form` — denuncia y sugerencia. El mapa está dentro de una
 * página que scrollea: un dedo mueve la página, dos dedos mueven el mapa.
 * Siempre enciende `cooperativeGestures`, también en puntero grueso.
 *
 * `primary-surface` — `/mapa` y el visor 3D. En puntero fino, Ctrl+rueda
 * para no robar el scroll de la página. En puntero grueso un dedo panea:
 * MapLibre, si el flag queda prendido, exige dos dedos y el mapa parece
 * trabado.
 *
 * El flag se lee una sola vez al construir. MapLibre no lo vuelve reactivo.
 */
export type MapLibreGesturePolicy = 'embedded-form' | 'primary-surface';

export interface MapLibreConstructor {
  Map: new (options: MapOptions) => MapLibreMap;
}

export interface CreateMapLibreMapParams {
  maplibre: MapLibreConstructor;
  gestures: MapLibreGesturePolicy;
  /** `cooperativeGestures` lo pone la política, no el caller. */
  options: Omit<MapOptions, 'cooperativeGestures'>;
  /**
   * Si se aborta durante el boot del worker, no se llama a `new Map()`.
   * StrictMode cancela el primer efecto antes de que el `await` retome;
   * construir igual gasta un contexto WebGL y el segundo `new Map()`
   * llega tarde o falla.
   */
  signal?: AbortSignal;
}

const destroyedMaps = new WeakSet<object>();
const pendingStyleSwaps = new WeakMap<object, Set<() => void>>();

/**
 * True cuando el puntero primario es grueso (dedo o stylus).
 *
 * Si `matchMedia` no está, devolvemos `false`: gestos cooperativos
 * prendidos, que es el default más seguro en escritorio.
 */
export function isCoarsePointerDevice(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  try {
    return window.matchMedia('(pointer: coarse)').matches;
  } catch {
    return false;
  }
}

export function resolveCooperativeGestures(policy: MapLibreGesturePolicy): boolean {
  if (policy === 'embedded-form') return true;
  return !isCoarsePointerDevice();
}

/**
 * Espera el boot único del worker y construye el mapa.
 * Locale por defecto: español rioplatense. Atribución por defecto:
 * compacta. `attributionControl: false` se respeta (el 3D agrega el
 * control a mano).
 */
export async function createMapLibreMap({
  maplibre,
  gestures,
  options,
  signal,
}: CreateMapLibreMapParams): Promise<MapLibreMap | null> {
  await bootMapLibreWorker();
  if (signal?.aborted) return null;
  const locale = options.locale ?? { ...MAP_LOCALE_ES };
  const attributionControl =
    options.attributionControl === undefined ? { compact: true } : options.attributionControl;
  return new maplibre.Map({
    ...options,
    locale,
    attributionControl,
    cooperativeGestures: resolveCooperativeGestures(gestures),
  });
}

/**
 * `map.remove()` una sola vez. El cleanup de React y la rama `cancelled`
 * del `await` pueden pegarle a la misma instancia (StrictMode); la
 * segunda llamada no vuelve a destruir ni relanza.
 */
export function destroyMapLibreMap(map: { remove?: () => void } | null | undefined): void {
  if (!map || destroyedMaps.has(map)) return;
  destroyedMaps.add(map);
  const swaps = pendingStyleSwaps.get(map);
  if (swaps) {
    for (const cancel of [...swaps]) cancel();
    swaps.clear();
  }
  try {
    map.remove?.();
  } catch {
    // MapLibre tira si `remove()` ya corrió por fuera de este helper.
  }
}

type StyleArg = NonNullable<Parameters<MapLibreMap['setStyle']>[0]>;
type StyleOpts = Parameters<MapLibreMap['setStyle']>[1];

/**
 * Reemplaza el estilo y resuelve en `style.load`.
 *
 * `/mapa` no lo usa para OSM/satélite: esas dos bases conviven en el
 * mismo estilo y se muestran con visibilidad de capa, así no se pierden
 * las fuentes vectoriales. El helper queda para un recambio de estilo
 * que no debe tirar abajo el `Map`.
 *
 * Si el mapa se destruye antes de `style.load`, la promesa se resuelve
 * (el swap se abandona) en lugar de quedar colgada.
 */
export function swapMapStyle(
  map: MapLibreMap,
  style: StyleArg,
  options?: StyleOpts
): Promise<void> {
  if (destroyedMaps.has(map)) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let settled = false;
    const swaps = pendingStyleSwaps.get(map) ?? new Set<() => void>();
    pendingStyleSwaps.set(map, swaps);

    const settle = (error?: unknown) => {
      if (settled) return;
      settled = true;
      swaps.delete(cancel);
      map.off('style.load', onLoad);
      if (error === undefined) resolve();
      else reject(error);
    };
    const cancel = () => settle();
    const onLoad = () => settle();
    swaps.add(cancel);
    map.once('style.load', onLoad);
    try {
      map.setStyle(style, options);
    } catch (error) {
      settle(error);
    }
  });
}
