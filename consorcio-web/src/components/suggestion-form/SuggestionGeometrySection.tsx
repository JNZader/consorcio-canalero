import { Box, Group, Stack, Text } from '@mantine/core';
import type maplibregl from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { addReferenceLayers, useFormMapLayers } from '../../hooks/useFormMapLayers';
import { logger } from '../../lib/logger';
import { loadMapLibre } from '../../lib/maplibreLoader';
import formStyles from '../../styles/components/form.module.css';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';
import SuggestionGeometryControl from '../map/SuggestionGeometryControl';
import { GeometrySummary } from './suggestionFormUtils';

const SUGGESTION_GEOMETRY_LABEL_ID = 'sugerencia-geometria-label';
const SUGGESTION_GEOMETRY_INSTRUCTIONS_ID = 'sugerencia-geometria-instrucciones';
const SUGGESTION_GEOMETRY_REFERENCE_ID = 'sugerencia-geometria-referencia';
const SUGGESTION_GEOMETRY_SUMMARY_ID = 'sugerencia-geometria-resumen';
const SUGGESTION_GEOMETRY_STATUS_ID = 'sugerencia-geometria-estado';

/** Lifecycle of the lazily loaded map engine. Mirrors `LocationSection`. */
type MapStatus = 'loading' | 'ready' | 'error';

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
  const [mapStatus, setMapStatus] = useState<MapStatus>('loading');
  const mapReady = mapStatus === 'ready';

  // PERF-005 — the map engine is fetched on demand (see `loadMapLibre`), so the
  // suggestion tab of `/participacion` no longer welds ~215 KB of MapLibre into
  // the page chunk. The effect body cannot be `async` (React needs the cleanup
  // synchronously), hence the inner IIFE plus the `cancelled` guard for an
  // unmount that races the in-flight chunk.
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    let cancelled = false;
    let map: maplibregl.Map | null = null;

    void (async () => {
      let maplibregl: Awaited<ReturnType<typeof loadMapLibre>>;
      try {
        maplibregl = await loadMapLibre();
      } catch (err) {
        if (cancelled) return;
        // Without this branch a failed chunk left `aria-busy="true"` forever on
        // an empty box: no message, no way out, and no hint that the suggestion
        // can be sent anyway (the trace is OPTIONAL — `buildSugerenciaPayload`
        // sends `geometry ?? undefined`).
        logger.error('[SugerenciaMap] no se pudo cargar maplibre-gl', err);
        setMapStatus('error');
        return;
      }

      if (cancelled || !mapContainerRef.current || mapInstanceRef.current) return;

      map = new maplibregl.Map({
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
        if (cancelled) return;
        mapInstanceRef.current = map;
        setMapStatus('ready');
      });
    })();

    return () => {
      cancelled = true;
      map?.remove();
      map = null;
      mapInstanceRef.current = null;
      setMapStatus('loading');
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

  // The status notice joins the description only while it exists, so a ready map
  // keeps exactly the previous accessible description.
  const describedBy = [
    SUGGESTION_GEOMETRY_INSTRUCTIONS_ID,
    SUGGESTION_GEOMETRY_SUMMARY_ID,
    SUGGESTION_GEOMETRY_REFERENCE_ID,
    mapStatus === 'ready' ? null : SUGGESTION_GEOMETRY_STATUS_ID,
  ]
    .filter(Boolean)
    .join(' ');

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
        aria-describedby={describedBy}
        aria-busy={mapStatus === 'loading'}
        style={{ position: 'relative' }}
      >
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
        {mapStatus !== 'ready' && (
          <Box
            id={SUGGESTION_GEOMETRY_STATUS_ID}
            aria-live="polite"
            data-testid="sugerencia-geometria-estado"
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              padding: 'var(--mantine-spacing-md)',
            }}
          >
            <Text size="sm" c={mapStatus === 'error' ? 'red' : 'dimmed'}>
              {mapStatus === 'error'
                ? 'No se pudo cargar el mapa. El trazo es opcional: podés enviar la sugerencia igual describiendo la ubicación en el texto, o recargar la página para reintentar.'
                : 'Cargando mapa…'}
            </Text>
          </Box>
        )}
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
