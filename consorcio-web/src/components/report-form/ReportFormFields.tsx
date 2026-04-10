import { Box, Button, SimpleGrid, Skeleton, Text, Textarea } from '@mantine/core';
import type { ReactNode } from 'react';
import { MAP_CENTER } from '../../constants';
import { AccessibleRadioGroup } from '../ui/accessibility';
import { LocationSection } from './LocationSection';
import { PhotoSection } from './PhotoSection';
import type { Ubicacion } from './reportFormTypes';

export interface TipoDenunciaOption {
  value: string;
  label: string;
  description?: string;
  icon?: ReactNode;
}

interface TipoProblemaFieldProps {
  contactoVerificado: boolean;
  value: string;
  error?: string;
  onChange: (value: string) => void;
  tiposDenuncia: TipoDenunciaOption[];
}

export function TipoProblemaField({
  contactoVerificado,
  value,
  error,
  onChange,
  tiposDenuncia,
}: Readonly<TipoProblemaFieldProps>) {
  if (contactoVerificado) {
    return (
      <AccessibleRadioGroup
        name="tipo-denuncia"
        label="Tipo de problema"
        options={tiposDenuncia}
        value={value}
        onChange={onChange}
        error={error}
        required
        columns={4}
      />
    );
  }

  return (
    <Box>
      <Text fw={500} size="sm" mb="xs">
        Tipo de problema *
      </Text>
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} height={70} radius="md" />
        ))}
      </SimpleGrid>
    </Box>
  );
}

interface DescripcionFieldProps {
  contactoVerificado: boolean;
  error?: string;
  getInputProps: (field: string) => object;
}

export function DescripcionField({
  contactoVerificado,
  error,
  getInputProps,
}: Readonly<DescripcionFieldProps>) {
  if (contactoVerificado) {
    return (
      <Box>
        <Textarea
          label="Descripcion"
          placeholder="Describe el problema con el mayor detalle posible..."
          minRows={4}
          {...getInputProps('descripcion')}
          required
          aria-describedby={error ? 'descripcion-error' : undefined}
        />
        {error && (
          <Text id="descripcion-error" size="xs" c="red" mt="xs" role="alert">
            {error}
          </Text>
        )}
      </Box>
    );
  }

  return (
    <Box>
      <Text size="sm" fw={500} mb="xs">
        Descripcion *
      </Text>
      <Skeleton height={100} radius="sm" />
    </Box>
  );
}

interface UbicacionFieldProps {
  contactoVerificado: boolean;
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
  contactoVerificado,
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
        Ubicacion del incidente *
      </Text>
      {contactoVerificado ? (
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
      ) : (
        <>
          <Skeleton height={36} width={180} radius="sm" mb="sm" />
          <Box style={{ minHeight: 360 }}>
            <Skeleton height="100%" radius="md" />
          </Box>
        </>
      )}
    </Box>
  );
}

interface FotoFieldProps {
  contactoVerificado: boolean;
  fotoPreview: string | null;
  onDrop: (files: File[]) => void;
  onRemove: () => void;
}

export function FotoField({
  contactoVerificado,
  fotoPreview,
  onDrop,
  onRemove,
}: Readonly<FotoFieldProps>) {
  return (
    <Box>
      <Text fw={500} size="sm" mb="xs" id="foto-label">
        Foto (opcional)
      </Text>
      {contactoVerificado ? (
        <PhotoSection fotoPreview={fotoPreview} onDrop={onDrop} onRemove={onRemove} />
      ) : (
        <Skeleton height={120} radius="md" />
      )}
    </Box>
  );
}

interface SubmitButtonProps {
  contactoVerificado: boolean;
  disabled: boolean;
}

export function SubmitButton({ contactoVerificado, disabled }: Readonly<SubmitButtonProps>) {
  if (contactoVerificado) {
    return (
      <Button type="submit" size="lg" fullWidth disabled={disabled}>
        Enviar Reporte
      </Button>
    );
  }
  return <Skeleton height={50} radius="md" />;
}
