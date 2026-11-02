/**
 * IDECOR hydro overlays served by Martin once `scripts/sql/idecor_hidrografia.sql`
 * has been applied and the ETL has loaded rows. Empty views draw nothing.
 */

import type { Map as MapLibreMap } from 'maplibre-gl';
import { getMartinTileUrl, MARTIN_SOURCES } from '../../hooks/useMartinLayers';
import { setLayerVisibility } from './map2dUtils';

export const IDECOR_HYDRO_LAYERS = [
  {
    id: 'idecor_consorcios',
    table: 'vt_idecor_consorcios',
    kind: 'fill',
  },
  {
    id: 'idecor_cursos',
    table: 'vt_idecor_cursos',
    kind: 'line',
  },
  {
    id: 'idecor_cuencas',
    table: 'vt_idecor_cuencas',
    kind: 'fill',
  },
  {
    id: 'idecor_canales_riego',
    table: 'vt_idecor_canales_riego',
    kind: 'line',
  },
] as const;

/** Other layer effects pass partial map stubs. This sync runs on every ready
 *  map, so a stub without the style API must be a no-op instead of throwing. */
function hasStyleApi(map: MapLibreMap): boolean {
  return (
    typeof map.getSource === 'function' &&
    typeof map.addSource === 'function' &&
    typeof map.getLayer === 'function' &&
    typeof map.addLayer === 'function' &&
    typeof map.setLayoutProperty === 'function'
  );
}

export function syncIdecorHydroLayers(
  map: MapLibreMap,
  visible: Readonly<Record<string, boolean | undefined>>
): void {
  if (!hasStyleApi(map)) return;
  for (const layer of IDECOR_HYDRO_LAYERS) {
    const style = MARTIN_SOURCES[layer.table]?.style;
    if (!style) continue;
    if (!map.getSource(layer.id)) {
      map.addSource(layer.id, {
        type: 'vector',
        tiles: [getMartinTileUrl(layer.table)],
        minzoom: 0,
        maxzoom: 16,
      });
    }
    const lineId = `${layer.id}-line`;
    const fillId = `${layer.id}-fill`;
    if (layer.kind === 'fill' && !map.getLayer(fillId)) {
      map.addLayer({
        id: fillId,
        type: 'fill',
        source: layer.id,
        'source-layer': layer.table,
        paint: {
          'fill-color': style.fillColor,
          'fill-opacity': style.fillOpacity,
        },
      });
    }
    if (!map.getLayer(lineId)) {
      map.addLayer({
        id: lineId,
        type: 'line',
        source: layer.id,
        'source-layer': layer.table,
        paint: {
          'line-color': style.color,
          'line-width': style.weight,
          'line-opacity': style.opacity,
        },
      });
    }
    const on = !!visible[layer.id];
    if (layer.kind === 'fill') setLayerVisibility(map, fillId, on);
    setLayerVisibility(map, lineId, on);
  }
}
