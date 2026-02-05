import L from 'leaflet';
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { useMap } from 'react-leaflet';
import 'leaflet-draw';
import 'leaflet-draw/dist/leaflet.draw.css';

export interface DrawnPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface DrawControlHandle {
  startDrawing: () => void;
  clearDrawing: () => void;
}

interface DrawControlProps {
  readonly onPolygonCreated: (geometry: DrawnPolygon) => void;
  readonly onPolygonDeleted: () => void;
  readonly showControls?: boolean;
}

const DrawControl = forwardRef<DrawControlHandle, DrawControlProps>(
  ({ onPolygonCreated, onPolygonDeleted, showControls = false }, ref) => {
    const map = useMap();
    const drawnItemsRef = useRef<L.FeatureGroup | null>(null);
    const drawControlRef = useRef<L.Control.Draw | null>(null);
    const polygonDrawerRef = useRef<L.Draw.Polygon | null>(null);

    useImperativeHandle(ref, () => ({
      startDrawing: () => {
        if (polygonDrawerRef.current) {
          polygonDrawerRef.current.disable();
        }
        // Cast map to DrawMap for leaflet-draw compatibility
        polygonDrawerRef.current = new L.Draw.Polygon(map as L.DrawMap, {
          allowIntersection: false,
          showArea: true,
          shapeOptions: {
            color: '#3b82f6',
            weight: 3,
            fillOpacity: 0.2,
          },
        });
        polygonDrawerRef.current.enable();
      },
      clearDrawing: () => {
        if (drawnItemsRef.current) {
          drawnItemsRef.current.clearLayers();
        }
        if (polygonDrawerRef.current) {
          polygonDrawerRef.current.disable();
          polygonDrawerRef.current = null;
        }
        onPolygonDeleted();
      },
    }));

    useEffect(() => {
      // Create feature group for drawn items
      const drawnItems = new L.FeatureGroup();
      drawnItemsRef.current = drawnItems;
      map.addLayer(drawnItems);

      // Only add visual controls if showControls is true
      if (showControls) {
        const drawControl = new L.Control.Draw({
          position: 'topleft',
          draw: {
            polygon: {
              allowIntersection: false,
              showArea: true,
              shapeOptions: {
                color: '#3b82f6',
                weight: 3,
                fillOpacity: 0.2,
              },
            },
            rectangle: {
              shapeOptions: {
                color: '#3b82f6',
                weight: 3,
                fillOpacity: 0.2,
              },
            },
            polyline: false,
            circle: false,
            circlemarker: false,
            marker: false,
          },
          edit: {
            featureGroup: drawnItems,
            remove: true,
          },
        });

        drawControlRef.current = drawControl;
        map.addControl(drawControl);
      }

      // Handle polygon creation
      const handleCreated = (e: L.LeafletEvent) => {
        const event = e as L.DrawEvents.Created;
        const layer = event.layer;

        // Remove previous polygon if exists
        drawnItems.clearLayers();

        // Add new polygon
        drawnItems.addLayer(layer);

        // Reset drawer reference
        if (polygonDrawerRef.current) {
          polygonDrawerRef.current = null;
        }

        // Convert to GeoJSON
        const geoJson = (layer as L.Polygon).toGeoJSON();
        const geometry: DrawnPolygon = {
          type: 'Polygon',
          coordinates: geoJson.geometry.coordinates as number[][][],
        };

        onPolygonCreated(geometry);
      };

      // Handle polygon deletion
      const handleDeleted = () => {
        onPolygonDeleted();
      };

      // Handle polygon edit
      const handleEdited = (e: L.LeafletEvent) => {
        const event = e as L.DrawEvents.Edited;
        const layers = event.layers;

        layers.eachLayer((layer) => {
          const geoJson = (layer as L.Polygon).toGeoJSON();
          const geometry: DrawnPolygon = {
            type: 'Polygon',
            coordinates: geoJson.geometry.coordinates as number[][][],
          };
          onPolygonCreated(geometry);
        });
      };

      map.on(L.Draw.Event.CREATED, handleCreated);
      map.on(L.Draw.Event.DELETED, handleDeleted);
      map.on(L.Draw.Event.EDITED, handleEdited);

      // Cleanup
      return () => {
        map.off(L.Draw.Event.CREATED, handleCreated);
        map.off(L.Draw.Event.DELETED, handleDeleted);
        map.off(L.Draw.Event.EDITED, handleEdited);

        if (polygonDrawerRef.current) {
          polygonDrawerRef.current.disable();
        }
        if (drawControlRef.current) {
          map.removeControl(drawControlRef.current);
        }
        if (drawnItemsRef.current) {
          map.removeLayer(drawnItemsRef.current);
        }
      };
    }, [map, onPolygonCreated, onPolygonDeleted, showControls]);

    return null;
  }
);

DrawControl.displayName = 'DrawControl';

export default DrawControl;
