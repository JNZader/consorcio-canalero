import { Badge, Button, Card, Checkbox, Group, Paper, SimpleGrid, Text, Title } from '@mantine/core';
import { useMemo, useState } from 'react';

import { IconPhoto } from '../../ui/icons';

export interface HistoricFloodEvent {
  id: string;
  name: string;
  date: string;
  description?: string;
  severity?: string;
  imagery_candidate?: boolean;
  imagery_note?: string;
}

interface ImageExplorerExtremeEventsProps {
  events: HistoricFloodEvent[];
  onLoadHistoricFlood: (floodId: string) => void;
  loading?: boolean;
}

function isImageryEligible(event: HistoricFloodEvent): boolean {
  return event.imagery_candidate !== false;
}

function severityColor(severity: string): string {
  if (severity === 'alta') return 'red';
  if (severity === 'media') return 'orange';
  return 'yellow';
}

export function ImageExplorerExtremeEvents({
  events,
  onLoadHistoricFlood,
  loading = false,
}: ImageExplorerExtremeEventsProps) {
  const [showWithoutImagery, setShowWithoutImagery] = useState(false);

  const visibleEvents = useMemo(() => {
    const filtered = showWithoutImagery ? events : events.filter(isImageryEligible);
    return [...filtered].sort((a, b) => b.date.localeCompare(a.date));
  }, [events, showWithoutImagery]);

  if (events.length === 0) return null;

  return (
    <Paper p="md" withBorder radius="md">
      <Title order={5} mb="xs">
        <Group gap="xs">
          <IconPhoto size={20} />
          Eventos de lluvia extrema
        </Group>
      </Title>
      <Text size="xs" c="dimmed" mb="sm">
        CHIRPS ordena de forma relativa, no en milímetros. Elegí un evento, buscá la imagen y
        publicá con Usar esta imagen.
      </Text>
      <Checkbox
        label="Mostrar sin imagen satelital"
        checked={showWithoutImagery}
        onChange={(event) => setShowWithoutImagery(event.currentTarget.checked)}
        mb="sm"
        size="sm"
      />
      <SimpleGrid cols={1} style={{ maxHeight: 480, overflow: 'auto' }}>
        {visibleEvents.map((flood) => {
          const canSearch = isImageryEligible(flood);
          return (
            <Card key={`${flood.id}-${flood.date}`} padding="sm" radius="md" withBorder>
              <Group justify="space-between" mb="xs" wrap="nowrap">
                <Text fw={500}>{flood.name}</Text>
                <Badge color={severityColor(flood.severity ?? '')} size="sm">
                  {flood.severity ?? ''}
                </Badge>
              </Group>
              <Text size="sm" c="dimmed">
                {flood.description ?? ''}
              </Text>
              <Text size="xs" c="dimmed" mt="xs">
                {flood.date}
              </Text>
              {flood.imagery_note ? (
                <Text size="xs" mt={4}>
                  {flood.imagery_note}
                </Text>
              ) : null}
              <Button
                mt="sm"
                size="xs"
                fullWidth
                disabled={!canSearch || loading}
                onClick={() => {
                  if (!canSearch) return;
                  onLoadHistoricFlood(flood.id);
                }}
              >
                {canSearch ? 'Buscar imagen' : 'Sin imagen satelital útil'}
              </Button>
            </Card>
          );
        })}
      </SimpleGrid>
    </Paper>
  );
}
