/**
 * DrawControl — polygon draw control for MapLibre GL maps.
 *
 * Replaces the leaflet-draw implementation with @mapbox/mapbox-gl-draw.
 * External interface (DrawControlHandle, DrawnPolygon, DrawControlProps) is
 * UNCHANGED so callers don't need any updates.
 *
 * NOTE: This component does NOT mount into the React tree — it wires into a
 * MapLibre map instance imperatively via the `map` prop.  It renders null.
 * It will be used inside MapaMapLibre.tsx (Phase 2).  MapaLeaflet.tsx still
 * uses the old Leaflet-based DrawControl until Phase 5 cleanup.
 */

import MapboxDraw from '@mapbox/mapbox-gl-draw';
import type maplibregl from 'maplibre-gl';
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { ensureMapboxDrawCompatibility } from './mapboxDrawCompatibility';
import { removeMapboxDrawArtifacts } from './mapboxDrawShared';

// ─── Public types (same as before) ───────────────────────────────────────────

export interface DrawnPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface DrawControlHandle {
  startDrawing: () => void;
  clearDrawing: () => void;
}

interface DrawControlProps {
  readonly map: maplibregl.Map;
  readonly onPolygonCreated: (geometry: DrawnPolygon) => void;
  readonly onPolygonDeleted: () => void;
  /** When false the draw toolbar is not added to the map (role gate for ciudadano). */
  readonly showControls?: boolean;
}

// ─── Component ────────────────────────────────────────────────────────────────

const DrawControl = forwardRef<DrawControlHandle, DrawControlProps>(
  ({ map, onPolygonCreated, onPolygonDeleted, showControls = false }, ref) => {
    const drawRef = useRef<MapboxDraw | null>(null);

    // Stable callbacks via ref so the effect doesn't re-run on every render
    const onPolygonCreatedRef = useRef(onPolygonCreated);
    const onPolygonDeletedRef = useRef(onPolygonDeleted);
    onPolygonCreatedRef.current = onPolygonCreated;
    onPolygonDeletedRef.current = onPolygonDeleted;

    useImperativeHandle(ref, () => ({
      startDrawing: () => {
        drawRef.current?.changeMode('draw_polygon');
      },
      clearDrawing: () => {
        drawRef.current?.deleteAll();
        onPolygonDeletedRef.current();
      },
    }));

    useEffect(() => {
      ensureMapboxDrawCompatibility(map);

      const draw = new MapboxDraw({
        displayControlsDefault: false,
        controls: showControls
          ? { polygon: true, trash: true }
          : undefined,
        defaultMode: 'simple_select',
        styles: [
          // Polygon fill (active)
          {
            id: 'gl-draw-polygon-fill',
            type: 'fill',
            filter: ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
            paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.2 },
          },
          // Polygon outline (active)
          {
            id: 'gl-draw-polygon-stroke-active',
            type: 'line',
            filter: ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
            paint: { 'line-color': '#3b82f6', 'line-width': 3 },
          },
          // Vertex points
          {
            id: 'gl-draw-polygon-and-line-vertex-active',
            type: 'circle',
            filter: ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point']],
            paint: { 'circle-radius': 5, 'circle-color': '#3b82f6' },
          },
        ],
      });

      drawRef.current = draw;

      // Before adding the control, remove any stale Draw sources/layers that may
      // linger after WebGL context loss+restore (MapboxDraw re-fires its setup on
      // every map 'load' event, causing "source already exists" on context restore).
      removeMapboxDrawArtifacts(map);

      // MapboxDraw is compatible with maplibre-gl maps — it targets the same GL API
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      map.addControl(draw as unknown as maplibregl.IControl);

      const handleCreate = () => {
        const all = draw.getAll();
        const polygon = all.features.find((f) => f.geometry.type === 'Polygon');
        if (!polygon || polygon.geometry.type !== 'Polygon') return;
        // Keep only the most-recently drawn polygon
        const idsToRemove = all.features
          .filter((f) => f.id !== polygon.id)
          .map((f) => f.id as string);
        if (idsToRemove.length > 0) draw.delete(idsToRemove);
        onPolygonCreatedRef.current({
          type: 'Polygon',
          coordinates: polygon.geometry.coordinates as number[][][],
        });
      };

      const handleDelete = () => {
        onPolygonDeletedRef.current();
      };

      const handleUpdate = () => {
        const all = draw.getAll();
        const polygon = all.features.find((f) => f.geometry.type === 'Polygon');
        if (!polygon || polygon.geometry.type !== 'Polygon') return;
        onPolygonCreatedRef.current({
          type: 'Polygon',
          coordinates: polygon.geometry.coordinates as number[][][],
        });
      };

      const handleContextLost = () => {
        removeMapboxDrawArtifacts(map);
      };

      map.on('draw.create', handleCreate);
      map.on('draw.delete', handleDelete);
      map.on('draw.update', handleUpdate);
      map.on('webglcontextlost', handleContextLost);

      return () => {
        map.off('draw.create', handleCreate);
        map.off('draw.delete', handleDelete);
        map.off('draw.update', handleUpdate);
        map.off('webglcontextlost', handleContextLost);
        if (map.hasControl(draw as unknown as maplibregl.IControl)) {
          map.removeControl(draw as unknown as maplibregl.IControl);
        }
        removeMapboxDrawArtifacts(map);
        drawRef.current = null;
      };
    }, [map, showControls]);

    return null;
  },
);

DrawControl.displayName = 'DrawControl';

export default DrawControl;
