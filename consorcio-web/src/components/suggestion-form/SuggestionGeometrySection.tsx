import { Box, Group, Stack, Text } from '@mantine/core';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useRef, useState } from 'react';
import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { addReferenceLayers, useFormMapLayers } from '../../hooks/useFormMapLayers';
import formStyles from '../../styles/components/form.module.css';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';
import SuggestionGeometryControl from '../map/SuggestionGeometryControl';
import { GeometrySummary } from './suggestionFormUtils';

export function SuggestionGeometrySection({
  geometry,
  onChange,
}: Readonly<{
  geometry: DrawnLineFeatureCollection | null;
  onChange: (geometry: DrawnLineFeatureCollection | null) => void;
}>) {
  const { zonaGeoJson, caminosGeoJson, waterways } = useFormMapLayers();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            ],
            tileSize: 256,
            attribution: 'Tiles &copy; Esri',
          },
        },
        layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }],
      },
      center: [MAP_CENTER[1], MAP_CENTER[0]],
      zoom: 12,
      minZoom: MAP_MIN_ZOOM,
      maxBounds: MAP_MAX_BOUNDS,
    });

    map.on('load', () => {
      mapInstanceRef.current = map;
      setMapReady(true);
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
      setMapReady(false);
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    try {
      addReferenceLayers(map, { zonaGeoJson, caminosGeoJson, waterways });
    } catch (err) {
      console.error('[SugerenciaMap] addReferenceLayers failed:', err);
    }
  }, [zonaGeoJson, caminosGeoJson, waterways, mapReady]);

  return (
    <Stack gap="xs">
      <Group justify="space-between" align="center">
        <Text size="sm" fw={500}>
          Canal en mapa
        </Text>
        <GeometrySummary geometry={geometry} />
      </Group>

      <Text size="xs" c="dimmed">
        Haz un clic para marcar un punto. Si haces otro clic, se convierte en línea. Clic derecho o
        clic sobre el punto para borrar lo último.
      </Text>

      <Box className={formStyles.mapContainer}>
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
        {mapReady && mapInstanceRef.current && (
          <SuggestionGeometryControl
            map={mapInstanceRef.current}
            value={geometry}
            onChange={onChange}
          />
        )}
      </Box>

      <Text size="xs" c="dimmed">
        Referencia: límite del consorcio (rojo), hidrografía (azul), caminos (amarillo). Lo que
        dibujes queda como sugerencia, no como canal oficial.
      </Text>
    </Stack>
  );
}
