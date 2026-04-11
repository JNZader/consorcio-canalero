import type { Feature } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { useEffect } from 'react';
import { SOURCE_IDS } from './map2dConfig';

interface UseMapInteractionEffectsParams {
  mapRef: React.RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  markingMode: boolean;
  setNewPoint: (value: { lat: number; lng: number } | null) => void;
  setSelectedFeature: (value: Feature | null) => void;
  showSuggestedZonesPanel: boolean;
  setSelectedDraftBasinId: (value: string | null) => void;
}

export function useMapInteractionEffects({
  mapRef,
  mapReady,
  markingMode,
  setNewPoint,
  setSelectedFeature,
  showSuggestedZonesPanel,
  setSelectedDraftBasinId,
}: UseMapInteractionEffectsParams) {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const clickableLayers = [
      `${SOURCE_IDS.WATERWAYS}-rio-tercero-line`,
      `${SOURCE_IDS.WATERWAYS}-arroyo-algodon-line`,
      `${SOURCE_IDS.WATERWAYS}-canal-desviador-line`,
      `${SOURCE_IDS.WATERWAYS}-canal-litin-line`,
      `${SOURCE_IDS.WATERWAYS}-canales-existentes-line`,
      `${SOURCE_IDS.WATERWAYS}-arroyo-mojarras-line`,
      `${SOURCE_IDS.SOIL}-fill`,
      `${SOURCE_IDS.CATASTRO}-fill`,
      `${SOURCE_IDS.ROADS}-line`,
      `${SOURCE_IDS.BASINS}-fill`,
      `${SOURCE_IDS.APPROVED_ZONES}-fill`,
      `${SOURCE_IDS.SUGGESTED_ZONES}-fill`,
      `${SOURCE_IDS.MARTIN_PUNTOS}-circle`,
    ];

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      if (markingMode) {
        setNewPoint({ lat: event.lngLat.lat, lng: event.lngLat.lng });
        return;
      }

      const features = map.queryRenderedFeatures(event.point, {
        layers: clickableLayers.filter((id) => map.getLayer(id)),
      });

      if (features.length > 0 && features[0]) {
        setSelectedFeature(features[0] as unknown as Feature);
      } else {
        setSelectedFeature(null);
      }
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [mapReady, mapRef, markingMode, setNewPoint, setSelectedFeature]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !showSuggestedZonesPanel) return;

    const handleBasinClick = (event: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(event.point, {
        layers: [`${SOURCE_IDS.BASINS}-fill`, `${SOURCE_IDS.SUGGESTED_ZONES}-fill`].filter((id) => map.getLayer(id)),
      });
      if (features.length > 0 && features[0]) {
        const basinId = features[0].properties?.id;
        if (typeof basinId === 'string') {
          setSelectedDraftBasinId(basinId);
        }
      }
    };

    map.on('click', handleBasinClick);
    return () => {
      map.off('click', handleBasinClick);
    };
  }, [mapReady, mapRef, setSelectedDraftBasinId, showSuggestedZonesPanel]);
}
