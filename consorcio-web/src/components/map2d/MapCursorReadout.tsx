import { Text } from '@mantine/core';
import { useEffect, useState } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { coordsFromLngLat, formatMapCursorCoords } from './mapCursorCoords';

interface MapCursorReadoutProps {
  readonly map: MapLibreMap | null;
  readonly mapReady: boolean;
}

export function MapCursorReadout({ map, mapReady }: MapCursorReadoutProps) {
  const [label, setLabel] = useState(formatMapCursorCoords(null));

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
    </Text>
  );
}
