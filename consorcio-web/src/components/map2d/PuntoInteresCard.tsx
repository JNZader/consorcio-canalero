import { Button, Stack, Text, Title } from '@mantine/core';
import { memo } from 'react';

import {
  PUNTO_INTERES_TIPO_LABELS,
  type PuntoInteresProperties,
} from '../../lib/api/puntosInteres';

export interface PuntoInteresCardProps {
  readonly properties: PuntoInteresProperties;
  readonly onDelete?: (id: string) => void;
}

export const PuntoInteresCard = memo(function PuntoInteresCard({
  properties,
  onDelete,
}: PuntoInteresCardProps) {
  const tipoLabel = PUNTO_INTERES_TIPO_LABELS[properties.tipo] ?? properties.tipo;

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
          onClick={() => onDelete(properties.id)}
        >
          Borrar
        </Button>
      ) : null}
    </Stack>
  );
});
