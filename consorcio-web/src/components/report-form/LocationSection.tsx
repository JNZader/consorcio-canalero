import { Badge, Box, Button, Collapse, Group, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useRef } from 'react';
import { MAP_CENTER } from '../../constants';
import { addReferenceLayers, isInsideZona, useFormMapLayers } from '../../hooks/useFormMapLayers';
import { CoordinatesInput } from '../ui/accessibility';
import formStyles from '../../styles/components/form.module.css';
import type { Ubicacion } from './reportFormTypes';

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
  const onLocationSelectRef = useRef(onLocationSelect);
  onLocationSelectRef.current = onLocationSelect;
  const { zonaGeoJson, caminosGeoJson, waterways } = useFormMapLayers();

  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const SATELLITE_TILES =
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

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
      center: [defaultCenter[1], defaultCenter[0]],
      zoom: defaultZoom,
    });

    map.on('click', (e) => {
      const { lng, lat } = e.lngLat;
      if (!isInsideZona(zonaGeoJson, [lng, lat])) {
        notifications.show({
          title: 'Fuera del área',
          message: 'La ubicación seleccionada está fuera del área del consorcio.',
          color: 'red',
        });
        return;
      }
      onLocationSelectRef.current(lat, lng);
    });

    map.on('load', () => {
      addReferenceLayers(map, { zonaGeoJson, caminosGeoJson, waterways });
    });

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
      markerRef.current = null;
    };
  }, [caminosGeoJson, defaultCenter, defaultZoom, waterways, zonaGeoJson]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !map.isStyleLoaded()) return;
    addReferenceLayers(map, { zonaGeoJson, caminosGeoJson, waterways });
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

    map.flyTo({ center: [ubicacion.lng, ubicacion.lat], zoom: Math.max(map.getZoom(), 14) });
  }, [ubicacion]);

  return (
    <>
      <Group gap="sm" mb="sm">
        <Button
          onClick={onObtenerGPS}
          loading={obteniendoUbicacion}
          variant="light"
          size="sm"
          leftSection={<span aria-hidden="true">&#128205;</span>}
        >
          Usar mi ubicacion GPS
        </Button>
        <Button
          onClick={onToggleInputManual}
          variant="subtle"
          size="sm"
          aria-expanded={mostrarInputManual}
          aria-controls="input-coordenadas-manual"
        >
          {mostrarInputManual ? 'Ocultar entrada manual' : 'Ingresar coordenadas manualmente'}
        </Button>
        {ubicacion && (
          <Group gap="xs">
            <Badge color="green" variant="light">
              {ubicacion.lat.toFixed(5)}, {ubicacion.lng.toFixed(5)}
            </Badge>
            <Button size="xs" variant="subtle" color="red" onClick={onClearLocation}>
              Limpiar
            </Button>
          </Group>
        )}
      </Group>

      <Collapse in={mostrarInputManual}>
        <Box id="input-coordenadas-manual" mb="md">
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
        aria-label="Mapa interactivo para seleccionar ubicacion. Haz clic en el mapa para marcar la ubicacion del incidente."
      >
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
      </Box>
      <Text size="xs" c="gray.6" mt="xs">
        Haz clic dentro del área del consorcio para marcar la ubicación del incidente.
        Referencia: límite del consorcio (rojo), hidrografía (azul), caminos (amarillo).
      </Text>
    </>
  );
}
