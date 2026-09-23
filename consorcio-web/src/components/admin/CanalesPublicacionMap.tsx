import type { Feature, FeatureCollection, LineString, MultiLineString } from 'geojson';
import maplibregl, {
  type DataDrivenPropertyValueSpecification,
  type FilterSpecification,
} from 'maplibre-gl';
import { useEffect, useRef } from 'react';
import 'maplibre-gl/dist/maplibre-gl.css';

import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import type { CanalLineCollection, CanalLineGeometry } from '../../lib/api/canalesPublicacion';
import { isSrPaListId, srPaFeatureById } from '../../lib/aprhiSrPa';
import {
  ADMIN_CANAL_LINE_LAYER_ID,
  CANAL_HIT_LAYER,
  type CanalHit,
  clickBbox,
  collectCanalHits,
  kmzGroupVisible,
  overlayLabelsVisible,
  overlayLineOffsetPx,
  overlayLineOpacity,
  pickDefaultHit,
} from '../../lib/canalesPublicacionOverlap';
import { MAP_GLYPHS_URL } from '../map2d/roadLabelLayer';

const CONS_SRC = 'pub-consorcio';
const EXISTENTES_SRC = 'pub-existentes';
const SR_SRC = 'pub-aprhi-sr';
const ZONA_SRC = 'pub-zona';
const CONS_CASING = 'pub-cons-casing';
const CONS_LINE = ADMIN_CANAL_LINE_LAYER_ID.KMZ;
const CONS_LABEL = 'pub-cons-label';
const EXISTENTES_LINE = ADMIN_CANAL_LINE_LAYER_ID.EXISTENTES;
const EXISTENTES_LABEL = 'pub-existentes-label';
const SR_LINE = ADMIN_CANAL_LINE_LAYER_ID.SR_PA;
const SR_LABEL = 'pub-aprhi-sr-label';

function overlayOpacityExpr(
  selectedId: string | null,
  kmzVisible: boolean,
  idProp: string
): DataDrivenPropertyValueSpecification<number> {
  const selected = selectedId ?? '';
  return [
    'case',
    ['==', ['get', idProp], selected],
    overlayLineOpacity(kmzVisible, true),
    overlayLineOpacity(kmzVisible, false),
  ];
}

function srPaPaint(
  selectedId: string | null,
  kmzVisible: boolean
): {
  'line-color': DataDrivenPropertyValueSpecification<string>;
  'line-width': DataDrivenPropertyValueSpecification<number>;
  'line-opacity': DataDrivenPropertyValueSpecification<number>;
  'line-offset': number;
} {
  const selected = selectedId ?? '';
  return {
    'line-color': [
      'case',
      ['==', ['get', 'list_id'], selected],
      '#facc15',
      ['==', ['get', 'Estado_Registro'], 'Eliminado'],
      '#78716c',
      '#c2410c',
    ],
    'line-width': ['case', ['==', ['get', 'list_id'], selected], 6, 3],
    'line-opacity': overlayOpacityExpr(selectedId, kmzVisible, 'list_id'),
    'line-offset': overlayLineOffsetPx(CANAL_HIT_LAYER.SR_PA, kmzVisible),
  };
}

export const EMPTY_LINE_COLLECTION: CanalLineCollection = {
  type: 'FeatureCollection',
  features: [],
};

function consorcioPaint(selectedId: string | null): {
  'line-color': DataDrivenPropertyValueSpecification<string>;
  'line-width': DataDrivenPropertyValueSpecification<number>;
  'line-opacity': DataDrivenPropertyValueSpecification<number>;
} {
  const selected = selectedId ?? '';
  return {
    'line-color': [
      'case',
      ['==', ['get', 'id'], selected],
      '#facc15',
      ['boolean', ['get', 'publicado'], false],
      '#22c55e',
      '#94a3b8',
    ],
    'line-width': ['case', ['==', ['get', 'id'], selected], 7, 4],
    'line-opacity': ['case', ['boolean', ['get', 'publicado'], false], 0.95, 0.5],
  };
}

function consorcioCasingPaint(selectedId: string | null): {
  'line-color': string;
  'line-width': DataDrivenPropertyValueSpecification<number>;
  'line-opacity': number;
} {
  const selected = selectedId ?? '';
  return {
    'line-color': '#0f172a',
    'line-width': ['case', ['==', ['get', 'id'], selected], 10, 7],
    'line-opacity': 0.85,
  };
}

function existentesPaint(
  selectedId: string | null,
  kmzVisible: boolean
): {
  'line-color': DataDrivenPropertyValueSpecification<string>;
  'line-width': DataDrivenPropertyValueSpecification<number>;
  'line-opacity': DataDrivenPropertyValueSpecification<number>;
  'line-offset': number;
} {
  const selected = selectedId ?? '';
  return {
    'line-color': ['case', ['==', ['get', 'id'], selected], '#facc15', '#7c3aed'],
    'line-width': ['case', ['==', ['get', 'id'], selected], 6, 3],
    'line-opacity': overlayOpacityExpr(selectedId, kmzVisible, 'id'),
    'line-offset': overlayLineOffsetPx(CANAL_HIT_LAYER.EXISTENTES, kmzVisible),
  };
}

/** MapLibre filter for KMZ traces. Does not change `publicado`. */
export function consorcioVisibilityFilter(
  showRelevados: boolean,
  showPropuestas: boolean
): FilterSpecification {
  if (showRelevados && showPropuestas) {
    return ['has', 'id'];
  }
  if (showRelevados) {
    return ['==', ['get', 'estado'], 'relevado'];
  }
  if (showPropuestas) {
    return ['==', ['get', 'estado'], 'propuesto'];
  }
  return ['==', ['get', 'id'], '__hidden__'];
}

function applyConsorcioFilter(
  map: maplibregl.Map,
  showRelevados: boolean,
  showPropuestas: boolean
): void {
  const filter = consorcioVisibilityFilter(showRelevados, showPropuestas);
  if (map.getLayer(CONS_CASING)) {
    map.setFilter(CONS_CASING, filter);
  }
  if (map.getLayer(CONS_LINE)) {
    map.setFilter(CONS_LINE, filter);
  }
  if (map.getLayer(CONS_LABEL)) {
    map.setFilter(CONS_LABEL, filter);
  }
}

function applyLineSource(map: maplibregl.Map, sourceId: string, data: FeatureCollection): void {
  const source = map.getSource(sourceId);
  if (source) {
    (source as maplibregl.GeoJSONSource).setData(data);
  }
}

function applyOverlayPaint(
  map: maplibregl.Map,
  selectedId: string | null,
  kmzVisible: boolean
): void {
  if (map.getLayer(EXISTENTES_LINE)) {
    const paint = existentesPaint(selectedId, kmzVisible);
    map.setPaintProperty(EXISTENTES_LINE, 'line-color', paint['line-color']);
    map.setPaintProperty(EXISTENTES_LINE, 'line-width', paint['line-width']);
    map.setPaintProperty(EXISTENTES_LINE, 'line-opacity', paint['line-opacity']);
    map.setPaintProperty(EXISTENTES_LINE, 'line-offset', paint['line-offset']);
  }
  if (map.getLayer(SR_LINE)) {
    const paint = srPaPaint(selectedId, kmzVisible);
    map.setPaintProperty(SR_LINE, 'line-color', paint['line-color']);
    map.setPaintProperty(SR_LINE, 'line-width', paint['line-width']);
    map.setPaintProperty(SR_LINE, 'line-opacity', paint['line-opacity']);
    map.setPaintProperty(SR_LINE, 'line-offset', paint['line-offset']);
  }
}

function applyOverlayLabelVisibility(
  map: maplibregl.Map,
  showAprhi: boolean,
  showExistentes: boolean,
  kmzVisible: boolean
): void {
  if (map.getLayer(SR_LABEL)) {
    map.setLayoutProperty(
      SR_LABEL,
      'visibility',
      overlayLabelsVisible(showAprhi, kmzVisible) ? 'visible' : 'none'
    );
  }
  if (map.getLayer(EXISTENTES_LABEL)) {
    map.setLayoutProperty(
      EXISTENTES_LABEL,
      'visibility',
      overlayLabelsVisible(showExistentes, kmzVisible) ? 'visible' : 'none'
    );
  }
}

function applyConsorcioPaint(map: maplibregl.Map, selectedId: string | null): void {
  if (map.getLayer(CONS_CASING)) {
    const casing = consorcioCasingPaint(selectedId);
    map.setPaintProperty(CONS_CASING, 'line-color', casing['line-color']);
    map.setPaintProperty(CONS_CASING, 'line-width', casing['line-width']);
    map.setPaintProperty(CONS_CASING, 'line-opacity', casing['line-opacity']);
  }
  if (map.getLayer(CONS_LINE)) {
    const paint = consorcioPaint(selectedId);
    map.setPaintProperty(CONS_LINE, 'line-color', paint['line-color']);
    map.setPaintProperty(CONS_LINE, 'line-width', paint['line-width']);
    map.setPaintProperty(CONS_LINE, 'line-opacity', paint['line-opacity']);
  }
}

function extendLineBounds(bounds: maplibregl.LngLatBounds, geometry: CanalLineGeometry): void {
  if (geometry.type === 'LineString') {
    for (const coord of geometry.coordinates) {
      bounds.extend(coord as [number, number]);
    }
    return;
  }
  for (const line of geometry.coordinates) {
    for (const coord of line) {
      bounds.extend(coord as [number, number]);
    }
  }
}

function featureById(
  collection: CanalLineCollection,
  id: string
): Feature<LineString | MultiLineString> | undefined {
  return collection.features.find((item) => item.id === id || item.properties?.id === id);
}

function queryCanalHits(map: maplibregl.Map, point: { x: number; y: number }): CanalHit[] {
  // ±8px bbox around the click point. 2D nadir lines are thin too;
  // MapLibre still returns features in z-order within the bbox
  // (top-most first).
  const bbox = clickBbox(point);
  const layers = Object.values(ADMIN_CANAL_LINE_LAYER_ID).filter((layerId) =>
    Boolean(map.getLayer(layerId))
  );
  if (layers.length === 0) return [];
  return collectCanalHits(
    map.queryRenderedFeatures(bbox, { layers }).map((feature) => ({
      layerId: feature.layer.id,
      properties: (feature.properties ?? null) as Record<string, unknown> | null,
    }))
  );
}

export function CanalesPublicacionMap({
  consorcio,
  existentes,
  srPa,
  showRelevados,
  showPropuestas,
  showAprhi,
  showExistentes,
  selectedId,
  onSelect,
  onOverlapHits,
}: {
  consorcio: CanalLineCollection;
  existentes: CanalLineCollection | null;
  srPa: FeatureCollection | null;
  showRelevados: boolean;
  showPropuestas: boolean;
  showAprhi: boolean;
  showExistentes: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOverlapHits: (hits: CanalHit[]) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const onSelectRef = useRef(onSelect);
  const onOverlapHitsRef = useRef(onOverlapHits);
  const consorcioRef = useRef(consorcio);
  const existentesRef = useRef(existentes);
  const srPaRef = useRef(srPa);
  const showAprhiRef = useRef(showAprhi);
  const showExistentesRef = useRef(showExistentes);
  const showRelevadosRef = useRef(showRelevados);
  const showPropuestasRef = useRef(showPropuestas);
  const selectedIdRef = useRef(selectedId);
  const fittedIdRef = useRef<string | null>(null);
  onSelectRef.current = onSelect;
  onOverlapHitsRef.current = onOverlapHits;
  consorcioRef.current = consorcio;
  existentesRef.current = existentes;
  srPaRef.current = srPa;
  showAprhiRef.current = showAprhi;
  showExistentesRef.current = showExistentes;
  showRelevadosRef.current = showRelevados;
  showPropuestasRef.current = showPropuestas;
  selectedIdRef.current = selectedId;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        glyphs: MAP_GLYPHS_URL,
        sources: {
          satellite: {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: '&copy; Esri',
          },
        },
        layers: [{ id: 'satellite', type: 'raster', source: 'satellite' }],
      },
      center: [MAP_CENTER[1], MAP_CENTER[0]],
      zoom: 11,
      minZoom: MAP_MIN_ZOOM,
      maxBounds: MAP_MAX_BOUNDS,
    });
    mapRef.current = map;

    map.on('load', () => {
      void fetch('/capas/zona.geojson')
        .then((res) => (res.ok ? res.json() : null))
        .then((zona: FeatureCollection | null) => {
          if (!zona || !map.getStyle()) return;
          map.addSource(ZONA_SRC, { type: 'geojson', data: zona });
          map.addLayer({
            id: 'pub-zona-fill',
            type: 'fill',
            source: ZONA_SRC,
            paint: { 'fill-color': '#ef4444', 'fill-opacity': 0.06 },
          });
          map.addLayer({
            id: 'pub-zona-line',
            type: 'line',
            source: ZONA_SRC,
            paint: { 'line-color': '#ef4444', 'line-width': 2, 'line-opacity': 0.9 },
          });
        })
        .catch(() => undefined);

      const kmzVisible = kmzGroupVisible(showRelevadosRef.current, showPropuestasRef.current);

      map.addSource(SR_SRC, { type: 'geojson', data: EMPTY_LINE_COLLECTION });
      const initialSrPa = srPaPaint(selectedIdRef.current, kmzVisible);
      map.addLayer({
        id: SR_LINE,
        type: 'line',
        source: SR_SRC,
        layout: { visibility: showAprhiRef.current ? 'visible' : 'none' },
        paint: {
          'line-color': initialSrPa['line-color'],
          'line-width': initialSrPa['line-width'],
          'line-opacity': initialSrPa['line-opacity'],
          'line-offset': initialSrPa['line-offset'],
          'line-dasharray': [3, 2],
        },
      });
      map.addLayer({
        id: SR_LABEL,
        type: 'symbol',
        source: SR_SRC,
        minzoom: 11,
        layout: {
          visibility: overlayLabelsVisible(showAprhiRef.current, kmzVisible) ? 'visible' : 'none',
          'symbol-placement': 'line',
          'symbol-spacing': 240,
          'text-field': [
            'concat',
            ['coalesce', ['get', 'Identificador'], ''],
            ' · ',
            ['coalesce', ['get', 'Nombre_Obra'], ''],
          ],
          'text-font': ['Noto Sans Regular'],
          'text-size': 12,
          'text-keep-upright': true,
        },
        paint: {
          'text-color': '#ffedd5',
          'text-halo-color': 'rgba(0,0,0,0.75)',
          'text-halo-width': 1.2,
        },
      });

      map.addSource(EXISTENTES_SRC, { type: 'geojson', data: EMPTY_LINE_COLLECTION });
      const initialExistentes = existentesPaint(selectedIdRef.current, kmzVisible);
      map.addLayer({
        id: EXISTENTES_LINE,
        type: 'line',
        source: EXISTENTES_SRC,
        paint: {
          'line-color': initialExistentes['line-color'],
          'line-width': initialExistentes['line-width'],
          'line-opacity': initialExistentes['line-opacity'],
          'line-offset': initialExistentes['line-offset'],
          'line-dasharray': [2, 2],
        },
      });
      map.addLayer({
        id: EXISTENTES_LABEL,
        type: 'symbol',
        source: EXISTENTES_SRC,
        minzoom: 12,
        layout: {
          visibility: overlayLabelsVisible(showExistentesRef.current, kmzVisible)
            ? 'visible'
            : 'none',
          'symbol-placement': 'line',
          'symbol-spacing': 280,
          'text-field': ['concat', 'Existentes · ', ['get', 'nombre_publico']],
          'text-font': ['Noto Sans Regular'],
          'text-size': 11,
          'text-keep-upright': true,
        },
        paint: {
          'text-color': '#ddd6fe',
          'text-halo-color': 'rgba(0,0,0,0.75)',
          'text-halo-width': 1.2,
        },
      });

      map.addSource(CONS_SRC, { type: 'geojson', data: EMPTY_LINE_COLLECTION });
      const casing = consorcioCasingPaint(selectedIdRef.current);
      map.addLayer({
        id: CONS_CASING,
        type: 'line',
        source: CONS_SRC,
        layout: { 'line-cap': 'round' },
        paint: {
          'line-color': casing['line-color'],
          'line-width': casing['line-width'],
          'line-opacity': casing['line-opacity'],
        },
      });
      const paint = consorcioPaint(selectedIdRef.current);
      map.addLayer({
        id: CONS_LINE,
        type: 'line',
        source: CONS_SRC,
        paint,
      });
      map.addLayer({
        id: CONS_LABEL,
        type: 'symbol',
        source: CONS_SRC,
        minzoom: 11,
        layout: {
          'symbol-placement': 'line',
          'symbol-spacing': 220,
          'text-field': ['get', 'nombre_publico'],
          'text-font': ['Noto Sans Regular'],
          'text-size': 14,
          'text-keep-upright': true,
        },
        paint: {
          'text-color': '#ffffff',
          'text-halo-color': 'rgba(0,0,0,0.75)',
          'text-halo-width': 1.4,
        },
      });

      applyLineSource(map, CONS_SRC, consorcioRef.current);
      applyConsorcioFilter(map, showRelevadosRef.current, showPropuestasRef.current);
      applyLineSource(
        map,
        EXISTENTES_SRC,
        showExistentesRef.current && existentesRef.current
          ? existentesRef.current
          : EMPTY_LINE_COLLECTION
      );
      applyLineSource(
        map,
        SR_SRC,
        showAprhiRef.current && srPaRef.current ? srPaRef.current : EMPTY_LINE_COLLECTION
      );

      map.on('click', (event) => {
        const hits = queryCanalHits(map, event.point);
        if (hits.length === 0) {
          onOverlapHitsRef.current([]);
          return;
        }
        if (hits.length === 1) {
          onSelectRef.current(hits[0].id);
          onOverlapHitsRef.current([]);
          return;
        }
        onOverlapHitsRef.current(hits);
        const picked = pickDefaultHit(hits);
        if (picked) onSelectRef.current(picked.id);
      });
      map.on('mouseenter', CONS_LINE, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', CONS_LINE, () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('mouseenter', EXISTENTES_LINE, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', EXISTENTES_LINE, () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('mouseenter', SR_LINE, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', SR_LINE, () => {
        map.getCanvas().style.cursor = '';
      });
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    applyLineSource(map, CONS_SRC, consorcio);
    applyConsorcioFilter(map, showRelevados, showPropuestas);
  }, [consorcio, showRelevados, showPropuestas]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    applyLineSource(
      map,
      EXISTENTES_SRC,
      showExistentes && existentes ? existentes : EMPTY_LINE_COLLECTION
    );
  }, [existentes, showExistentes]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (map.getLayer(SR_LINE)) {
      map.setLayoutProperty(SR_LINE, 'visibility', showAprhi ? 'visible' : 'none');
    }
    applyLineSource(map, SR_SRC, showAprhi && srPa ? srPa : EMPTY_LINE_COLLECTION);
  }, [showAprhi, srPa]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const kmzVisible = kmzGroupVisible(showRelevados, showPropuestas);
    applyOverlayPaint(map, selectedId, kmzVisible);
    applyOverlayLabelVisibility(map, showAprhi, showExistentes, kmzVisible);
  }, [selectedId, showRelevados, showPropuestas, showAprhi, showExistentes]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    applyConsorcioPaint(map, selectedId);
    applyOverlayPaint(
      map,
      selectedId,
      kmzGroupVisible(showRelevadosRef.current, showPropuestasRef.current)
    );
    if (!selectedId || fittedIdRef.current === selectedId) return;
    const feature =
      featureById(consorcio, selectedId) ??
      (existentes ? featureById(existentes, selectedId) : undefined) ??
      (srPa && isSrPaListId(selectedId) ? srPaFeatureById(srPa, selectedId) : undefined);
    const geometry = feature?.geometry;
    if (geometry?.type !== 'LineString' && geometry?.type !== 'MultiLineString') return;
    const bounds = new maplibregl.LngLatBounds();
    extendLineBounds(bounds, geometry);
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 80, maxZoom: 14, duration: 400 });
      fittedIdRef.current = selectedId;
    }
  }, [selectedId, consorcio, existentes, srPa]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 480 }} />;
}

export function patchConsorcioFeature(
  collection: FeatureCollection,
  id: string,
  patch: { publicado?: boolean; nombre_publico?: string }
): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: collection.features.map((feature) => {
      const featureId = String(feature.id ?? feature.properties?.id ?? '');
      if (featureId !== id) return feature;
      return {
        ...feature,
        properties: {
          ...feature.properties,
          ...(patch.publicado != null ? { publicado: patch.publicado } : {}),
          ...(patch.nombre_publico != null ? { nombre_publico: patch.nombre_publico } : {}),
        },
      };
    }),
  };
}
