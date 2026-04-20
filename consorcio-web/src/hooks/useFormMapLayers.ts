/**
 * Hook + utilities for adding reference layers (zona consorcio, hidrografía, caminos)
 * to MapLibre maps in public forms (reportes, sugerencias).
 *
 * Loads static GeoJSON files (no auth required) and provides:
 *  - zonaGeoJson: consorcio boundary polygon for clip/validation
 *  - addReferenceLayers(): paints zona + waterways + caminos onto a map
 *  - isInsideZona(): checks if a point falls inside the consorcio boundary
 */

import type { FeatureCollection } from 'geojson';
import { useQuery } from '@tanstack/react-query';
import type maplibregl from 'maplibre-gl';
import { useGEELayers } from './useGEELayers';
import { useWaterways, type WaterwayLayer } from './useWaterways';
import { logger } from '../lib/logger';

// ── Static file loaders ─────────────────────────────────────────────────────

async function fetchGeoJson(url: string): Promise<FeatureCollection | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return (await res.json()) as FeatureCollection;
  } catch {
    return null;
  }
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useFormMapLayers() {
  const { waterways } = useWaterways();
  const { layers: geeLayers } = useGEELayers({ layerNames: ['zona'] });

  const caminosQuery = useQuery({
    queryKey: ['form-map', 'caminos'],
    queryFn: () => fetchGeoJson('/capas/caminos.geojson'),
    staleTime: Number.POSITIVE_INFINITY,
  });

  return {
    zonaGeoJson: geeLayers.zona ?? null,
    caminosGeoJson: caminosQuery.data ?? null,
    waterways,
    loading: caminosQuery.isLoading,
  };
}

// ── Layer painting ──────────────────────────────────────────────────────────

const FORM_ZONA_SOURCE = 'form-zona';
const FORM_CAMINOS_SOURCE = 'form-caminos';

/**
 * Add reference layers to a MapLibre map matching the style from MapaMapLibre.tsx.
 * Order (bottom to top): caminos → waterways → zona boundary.
 *
 * Layers are inserted BEFORE any draw control layers (gl-draw-*) so they don't
 * block draw interaction or cover drawn geometry.
 */
export function addReferenceLayers(
  map: maplibregl.Map,
  opts: {
    zonaGeoJson: FeatureCollection | null;
    caminosGeoJson: FeatureCollection | null;
    waterways: WaterwayLayer[];
  },
) {
  const { zonaGeoJson, caminosGeoJson, waterways } = opts;

  // Find the first draw layer to insert reference layers BEFORE it
  const firstDrawLayer = map.getStyle()?.layers?.find(
    (l) => l.id.startsWith('gl-draw-') || l.id.includes('mapbox-gl-draw'),
  )?.id;

  // 1) Caminos — bottom layer (same as MapaMapLibre ROADS paint)
  if (caminosGeoJson) {
    if (!map.getSource(FORM_CAMINOS_SOURCE)) {
      map.addSource(FORM_CAMINOS_SOURCE, { type: 'geojson', data: caminosGeoJson });
    }
    if (!map.getLayer(`${FORM_CAMINOS_SOURCE}-line`)) {
      map.addLayer({
        id: `${FORM_CAMINOS_SOURCE}-line`,
        type: 'line',
        source: FORM_CAMINOS_SOURCE,
        paint: { 'line-color': '#FFEB3B', 'line-width': 2, 'line-opacity': 0.9 },
      }, firstDrawLayer);
    }
  }

  // 2) Waterways — rendered in the order declared in WATERWAY_DEFS.
  // Batch 5: the legacy `canales_existentes` last-draw special case was
  // retired along with the layer itself (Pilar Azul `useCanales` replaced it).
  for (const ww of waterways) {
    const srcId = `form-ww-${ww.id}`;
    const layerId = `${srcId}-line`;
    if (!map.getSource(srcId)) {
      map.addSource(srcId, { type: 'geojson', data: ww.data });
    }
    if (!map.getLayer(layerId)) {
      map.addLayer({
        id: layerId,
        type: 'line',
        source: srcId,
        paint: {
          'line-color': ww.style.color,
          'line-width': ww.style.weight,
          'line-opacity': ww.style.opacity,
        },
      }, firstDrawLayer);
    }
  }

  // 3) Zona consorcio boundary — top reference layer, below draw controls
  if (zonaGeoJson) {
    if (!map.getSource(FORM_ZONA_SOURCE)) {
      map.addSource(FORM_ZONA_SOURCE, { type: 'geojson', data: zonaGeoJson });
    }
    if (!map.getLayer(`${FORM_ZONA_SOURCE}-line`)) {
      map.addLayer({
        id: `${FORM_ZONA_SOURCE}-line`,
        type: 'line',
        source: FORM_ZONA_SOURCE,
        paint: { 'line-color': '#FF0000', 'line-width': 3, 'line-opacity': 0.95 },
      }, firstDrawLayer);
    }
  }
}

// ── Boundary validation ─────────────────────────────────────────────────────

/** Ray-casting point-in-polygon test for a single ring. */
function pointInRing(point: [number, number], ring: number[][]): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/** Check if point is inside a Polygon (first ring = exterior, rest = holes). */
function pointInPolygon(point: [number, number], coords: number[][][]): boolean {
  if (!pointInRing(point, coords[0])) return false;
  for (let i = 1; i < coords.length; i++) {
    if (pointInRing(point, coords[i])) return false; // inside a hole
  }
  return true;
}

/**
 * Check if a [lng, lat] point falls inside the consorcio boundary.
 */
export function isInsideZona(
  zonaGeoJson: FeatureCollection | null,
  lngLat: [number, number],
): boolean {
  if (!zonaGeoJson || !zonaGeoJson.features?.length) return true;
  try {
    for (const feature of zonaGeoJson.features) {
      const geom = feature.geometry;
      if (geom.type === 'Polygon') {
        if (pointInPolygon(lngLat, geom.coordinates as number[][][])) return true;
      } else if (geom.type === 'MultiPolygon') {
        for (const polygon of geom.coordinates as number[][][][]) {
          if (pointInPolygon(lngLat, polygon)) return true;
        }
      }
    }
    return false;
  } catch (err) {
    logger.warn('isInsideZona check failed', err);
    return true;
  }
}
