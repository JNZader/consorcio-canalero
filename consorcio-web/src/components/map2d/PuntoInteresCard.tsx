import { Button, Stack, Text, Title } from '@mantine/core';
import { memo, useState } from 'react';

import {
  PUNTO_INTERES_TIPO_LABELS,
  type PuntoInteresProperties,
} from '../../lib/api/puntosInteres';
import { ConfirmDialog } from '../ui/ConfirmDialog';

export interface PuntoInteresCardProps {
  readonly properties: PuntoInteresProperties;
  readonly onDelete?: (id: string) => void;
}

export const PuntoInteresCard = memo(function PuntoInteresCard({
  properties,
  onDelete,
}: PuntoInteresCardProps) {
  const tipoLabel = PUNTO_INTERES_TIPO_LABELS[properties.tipo] ?? properties.tipo;
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <Stack gap="xs" data-testid="punto-interes-card">
      <Title order={5}>{properties.titulo}</Title>
      <Text size="xs" c="dimmed">
        {tipoLabel}
      </Text>
      {properties.nota ? <Text size="sm">{properties.nota}</Text> : null}
      {onDelete ? (
        <Button
          size="xs"
          color="red"
          variant="light"
          aria-label="Borrar punto de interés"
          onClick={() => setConfirmOpen(true)}
        >
          Borrar
        </Button>
      ) : null}
      {onDelete ? (
        <ConfirmDialog
          opened={confirmOpen}
          title="Borrar punto de interés"
          message={`¿Borrar «${properties.titulo}»? No se puede deshacer.`}
          confirmLabel="Borrar"
          onClose={() => setConfirmOpen(false)}
          onConfirm={() => {
            setConfirmOpen(false);
            onDelete(properties.id);
          }}
        />
      ) : null}
    </Stack>
  );
});
