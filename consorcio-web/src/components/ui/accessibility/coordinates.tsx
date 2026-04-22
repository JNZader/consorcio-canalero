import { Alert, Box, Button, Group, Stack, Text, TextInput } from '@mantine/core';
import { useState } from 'react';
import { logger } from '../../../lib/logger';
import { useLiveRegion } from './liveRegion';
import { AccessibleError } from './primitives';

interface CoordinatesInputProps {
  readonly onCoordinatesChange: (lat: number, lng: number) => void;
  readonly currentLat?: number | null;
  readonly currentLng?: number | null;
  readonly onAddressSearch?: (address: string) => Promise<{ lat: number; lng: number } | null>;
}

export function CoordinatesInput({
  onCoordinatesChange,
  currentLat,
  currentLng,
  onAddressSearch,
}: CoordinatesInputProps) {
  const [manualLat, setManualLat] = useState(currentLat?.toString() || '');
  const [manualLng, setManualLng] = useState(currentLng?.toString() || '');
  const [searchAddress, setSearchAddress] = useState('');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { announce } = useLiveRegion();

  const handleManualSubmit = () => {
    const lat = Number.parseFloat(manualLat);
    const lng = Number.parseFloat(manualLng);

    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      setError('Por favor, ingresa coordenadas validas (numeros decimales)');
      announce('Error: coordenadas invalidas', 'assertive');
      return;
    }
    if (lat < -90 || lat > 90) {
      setError('La latitud debe estar entre -90 y 90');
      announce('Error: latitud fuera de rango', 'assertive');
      return;
    }
    if (lng < -180 || lng > 180) {
      setError('La longitud debe estar entre -180 y 180');
      announce('Error: longitud fuera de rango', 'assertive');
      return;
    }

    setError(null);
    onCoordinatesChange(lat, lng);
    announce(`Ubicacion establecida: latitud ${lat.toFixed(4)}, longitud ${lng.toFixed(4)}`);
  };

  const handleAddressSearch = async () => {
    if (!onAddressSearch || !searchAddress.trim()) return;

    setSearching(true);
    setError(null);
    announce('Buscando direccion...');

    try {
      const result = await onAddressSearch(searchAddress);
      if (result) {
        onCoordinatesChange(result.lat, result.lng);
        setManualLat(result.lat.toString());
        setManualLng(result.lng.toString());
        announce(
          `Direccion encontrada: latitud ${result.lat.toFixed(4)}, longitud ${result.lng.toFixed(4)}`
        );
      } else {
        setError('No se encontro la direccion. Intenta con otra busqueda.');
        announce('Direccion no encontrada', 'assertive');
      }
    } catch (error) {
      logger.error('Error al buscar direccion:', error);
      setError('Error al buscar la direccion');
      announce('Error en la busqueda', 'assertive');
    } finally {
      setSearching(false);
    }
  };

  return (
    <Stack gap="md">
      <Box
        component="fieldset"
        style={{
          border: '1px solid var(--mantine-color-gray-4)',
          padding: '1rem',
          borderRadius: 8,
        }}
      >
        <Text component="legend" size="sm" fw={500} mb="xs">
          Opcion 1: Ingresar coordenadas manualmente
        </Text>
        <Group gap="sm" align="flex-end">
          <TextInput
            label="Latitud"
            placeholder="-32.63"
            value={manualLat}
            onChange={(event) => setManualLat(event.target.value)}
            aria-describedby="lat-format-help"
            style={{ flex: 1 }}
            inputMode="decimal"
          />
          <TextInput
            label="Longitud"
            placeholder="-62.68"
            value={manualLng}
            onChange={(event) => setManualLng(event.target.value)}
            aria-describedby="lng-format-help"
            style={{ flex: 1 }}
            inputMode="decimal"
          />
          <Button onClick={handleManualSubmit} variant="light">
            Establecer
          </Button>
        </Group>
        <Text id="lat-format-help" size="xs" c="gray.6" mt="xs">
          Formato: numeros decimales (ej: -32.63000 para latitud sur)
        </Text>
      </Box>

      {onAddressSearch && (
        <Box
          component="fieldset"
          style={{
            border: '1px solid var(--mantine-color-gray-4)',
            padding: '1rem',
            borderRadius: 8,
          }}
        >
          <Text component="legend" size="sm" fw={500} mb="xs">
            Opcion 2: Buscar por direccion
          </Text>
          <Group gap="sm">
            <TextInput
              placeholder="Ej: Ruta 9 km 312, Bell Ville, Cordoba"
              value={searchAddress}
              onChange={(event) => setSearchAddress(event.target.value)}
              aria-label="Direccion a buscar"
              style={{ flex: 1 }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') handleAddressSearch();
              }}
            />
            <Button onClick={handleAddressSearch} loading={searching} variant="light">
              Buscar
            </Button>
          </Group>
        </Box>
      )}

      <AccessibleError id="coords-error" error={error} />

      {currentLat && currentLng && (
        <Alert color="green" variant="light">
          <Text size="sm">
            <strong>Ubicacion seleccionada:</strong> {currentLat.toFixed(5)},{' '}
            {currentLng.toFixed(5)}
          </Text>
        </Alert>
      )}
    </Stack>
  );
}
