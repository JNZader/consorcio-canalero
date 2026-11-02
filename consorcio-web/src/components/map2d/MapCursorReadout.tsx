import { Text } from '@mantine/core';
import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useState } from 'react';

import { coordsFromLngLat, formatMapCursorCoords } from './mapCursorCoords';
import { useMapFeatureReadout } from './mapFeatureReadout';

interface MapCursorReadoutProps {
  readonly map: MapLibreMap | null;
  readonly mapReady: boolean;
}

export function MapCursorReadout({ map, mapReady }: MapCursorReadoutProps) {
  const [label, setLabel] = useState(formatMapCursorCoords(null));
  const featureLabel = useMapFeatureReadout('2d');

  useEffect(() => {
    if (!map || !mapReady) return;
    const onMove = (event: { lngLat: { lng: number; lat: number } }) => {
      setLabel(formatMapCursorCoords(coordsFromLngLat(event.lngLat)));
    };
    const onLeave = () => setLabel(formatMapCursorCoords(null));
    map.on('mousemove', onMove);
    map.on('mouseout', onLeave);
    return () => {
      map.off('mousemove', onMove);
      map.off('mouseout', onLeave);
    };
  }, [map, mapReady]);

  return (
    <Text size="xs" c="dimmed" data-testid="map-cursor-coords" aria-live="polite">
      {label}
      {featureLabel ? (
        <Text span data-testid="map-feature-readout">{` · ${featureLabel}`}</Text>
      ) : null}
    </Text>
  );
}
