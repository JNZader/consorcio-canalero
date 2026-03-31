import L from 'leaflet';
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import 'leaflet-draw';
import 'leaflet-draw/dist/leaflet.draw.css';

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
  readonly value: DrawnLineFeatureCollection | null;
  readonly onChange: (geometry: DrawnLineFeatureCollection | null) => void;
}

function layerToFeature(layer: L.Layer) {
  const geoJson = (layer as L.Polyline).toGeoJSON() as GeoJSON.Feature<GeoJSON.LineString>;
  return {
    type: 'Feature' as const,
    geometry: {
      type: 'LineString' as const,
      coordinates: geoJson.geometry.coordinates as number[][],
    },
    properties: {},
  };
}

export default function LineDrawControl({ value, onChange }: LineDrawControlProps) {
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
          shapeOptions: {
            color: '#0B3D91',
            weight: 4,
            opacity: 0.95,
          },
        },
      },
      edit: {
        featureGroup: drawnItems,
        remove: true,
      },
    });

    drawControlRef.current = drawControl;
    map.addControl(drawControl);

    const emitCurrent = () => {
      const layers = drawnItems.getLayers();
      if (layers.length === 0) {
        onChange(null);
        return;
      }
      onChange({
        type: 'FeatureCollection',
        features: layers.map(layerToFeature),
      });
    };

    const handleCreated = (e: L.LeafletEvent) => {
      const event = e as L.DrawEvents.Created;
      drawnItems.addLayer(event.layer);
      emitCurrent();
    };

    const handleEdited = () => emitCurrent();
    const handleDeleted = () => emitCurrent();

    map.on(L.Draw.Event.CREATED, handleCreated);
    map.on(L.Draw.Event.EDITED, handleEdited);
    map.on(L.Draw.Event.DELETED, handleDeleted);

    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated);
      map.off(L.Draw.Event.EDITED, handleEdited);
      map.off(L.Draw.Event.DELETED, handleDeleted);
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
      drawnItems.addLayer(
        L.polyline(latLngs, {
          color: '#0B3D91',
          weight: 4,
          opacity: 0.95,
        }),
      );
    }
  }, [value]);

  return null;
}
