import { Box, Button, Text, Textarea } from '@mantine/core';
import type { ReactNode } from 'react';
import { MAP_CENTER } from '../../constants';
import { AccessibleRadioGroup } from '../ui/accessibility';
import { LocationSection } from './LocationSection';
import { PhotoSection } from './PhotoSection';
import type { Ubicacion } from './reportFormTypes';

const DESCRIPCION_ERROR_ID = 'descripcion-error';

export interface TipoDenunciaOption {
  value: string;
  label: string;
  description?: string;
  icon?: ReactNode;
}

interface TipoProblemaFieldProps {
  value: string;
  error?: string;
  onChange: (value: string) => void;
  tiposDenuncia: TipoDenunciaOption[];
}

export function TipoProblemaField({
  value,
  error,
  onChange,
  tiposDenuncia,
}: Readonly<TipoProblemaFieldProps>) {
  return (
    <AccessibleRadioGroup
      name="tipo-denuncia"
      label="Tipo de problema"
      options={tiposDenuncia}
      value={value}
      onChange={onChange}
      error={error}
      required
    />
  );
}

interface DescripcionFieldProps {
  error?: string;
  getInputProps: (field: string) => object;
}

export function DescripcionField({ error, getInputProps }: Readonly<DescripcionFieldProps>) {
  return (
    <Textarea
      label="Descripción"
      placeholder="Describí el problema con el mayor detalle posible..."
      minRows={4}
      {...getInputProps('descripcion')}
      required
      error={error}
      errorProps={{
        id: DESCRIPCION_ERROR_ID,
        role: 'alert',
        'aria-live': 'assertive',
      }}
    />
  );
}

interface UbicacionFieldProps {
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

export function UbicacionField({
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
}: Readonly<UbicacionFieldProps>) {
  return (
    <Box>
      <Text fw={500} size="sm" mb="xs" id="ubicacion-label">
        Ubicación del incidente *
      </Text>
      <LocationSection
        ubicacion={ubicacion}
        mostrarInputManual={mostrarInputManual}
        obteniendoUbicacion={obteniendoUbicacion}
        onObtenerGPS={onObtenerGPS}
        onToggleInputManual={onToggleInputManual}
        onLocationSelect={onLocationSelect}
        onCoordinatesChange={onCoordinatesChange}
        onClearLocation={onClearLocation}
        defaultCenter={defaultCenter}
        defaultZoom={defaultZoom}
      />
    </Box>
  );
}

interface FotoFieldProps {
  fotoPreview: string | null;
  onDrop: (files: File[]) => void;
  onRemove: () => void;
}

export function FotoField({ fotoPreview, onDrop, onRemove }: Readonly<FotoFieldProps>) {
  return (
    <Box>
      <Text fw={500} size="sm" mb="xs" id="foto-label">
        Foto (opcional)
      </Text>
      <PhotoSection fotoPreview={fotoPreview} onDrop={onDrop} onRemove={onRemove} />
    </Box>
  );
}

interface SubmitButtonProps {
  disabled: boolean;
}

export function SubmitButton({ disabled }: Readonly<SubmitButtonProps>) {
  return (
    <Button type="submit" size="lg" fullWidth disabled={disabled}>
      Enviar Reporte
    </Button>
  );
}
