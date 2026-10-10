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

export interface ImageryShortlistRow {
  rank: number;
  sensor: string;
  scene_id: string;
  scene_date: string;
  days_from_peak: number;
  cloud_pct: number | null;
  score: number;
  visualization: string;
}

interface ImageExplorerExtremeEventsProps {
  events: HistoricFloodEvent[];
  onLoadHistoricFlood: (floodId: string) => void;
  onTryShortlist?: (row: ImageryShortlistRow) => void;
  shortlists?: Record<string, ImageryShortlistRow[]>;
  loading?: boolean;
}

const SENSOR_SHORT: Record<string, string> = {
  sentinel1: 'S1',
  sentinel2: 'S2',
  landsat8: 'L8',
  landsat7: 'L7',
  landsat5: 'L5',
};

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
  onTryShortlist,
  shortlists = {},
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
        CHIRPS ordena de forma relativa, no en milímetros. Probar este usa la escena ya
        ranqueada; Buscar imagen arma el compuesto. Después publicá con Usar esta imagen.
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
              {(shortlists[flood.id] ?? []).map((row) => {
                const label = `Probar este · ${SENSOR_SHORT[row.sensor] ?? row.sensor} · ${row.scene_date}`;
                return (
                  <Button
                    key={`${row.scene_id}-${row.rank}`}
                    mt="sm"
                    size="xs"
                    fullWidth
                    variant="light"
                    disabled={loading}
                    onClick={() => onTryShortlist?.(row)}
                  >
                    {label}
                  </Button>
                );
              })}
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
