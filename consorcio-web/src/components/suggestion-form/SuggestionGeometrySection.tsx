import { Box, Group, Stack, Text } from '@mantine/core';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useRef, useState } from 'react';
import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { addReferenceLayers, useFormMapLayers } from '../../hooks/useFormMapLayers';
import { logger } from '../../lib/logger';
import formStyles from '../../styles/components/form.module.css';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';
import SuggestionGeometryControl from '../map/SuggestionGeometryControl';
import { GeometrySummary } from './suggestionFormUtils';

const SUGGESTION_GEOMETRY_LABEL_ID = 'sugerencia-geometria-label';
const SUGGESTION_GEOMETRY_INSTRUCTIONS_ID = 'sugerencia-geometria-instrucciones';
const SUGGESTION_GEOMETRY_REFERENCE_ID = 'sugerencia-geometria-referencia';
const SUGGESTION_GEOMETRY_SUMMARY_ID = 'sugerencia-geometria-resumen';

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
      logger.error('[SugerenciaMap] addReferenceLayers failed', err);
    }
  }, [zonaGeoJson, caminosGeoJson, waterways, mapReady]);

  return (
    <Stack gap="xs">
      <Group justify="space-between" align="center">
        <Text id={SUGGESTION_GEOMETRY_LABEL_ID} size="sm" fw={500}>
          Canal en mapa
        </Text>
        <Box id={SUGGESTION_GEOMETRY_SUMMARY_ID} role="status" aria-live="polite">
          <GeometrySummary geometry={geometry} />
        </Box>
      </Group>

      <Text id={SUGGESTION_GEOMETRY_INSTRUCTIONS_ID} size="xs" c="dimmed">
        Haz un clic para marcar un punto. Si haces otro clic, se convierte en línea. Clic derecho o
        clic sobre el punto para borrar lo último.
      </Text>

      <Box
        className={formStyles.mapContainer}
        role="application"
        aria-labelledby={SUGGESTION_GEOMETRY_LABEL_ID}
        aria-describedby={`${SUGGESTION_GEOMETRY_INSTRUCTIONS_ID} ${SUGGESTION_GEOMETRY_SUMMARY_ID} ${SUGGESTION_GEOMETRY_REFERENCE_ID}`}
        aria-busy={!mapReady}
      >
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
        {mapReady && mapInstanceRef.current && (
          <SuggestionGeometryControl
            map={mapInstanceRef.current}
            value={geometry}
            onChange={onChange}
          />
        )}
      </Box>

      <Text id={SUGGESTION_GEOMETRY_REFERENCE_ID} size="xs" c="dimmed">
        Referencia: límite del consorcio (rojo), hidrografía (azul), caminos (amarillo). Lo que
        dibujes queda como sugerencia, no como canal oficial.
      </Text>
    </Stack>
  );
}
