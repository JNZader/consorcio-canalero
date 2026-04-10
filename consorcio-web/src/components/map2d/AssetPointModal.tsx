import { Button, Modal, Select, Stack, Text, Textarea, TextInput } from '@mantine/core';
import { type FormEvent, memo } from 'react';

interface AssetPointModalProps {
  readonly opened: boolean;
  readonly coordinates: { lat: number; lng: number } | null;
  readonly onClose: () => void;
  readonly onSubmit: (event?: FormEvent<HTMLFormElement>) => void;
  readonly isSubmitting: boolean;
  readonly nameInputProps: object;
  readonly typeInputProps: object;
  readonly descriptionInputProps: object;
}

const ASSET_TYPE_OPTIONS = [
  { value: 'alcantarilla', label: 'Alcantarilla' },
  { value: 'puente', label: 'Puente' },
  { value: 'canal', label: 'Canal' },
  { value: 'otro', label: 'Otro' },
];

export const AssetPointModal = memo(function AssetPointModal({
  opened,
  coordinates,
  onClose,
  onSubmit,
  isSubmitting,
  nameInputProps,
  typeInputProps,
  descriptionInputProps,
}: AssetPointModalProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="Registrar activo de infraestructura" size="sm">
      <form onSubmit={onSubmit}>
        <Stack gap="xs">
          <Text size="xs" c="dimmed">
            Coordenadas: {coordinates?.lat.toFixed(5)}, {coordinates?.lng.toFixed(5)}
          </Text>
          <TextInput size="xs" label="Nombre" placeholder="Nombre del activo" {...nameInputProps} />
          <Select size="xs" label="Tipo" data={ASSET_TYPE_OPTIONS} {...typeInputProps} />
          <Textarea
            size="xs"
            label="Descripción"
            placeholder="Descripción opcional"
            minRows={2}
            {...descriptionInputProps}
          />
          <Button type="submit" size="xs" loading={isSubmitting}>
            Guardar punto
          </Button>
        </Stack>
      </form>
    </Modal>
  );
});
