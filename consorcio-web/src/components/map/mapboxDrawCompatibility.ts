import type maplibregl from 'maplibre-gl';

/**
 * @mapbox/mapbox-gl-draw expects Mapbox GL class names on the map container/canvas.
 * MapLibre uses different class names, so we add compatible aliases.
 */
export function ensureMapboxDrawCompatibility(map: maplibregl.Map): void {
  map.getContainer().classList.add('mapboxgl-map');
  map.getCanvas().classList.add('mapboxgl-canvas');

  const canvasContainer = map.getCanvasContainer();
  canvasContainer.classList.add('mapboxgl-canvas-container');

  if (canvasContainer.classList.contains('maplibregl-interactive')) {
    canvasContainer.classList.add('mapboxgl-interactive');
  }
}
