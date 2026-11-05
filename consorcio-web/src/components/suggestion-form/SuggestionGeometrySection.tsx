import { Box, Button, Group, Stack, Text } from '@mantine/core';
import type * as maplibregl from 'maplibre-gl';
import { useEffect, useRef, useState } from 'react';
import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { addReferenceLayers, useFormMapLayers } from '../../hooks/useFormMapLayers';
import { logger } from '../../lib/logger';
import { loadMapLibre } from '../../lib/maplibreLoader';
import formStyles from '../../styles/components/form.module.css';
import type { DrawnLineFeatureCollection } from '../map/LineDrawControl';
import SuggestionGeometryControl from '../map/SuggestionGeometryControl';
import { MAP_LOCALE_ES } from '../map2d/mapLibreLocale';
import { IconArrowBackUp, IconCurrentLocation, IconMapPin, IconTrash } from '../ui/icons';
import { isNonSpatialCategory } from './suggestionFormConstants';
import { GeometrySummary, showSuggestionNotification } from './suggestionFormUtils';

const SUGGESTION_GEOMETRY_LABEL_ID = 'sugerencia-geometria-label';
const SUGGESTION_GEOMETRY_INSTRUCTIONS_ID = 'sugerencia-geometria-instrucciones';
const SUGGESTION_GEOMETRY_REFERENCE_ID = 'sugerencia-geometria-referencia';
const SUGGESTION_GEOMETRY_SUMMARY_ID = 'sugerencia-geometria-resumen';
const SUGGESTION_GEOMETRY_STATUS_ID = 'sugerencia-geometria-estado';

/** Lifecycle of the lazily loaded map engine. Mirrors `LocationSection`. */
type MapStatus = 'loading' | 'ready' | 'error';

function removeLastVertexFromGeometry(
  geometry: DrawnLineFeatureCollection | null
): DrawnLineFeatureCollection | null {
  const features = geometry?.features ?? [];
  if (features.length === 0) return null;

  const last = features[features.length - 1];
  const prefix = features.slice(0, -1);

  if (last.geometry.type === 'Point') {
    return prefix.length > 0 ? { type: 'FeatureCollection', features: prefix } : null;
  }

  const remainingCoords = last.geometry.coordinates.slice(0, -1);
  if (remainingCoords.length >= 2) {
    return {
      type: 'FeatureCollection',
      features: [
        ...prefix,
        {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'LineString',
            coordinates: remainingCoords,
          },
        },
      ],
    };
  }

  if (remainingCoords.length === 1) {
    return {
      type: 'FeatureCollection',
      features: [
        ...prefix,
        {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'Point',
            coordinates: remainingCoords[0],
          },
        },
      ],
    };
  }

  return prefix.length > 0 ? { type: 'FeatureCollection', features: prefix } : null;
}

export function SuggestionGeometrySection({
  geometry,
  onChange,
  categoria,
}: Readonly<{
  geometry: DrawnLineFeatureCollection | null;
  onChange: (geometry: DrawnLineFeatureCollection | null) => void;
  categoria?: string;
}>) {
  const { zonaGeoJson, caminosGeoJson, waterways } = useFormMapLayers();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const [mapStatus, setMapStatus] = useState<MapStatus>('loading');
  const [locatingGps, setLocatingGps] = useState(false);
  const [showOptionalMap, setShowOptionalMap] = useState(false);
  const mapReady = mapStatus === 'ready';
  const hasGeometry = (geometry?.features?.length ?? 0) > 0;
  const isCollapsedByCategory = isNonSpatialCategory(categoria) && !showOptionalMap && !hasGeometry;

  useEffect(() => {
    if (isNonSpatialCategory(categoria) && !hasGeometry) {
      setShowOptionalMap(false);
    }
  }, [categoria, hasGeometry]);

  // PERF-005 — the map engine is fetched on demand (see `loadMapLibre`), so the
  // suggestion tab of `/participacion` no longer welds ~215 KB of MapLibre into
  // the page chunk. The effect body cannot be `async` (React needs the cleanup
  // synchronously), hence the inner IIFE plus the `cancelled` guard for an
  // unmount that races the in-flight chunk.
  useEffect(() => {
    if (isCollapsedByCategory) return;
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
        // Igual que el mapa de la denuncia: el trazo vive dentro de un
        // formulario que scrollea. Un dedo mueve la página; dos dedos mueven
        // el mapa. La atribución compacta no se come la altura del móvil.
        cooperativeGestures: true,
        attributionControl: { compact: true },
        locale: { ...MAP_LOCALE_ES },
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
  }, [isCollapsedByCategory]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapReady) return;
    try {
      addReferenceLayers(map, { zonaGeoJson, caminosGeoJson, waterways });
    } catch (err) {
      logger.error('[SugerenciaMap] addReferenceLayers failed', err);
    }
  }, [zonaGeoJson, caminosGeoJson, waterways, mapReady]);

  const handleLocateGps = () => {
    if (!navigator.geolocation) {
      showSuggestionNotification('Error', 'Tu navegador no soporta geolocalización', 'red');
      return;
    }

    setLocatingGps(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocatingGps(false);
        const { latitude, longitude } = position.coords;
        mapInstanceRef.current?.flyTo?.({
          center: [longitude, latitude],
          zoom: 15,
        });
        showSuggestionNotification(
          'Ubicación obtenida',
          'Se centró el mapa en tu ubicación actual',
          'green'
        );
      },
      (error) => {
        setLocatingGps(false);
        const errorMsg =
          error.code === error.TIMEOUT
            ? 'Tiempo de espera agotado al obtener tu ubicación. Podés navegar manualmente en el mapa.'
            : 'No se pudo obtener tu ubicación. Podés navegar manualmente en el mapa.';
        showSuggestionNotification('Error de ubicación', errorMsg, 'red');
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  const handleUndoLastPoint = () => {
    onChange(removeLastVertexFromGeometry(geometry));
  };

  const handleClearGeometry = () => {
    onChange(null);
  };

  if (isCollapsedByCategory) {
    return (
      <Box>
        <Button
          type="button"
          variant="subtle"
          size="sm"
          fullWidth
          className="touch-target-min"
          leftSection={<IconMapPin size={16} aria-hidden="true" />}
          onClick={() => setShowOptionalMap(true)}
        >
          Agregar ubicación en el mapa (opcional)
        </Button>
      </Box>
    );
  }

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
      <Stack gap={4}>
        <Text id={SUGGESTION_GEOMETRY_LABEL_ID} size="sm" fw={500}>
          Canal en mapa
        </Text>
        <Box id={SUGGESTION_GEOMETRY_SUMMARY_ID} role="status" aria-live="polite">
          <GeometrySummary geometry={geometry} />
        </Box>
      </Stack>

      <Text id={SUGGESTION_GEOMETRY_INSTRUCTIONS_ID} size="xs" c="dimmed">
        Hacé un clic para marcar un punto (o tocá el mapa en el celular). Si agregás otro punto, se
        convierte en línea. Con un dedo se desplaza la página; con dos dedos se mueve el mapa. Tocá
        un vértice o usá «Deshacer último punto» y «Limpiar dibujo» para corregir.
      </Text>

      <Group gap="sm" wrap="wrap">
        <Button
          type="button"
          variant="light"
          size="sm"
          className="touch-target-min"
          leftSection={<IconCurrentLocation size={16} aria-hidden="true" />}
          loading={locatingGps}
          onClick={handleLocateGps}
        >
          Mi ubicación (GPS)
        </Button>
        <Button
          type="button"
          variant="default"
          size="sm"
          className="touch-target-min"
          leftSection={<IconArrowBackUp size={16} aria-hidden="true" />}
          disabled={!hasGeometry}
          onClick={handleUndoLastPoint}
        >
          Deshacer último punto
        </Button>
        <Button
          type="button"
          variant="subtle"
          color="red"
          size="sm"
          className="touch-target-min"
          leftSection={<IconTrash size={16} aria-hidden="true" />}
          disabled={!hasGeometry}
          onClick={handleClearGeometry}
        >
          Limpiar dibujo
        </Button>
      </Group>

      <Box
        className={`${formStyles.mapContainer} ${formStyles.mapContainerLarge}`}
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
