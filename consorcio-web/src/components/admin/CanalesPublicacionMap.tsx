import type { Feature, FeatureCollection, LineString } from 'geojson';
import maplibregl, { type DataDrivenPropertyValueSpecification } from 'maplibre-gl';
import { useEffect, useRef } from 'react';
import 'maplibre-gl/dist/maplibre-gl.css';

import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { MAP_GLYPHS_URL } from '../map2d/roadLabelLayer';

const CONS_SRC = 'pub-consorcio';
const APRHI_SRC = 'pub-aprhi';
const ZONA_SRC = 'pub-zona';
const CONS_LINE = 'pub-cons-line';
const APRHI_LINE = 'pub-aprhi-line';

export const EMPTY_LINE_COLLECTION: FeatureCollection<LineString> = {
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

function applyLineSource(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection<LineString>
): void {
  const source = map.getSource(sourceId);
  if (source) {
    (source as maplibregl.GeoJSONSource).setData(data);
  }
}

export function CanalesPublicacionMap({
  consorcio,
  aprhi,
  showAprhi,
  selectedId,
  onSelect,
}: {
  consorcio: FeatureCollection<LineString>;
  aprhi: FeatureCollection<LineString> | null;
  showAprhi: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const onSelectRef = useRef(onSelect);
  const consorcioRef = useRef(consorcio);
  const aprhiRef = useRef(aprhi);
  const showAprhiRef = useRef(showAprhi);
  const selectedIdRef = useRef(selectedId);
  const fittedIdRef = useRef<string | null>(null);
  onSelectRef.current = onSelect;
  consorcioRef.current = consorcio;
  aprhiRef.current = aprhi;
  showAprhiRef.current = showAprhi;
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
    let aprhiPopup: maplibregl.Popup | null = null;

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

      map.addSource(APRHI_SRC, { type: 'geojson', data: EMPTY_LINE_COLLECTION });
      map.addLayer({
        id: APRHI_LINE,
        type: 'line',
        source: APRHI_SRC,
        paint: {
          'line-color': '#ea580c',
          'line-width': 2,
          'line-opacity': 0.8,
          'line-dasharray': [3, 2],
        },
      });
      map.addLayer({
        id: 'pub-aprhi-label',
        type: 'symbol',
        source: APRHI_SRC,
        minzoom: 12,
        layout: {
          'symbol-placement': 'line',
          'symbol-spacing': 280,
          'text-field': ['concat', 'APRHI · ', ['get', 'nombre']],
          'text-font': ['Noto Sans Regular'],
          'text-size': 11,
          'text-keep-upright': true,
        },
        paint: {
          'text-color': '#fed7aa',
          'text-halo-color': 'rgba(0,0,0,0.75)',
          'text-halo-width': 1.2,
        },
      });

      map.addSource(CONS_SRC, { type: 'geojson', data: EMPTY_LINE_COLLECTION });
      const paint = consorcioPaint(selectedIdRef.current);
      map.addLayer({
        id: CONS_LINE,
        type: 'line',
        source: CONS_SRC,
        paint,
      });
      map.addLayer({
        id: 'pub-cons-label',
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
      applyLineSource(
        map,
        APRHI_SRC,
        showAprhiRef.current && aprhiRef.current ? aprhiRef.current : EMPTY_LINE_COLLECTION
      );

      map.on('click', CONS_LINE, (event) => {
        const feature = event.features?.[0];
        const id = feature?.properties?.id;
        if (typeof id === 'string') onSelectRef.current(id);
      });
      map.on('click', APRHI_LINE, (event) => {
        const raw = event.features?.[0]?.properties?.nombre;
        const nombre = typeof raw === 'string' && raw.trim() ? raw.trim() : 'sin nombre APRHI';
        aprhiPopup?.remove();
        aprhiPopup = new maplibregl.Popup({ closeButton: true, offset: 8 })
          .setLngLat(event.lngLat)
          .setText(`APRHI (referencia) · ${nombre}`)
          .addTo(map);
      });
      map.on('mouseenter', CONS_LINE, () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', CONS_LINE, () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('mouseenter', APRHI_LINE, () => {
        map.getCanvas().style.cursor = 'help';
      });
      map.on('mouseleave', APRHI_LINE, () => {
        if (map.getCanvas().style.cursor === 'help') {
          map.getCanvas().style.cursor = '';
        }
      });
    });
    return () => {
      aprhiPopup?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    applyLineSource(map, CONS_SRC, consorcio);
  }, [consorcio]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    applyLineSource(
      map,
      APRHI_SRC,
      showAprhi && aprhi ? aprhi : EMPTY_LINE_COLLECTION
    );
  }, [aprhi, showAprhi]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer(CONS_LINE)) return;
    const paint = consorcioPaint(selectedId);
    map.setPaintProperty(CONS_LINE, 'line-color', paint['line-color']);
    map.setPaintProperty(CONS_LINE, 'line-width', paint['line-width']);
    map.setPaintProperty(CONS_LINE, 'line-opacity', paint['line-opacity']);
    if (!selectedId || fittedIdRef.current === selectedId) return;
    const feature = consorcio.features.find(
      (item) => item.id === selectedId || item.properties?.id === selectedId
    );
    if (!feature || feature.geometry.type !== 'LineString') return;
    const bounds = new maplibregl.LngLatBounds();
    for (const coord of feature.geometry.coordinates) {
      bounds.extend(coord as [number, number]);
    }
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 80, maxZoom: 14, duration: 400 });
      fittedIdRef.current = selectedId;
    }
  }, [selectedId, consorcio]);

  return <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 480 }} />;
}

export function patchConsorcioFeature(
  collection: FeatureCollection<LineString>,
  id: string,
  patch: { publicado?: boolean; nombre_publico?: string }
): FeatureCollection<LineString> {
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
      } as Feature<LineString>;
    }),
  };
}
