/**
 * LineDrawControl — polyline draw control.
 *
 * Supports two rendering modes:
 *  - MapLibre mode: pass `map` prop (maplibregl.Map instance) — uses @mapbox/mapbox-gl-draw
 *  - Leaflet mode:  omit `map` prop — uses the original leaflet-draw implementation
 *    (still needed by FormularioSugerencia.tsx until Phase 5 cleanup)
 *
 * External interface (DrawnLineFeatureCollection, LineDrawControlProps) is UNCHANGED.
 */

// ─── Public types (same as before) ───────────────────────────────────────────

export interface DrawnLineFeatureCollection {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry: {
      type: 'LineString';
      coordinates: number[][];
    };
    properties: Record<string, never>;
  }>;
}

interface LineDrawControlProps {
  /** MapLibre map instance.  When provided, uses @mapbox/mapbox-gl-draw.
   *  When omitted, falls back to the leaflet-draw implementation (Leaflet context required). */
  readonly map?: import('maplibre-gl').Map;
  readonly value: DrawnLineFeatureCollection | null;
  readonly onChange: (geometry: DrawnLineFeatureCollection | null) => void;
}

// ─── MapLibre implementation ──────────────────────────────────────────────────

import MapboxDraw from '@mapbox/mapbox-gl-draw';
import { useEffect, useRef } from 'react';

function MapLibreLineDrawControl({
  map,
  value,
  onChange,
}: Required<Pick<LineDrawControlProps, 'map'>> & Omit<LineDrawControlProps, 'map'>) {
  const drawRef = useRef<MapboxDraw | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    const draw = new MapboxDraw({
      displayControlsDefault: false,
      controls: { line_string: true, trash: true },
      defaultMode: 'simple_select',
      styles: [
        {
          id: 'gl-draw-line-active',
          type: 'line',
          filter: ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
          paint: { 'line-color': '#0B3D91', 'line-width': 4, 'line-opacity': 0.95 },
        },
        {
          id: 'gl-draw-line-vertex',
          type: 'circle',
          filter: ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point']],
          paint: { 'circle-radius': 4, 'circle-color': '#0B3D91' },
        },
      ],
    });

    drawRef.current = draw;
    // MapboxDraw targets the same GL API as maplibre-gl
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    map.addControl(draw as unknown as import('maplibre-gl').IControl);

    const emitCurrent = () => {
      const all = draw.getAll();
      const lines = all.features.filter((f) => f.geometry.type === 'LineString');
      if (lines.length === 0) {
        onChangeRef.current(null);
        return;
      }
      onChangeRef.current({
        type: 'FeatureCollection',
        features: lines.map((f) => ({
          type: 'Feature' as const,
          geometry: {
            type: 'LineString' as const,
            coordinates: (f.geometry as GeoJSON.LineString).coordinates as number[][],
          },
          properties: {} as Record<string, never>,
        })),
      });
    };

    map.on('draw.create', emitCurrent);
    map.on('draw.update', emitCurrent);
    map.on('draw.delete', emitCurrent);

    return () => {
      map.off('draw.create', emitCurrent);
      map.off('draw.update', emitCurrent);
      map.off('draw.delete', emitCurrent);
      if (map.hasControl(draw as unknown as import('maplibre-gl').IControl)) {
        map.removeControl(draw as unknown as import('maplibre-gl').IControl);
      }
      drawRef.current = null;
    };
  }, [map]);

  // Sync external value → draw control (controlled component pattern)
  useEffect(() => {
    const draw = drawRef.current;
    if (!draw) return;
    draw.deleteAll();
    for (const feature of value?.features ?? []) {
      if (feature.geometry.type !== 'LineString') continue;
      draw.add({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: feature.geometry.coordinates },
        properties: {},
      });
    }
  }, [value]);

  return null;
}

// ─── Leaflet fallback implementation ─────────────────────────────────────────

import L from 'leaflet';
import { useMap } from 'react-leaflet';
import 'leaflet-draw';
import 'leaflet-draw/dist/leaflet.draw.css';

function layerToFeature(layer: L.Layer) {
  const geoJson = (layer as L.Polyline).toGeoJSON() as GeoJSON.Feature<GeoJSON.LineString>;
  return {
    type: 'Feature' as const,
    geometry: {
      type: 'LineString' as const,
      coordinates: geoJson.geometry.coordinates as number[][],
    },
    properties: {} as Record<string, never>,
  };
}

function LeafletLineDrawControl({ value, onChange }: Omit<LineDrawControlProps, 'map'>) {
  const map = useMap();
  const drawnItemsRef = useRef<L.FeatureGroup | null>(null);
  const drawControlRef = useRef<L.Control.Draw | null>(null);

  useEffect(() => {
    const drawnItems = new L.FeatureGroup();
    drawnItemsRef.current = drawnItems;
    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({
      position: 'topleft',
      draw: {
        polygon: false,
        rectangle: false,
        circle: false,
        circlemarker: false,
        marker: false,
        polyline: {
          shapeOptions: { color: '#0B3D91', weight: 4, opacity: 0.95 },
        },
      },
      edit: { featureGroup: drawnItems, remove: true },
    });

    drawControlRef.current = drawControl;
    map.addControl(drawControl);

    const emitCurrent = () => {
      const layers = drawnItems.getLayers();
      if (layers.length === 0) {
        onChange(null);
        return;
      }
      onChange({ type: 'FeatureCollection', features: layers.map(layerToFeature) });
    };

    const handleCreated = (e: L.LeafletEvent) => {
      const event = e as L.DrawEvents.Created;
      drawnItems.addLayer(event.layer);
      emitCurrent();
    };

    map.on(L.Draw.Event.CREATED, handleCreated);
    map.on(L.Draw.Event.EDITED, emitCurrent);
    map.on(L.Draw.Event.DELETED, emitCurrent);

    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated);
      map.off(L.Draw.Event.EDITED, emitCurrent);
      map.off(L.Draw.Event.DELETED, emitCurrent);
      if (drawControlRef.current) map.removeControl(drawControlRef.current);
      if (drawnItemsRef.current) map.removeLayer(drawnItemsRef.current);
    };
  }, [map, onChange]);

  useEffect(() => {
    const drawnItems = drawnItemsRef.current;
    if (!drawnItems) return;
    drawnItems.clearLayers();
    for (const feature of value?.features ?? []) {
      if (feature.geometry.type !== 'LineString') continue;
      const latLngs = feature.geometry.coordinates.map(([lng, lat]) => L.latLng(lat, lng));
      drawnItems.addLayer(L.polyline(latLngs, { color: '#0B3D91', weight: 4, opacity: 0.95 }));
    }
  }, [value]);

  return null;
}

// ─── Unified export ───────────────────────────────────────────────────────────

export default function LineDrawControl({ map, value, onChange }: LineDrawControlProps) {
  if (map) {
    return <MapLibreLineDrawControl map={map} value={value} onChange={onChange} />;
  }
  return <LeafletLineDrawControl value={value} onChange={onChange} />;
}
