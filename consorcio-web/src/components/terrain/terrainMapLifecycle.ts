import type * as maplibregl from 'maplibre-gl';
import type { LngLatBoundsLike, Map as MapLibreMap, StyleSpecification } from 'maplibre-gl';
import { createMapLibreMap, destroyMapLibreMap } from '../../lib/maplibreLifecycle';
import { MAP_LOCALE_ES } from '../map2d/mapLibreLocale';

/**
 * Adaptador del visor 3D hacia el ciclo de vida compartido.
 *
 * El terreno sigue dueño del estilo DEM, los controles, la clasificación
 * de errores de tiles GEE, los listeners del canvas y el rebuild de
 * `terrain-rgb`. Acá solo entran worker, gestos de superficie principal,
 * locale, atribución apagada (el visor agrega `AttributionControl` a mano)
 * y la destrucción idempotente.
 */
export interface TerrainMapInit {
  readonly container: HTMLElement;
  readonly style: StyleSpecification;
  readonly center: [number, number];
  readonly zoom: number;
  readonly minZoom: number;
  readonly maxBounds: LngLatBoundsLike;
  readonly pitch: number;
  readonly bearing: number;
  readonly maxPitch: number;
  readonly maxTileCacheSize: number;
}

export function createTerrainMapLibreMap(
  maplibre: Pick<typeof maplibregl, 'Map'>,
  init: TerrainMapInit,
  signal?: AbortSignal
): Promise<MapLibreMap | null> {
  return createMapLibreMap({
    maplibre,
    gestures: 'primary-surface',
    signal,
    options: {
      container: init.container,
      style: init.style,
      center: init.center,
      zoom: init.zoom,
      minZoom: init.minZoom,
      maxBounds: init.maxBounds,
      pitch: init.pitch,
      bearing: init.bearing,
      maxPitch: init.maxPitch,
      hash: 'v',
      locale: { ...MAP_LOCALE_ES },
      attributionControl: false,
      maxTileCacheSize: init.maxTileCacheSize,
    },
  });
}

export { destroyMapLibreMap };
