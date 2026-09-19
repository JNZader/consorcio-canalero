import { Button, Group, Modal, Select, Stack, Text, TextInput, Textarea } from '@mantine/core';
import { memo, useEffect, useState } from 'react';

import {
  PUNTO_INTERES_TIPOS,
  PUNTO_INTERES_TIPO_LABELS,
  type PuntoInteresTipo,
} from '../../lib/api/puntosInteres';

const TIPO_OPTIONS = Object.values(PUNTO_INTERES_TIPOS).map((value) => ({
  value,
  label: PUNTO_INTERES_TIPO_LABELS[value],
}));

export interface PuntoInteresPlaceModalProps {
  readonly opened: boolean;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onClose: () => void;
  readonly onSave: (input: {
    titulo: string;
    nota: string;
    tipo: PuntoInteresTipo;
  }) => void | Promise<void>;
}

export const PuntoInteresPlaceModal = memo(function PuntoInteresPlaceModal({
  opened,
  saving,
  error,
  onClose,
  onSave,
}: PuntoInteresPlaceModalProps) {
  const [titulo, setTitulo] = useState('');
  const [nota, setNota] = useState('');
  const [tipo, setTipo] = useState<PuntoInteresTipo | null>(PUNTO_INTERES_TIPOS.ALCANTARILLA);

  useEffect(() => {
    if (!opened) return;
    setTitulo('');
    setNota('');
    setTipo(PUNTO_INTERES_TIPOS.ALCANTARILLA);
  }, [opened]);

  const canSave = titulo.trim().length > 0 && tipo !== null && !saving;

  return (
    <Modal opened={opened} onClose={onClose} title="Punto de interés" size="sm">
      <Stack gap="xs">
        <TextInput
          size="xs"
          label="Título"
          required
          value={titulo}
          maxLength={120}
          onChange={(event) => setTitulo(event.currentTarget.value)}
        />
        <Select
          size="xs"
          label="Tipo"
          required
          data={TIPO_OPTIONS}
          value={tipo}
          onChange={(value) => setTipo(value as PuntoInteresTipo | null)}
        />
        <Textarea
          size="xs"
          label="Nota"
          value={nota}
          maxLength={2000}
          minRows={3}
          onChange={(event) => setNota(event.currentTarget.value)}
        />
        {error ? (
          <Text size="xs" c="red">
            {error}
          </Text>
        ) : null}
        <Group justify="flex-end" gap="xs">
          <Button size="xs" variant="default" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            size="xs"
            onClick={() => {
              if (!tipo) return;
              onSave({ titulo: titulo.trim(), nota: nota.trim(), tipo });
            }}
            disabled={!canSave}
            loading={saving}
          >
            Guardar
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
});
