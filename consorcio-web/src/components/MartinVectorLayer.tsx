/**
 * MartinVectorLayer - Renders a Martin MVT source as a Leaflet vectorGrid layer.
 *
 * Uses leaflet.vectorgrid to consume protobuf MVT tiles from Martin.
 * Supports dynamic per-feature styling (e.g., flood risk colors per zona).
 */

import L from 'leaflet';
import 'leaflet.vectorgrid';
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';

interface StyleDef {
  fill?: boolean;
  color?: string;
  fillColor?: string;
  fillOpacity?: number;
  weight?: number;
  opacity?: number;
  radius?: number;
}

interface MartinVectorLayerProps {
  /** Full MVT URL template, e.g. http://localhost:3000/puntos_conflicto/{z}/{x}/{y} */
  tileUrl: string;
  /** Martin table name — used as the layer name in vectorgrid */
  layerName: string;
  /** Base style for all features */
  style: StyleDef;
  /** Optional per-feature style override — receives properties, returns partial style */
  featureStyle?: (properties: Record<string, unknown>) => Partial<StyleDef>;
  /** Leaflet pane name */
  pane?: string;
  /** Min zoom to start showing tiles */
  minZoom?: number;
  maxZoom?: number;
  maxNativeZoom?: number;
}

export default function MartinVectorLayer({
  tileUrl,
  layerName,
  style,
  featureStyle,
  pane = 'vectorOverlayPane',
  minZoom = 8,
  maxZoom = 18,
  maxNativeZoom = 16,
}: MartinVectorLayerProps) {
  const map = useMap();
  const layerRef = useRef<L.Layer | null>(null);

  useEffect(() => {
    // Remove previous layer instance when props change
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vg = (L as any).vectorGrid;
    if (!vg?.protobuf) {
      console.warn('leaflet.vectorgrid not loaded');
      return;
    }

    const vectorStyles: Record<string, StyleDef | ((props: Record<string, unknown>) => StyleDef)> = {
      [layerName]: featureStyle
        ? (props: Record<string, unknown>) => ({ ...style, ...featureStyle(props) })
        : style,
    };

    const layer = vg.protobuf(tileUrl, {
      vectorTileLayerStyles: vectorStyles,
      interactive: false,
      pane,
      minZoom,
      maxZoom,
      maxNativeZoom,
    });

    layer.addTo(map);
    layerRef.current = layer;

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [tileUrl, layerName, style, featureStyle, pane, minZoom, maxZoom, maxNativeZoom, map]);

  return null;
}
