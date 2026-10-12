/** CART-06: parcel/soil fills are noise below city zoom. */
export const CATASTRO_LAYER_MIN_ZOOM = 12;
export const SOIL_LAYER_MIN_ZOOM = 12;

export const LAYER_MIN_ZOOM: Readonly<Record<string, number>> = {
  catastro: CATASTRO_LAYER_MIN_ZOOM,
  soil: SOIL_LAYER_MIN_ZOOM,
};

export const LAYER_ZOOM_IN_HINT = 'Acercate para ver esta capa';

export function layerBelowMinZoom(layerId: string, zoom: number): boolean {
  const min = LAYER_MIN_ZOOM[layerId];
  return min !== undefined && zoom < min;
}

export function applyLayerMinZoom(
  map: {
    getLayer: (id: string) => unknown;
    setLayerZoomRange?: (id: string, minzoom: number, maxzoom: number) => void;
  },
  layerId: string,
  minzoom: number
): void {
  if (!map.getLayer(layerId) || typeof map.setLayerZoomRange !== 'function') return;
  map.setLayerZoomRange(layerId, minzoom, 24);
}
