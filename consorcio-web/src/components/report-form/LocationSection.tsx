import { Badge, Box, Button, Collapse, Group, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useRef } from 'react';
import { MAP_CENTER, MAP_MAX_BOUNDS, MAP_MIN_ZOOM } from '../../constants';
import { addReferenceLayers, isInsideZona, useFormMapLayers } from '../../hooks/useFormMapLayers';
import formStyles from '../../styles/components/form.module.css';
import { CoordinatesInput } from '../ui/accessibility';
import type { Ubicacion } from './reportFormTypes';

const MANUAL_COORDINATES_PANEL_ID = 'input-coordenadas-manual';
const LOCATION_HELP_ID = 'ubicacion-mapa-ayuda';
const SELECTED_LOCATION_ID = 'ubicacion-seleccionada';

interface LocationSectionProps {
  ubicacion: Ubicacion | null;
  mostrarInputManual: boolean;
  obteniendoUbicacion: boolean;
  onObtenerGPS: () => void;
  onToggleInputManual: () => void;
  onLocationSelect: (lat: number, lng: number) => void;
  onCoordinatesChange: (lat: number, lng: number) => void;
  onClearLocation: () => void;
  defaultCenter?: [number, number];
  defaultZoom?: number;
}

export function LocationSection({
  ubicacion,
  mostrarInputManual,
  obteniendoUbicacion,
  onObtenerGPS,
  onToggleInputManual,
  onLocationSelect,
  onCoordinatesChange,
  onClearLocation,
  defaultCenter = MAP_CENTER,
  defaultZoom = 12,
}: Readonly<LocationSectionProps>) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);

  // Refs for everything the map's `click` handler needs to read AT CLICK
  // TIME instead of at setup time. The setup effect runs ONLY ONCE on
  // mount (deps `[]`); pulling these into refs avoids the previous bug
  // where any change in `caminosGeoJson` / `waterways` / etc. tore the
  // map down (`map.remove()`) and rebuilt it on every parent re-render —
  // that's what was making the form "reset" when the user typed in
  // descripcion or picked a tipo, and what threw the cascade of
  // `WebGL context was lost` errors.
  const onLocationSelectRef = useRef(onLocationSelect);
  onLocationSelectRef.current = onLocationSelect;
  const { zonaGeoJson, caminosGeoJson, waterways } = useFormMapLayers();
  const zonaGeoJsonRef = useRef(zonaGeoJson);
  zonaGeoJsonRef.current = zonaGeoJson;
  const initialCenterRef = useRef(defaultCenter);
  const initialZoomRef = useRef(defaultZoom);

  const selectedCoordinatesLabel = ubicacion
    ? `${ubicacion.lat.toFixed(5)}, ${ubicacion.lng.toFixed(5)}`
    : null;

  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const SATELLITE_TILES =
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

    const initialCenter = initialCenterRef.current;
    const initialZoom = initialZoomRef.current;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: 'raster',
            tiles: [SATELLITE_TILES],
            tileSize: 256,
            attribution: 'Tiles &copy; Esri',
          },
        },
        layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }],
      },
      center: [initialCenter[1], initialCenter[0]],
      zoom: initialZoom,
      minZoom: MAP_MIN_ZOOM,
      maxBounds: MAP_MAX_BOUNDS,
    });

    map.on('click', (e) => {
      const { lng, lat } = e.lngLat;
      // Read zonaGeoJson via ref so we always validate against the
      // latest data, even though the click handler was registered once
      // at mount time when the data wasn't loaded yet.
      if (!isInsideZona(zonaGeoJsonRef.current, [lng, lat])) {
        notifications.show({
          title: 'Fuera del área',
          message: 'La ubicación seleccionada está fuera del área del consorcio.',
          color: 'red',
        });
        return;
      }
      onLocationSelectRef.current(lat, lng);
    });

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
      markerRef.current = null;
    };
    // Setup runs ONCE per mount. Reference layers (zona / caminos /
    // waterways) are painted by the dedicated effect below as soon as
    // both the map style AND the data are ready.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const paint = () => {
      addReferenceLayers(map, { zonaGeoJson, caminosGeoJson, waterways });
    };
    if (map.isStyleLoaded()) {
      paint();
    } else {
      map.once('load', paint);
    }
  }, [zonaGeoJson, caminosGeoJson, waterways]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (!ubicacion) {
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
      return;
    }

    if (markerRef.current) {
      markerRef.current.setLngLat([ubicacion.lng, ubicacion.lat]);
    } else {
      markerRef.current = new maplibregl.Marker({ color: '#e03131' })
        .setLngLat([ubicacion.lng, ubicacion.lat])
        .addTo(map);
    }

    // Only animate to the new spot if it's outside the current viewport.
    // When the user clicks the map, the point is by definition INSIDE
    // the viewport — animating there is jarring and was the user's main
    // complaint ("se mueve el mapa"). When the source is GPS or manual
    // input, the point may be off-screen and we DO want to bring it in.
    const bounds = map.getBounds();
    const inView = bounds.contains([ubicacion.lng, ubicacion.lat]);
    if (!inView) {
      map.flyTo({ center: [ubicacion.lng, ubicacion.lat], zoom: Math.max(map.getZoom(), 14) });
    }
  }, [ubicacion]);

  return (
    <>
      <Group gap="sm" mb="sm">
        <Button
          type="button"
          onClick={onObtenerGPS}
          loading={obteniendoUbicacion}
          variant="light"
          size="sm"
          leftSection={<span aria-hidden="true">&#128205;</span>}
          aria-busy={obteniendoUbicacion}
        >
          Usar mi ubicacion GPS
        </Button>
        <Button
          type="button"
          onClick={onToggleInputManual}
          variant="subtle"
          size="sm"
          aria-expanded={mostrarInputManual}
          aria-controls={MANUAL_COORDINATES_PANEL_ID}
        >
          {mostrarInputManual ? 'Ocultar entrada manual' : 'Ingresar coordenadas manualmente'}
        </Button>
        {ubicacion && selectedCoordinatesLabel && (
          <Group gap="xs" role="status" aria-live="polite">
            <Badge id={SELECTED_LOCATION_ID} color="green" variant="light">
              {selectedCoordinatesLabel}
            </Badge>
            <Button
              type="button"
              size="xs"
              variant="subtle"
              color="red"
              onClick={onClearLocation}
              aria-label={`Limpiar ubicación seleccionada ${selectedCoordinatesLabel}`}
            >
              Limpiar
            </Button>
          </Group>
        )}
      </Group>

      <Collapse in={mostrarInputManual}>
        <Box
          id={MANUAL_COORDINATES_PANEL_ID}
          role="region"
          aria-labelledby="ubicacion-label"
          mb="md"
        >
          <CoordinatesInput
            onCoordinatesChange={onCoordinatesChange}
            currentLat={ubicacion?.lat}
            currentLng={ubicacion?.lng}
          />
        </Box>
      </Collapse>

      <Box
        className={`${formStyles.mapContainer} ${formStyles.mapContainerLarge}`}
        role="application"
        aria-label="Mapa interactivo para seleccionar ubicación"
        aria-describedby={
          selectedCoordinatesLabel
            ? `${LOCATION_HELP_ID} ${SELECTED_LOCATION_ID}`
            : LOCATION_HELP_ID
        }
      >
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
      </Box>
      <Text id={LOCATION_HELP_ID} size="xs" c="gray.6" mt="xs">
        Haz clic dentro del área del consorcio para marcar la ubicación del incidente. Referencia:
        límite del consorcio (rojo), hidrografía (azul), caminos (amarillo).
      </Text>
    </>
  );
}
