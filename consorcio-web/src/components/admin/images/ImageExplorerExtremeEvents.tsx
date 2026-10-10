import {
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  NativeSelect,
  Paper,
  SimpleGrid,
  Text,
  Title,
} from '@mantine/core';
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
  fired_windows?: Record<string, { peak_total_mm?: number | null }> | null;
}

export function chirpsZoneMmLine(firedWindows: unknown): string | null {
  if (!firedWindows || typeof firedWindows !== 'object') return null;
  const windows = firedWindows as Record<string, { peak_total_mm?: unknown }>;
  const mm = (key: string): number | null => {
    const value = windows[key]?.peak_total_mm;
    return typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : null;
  };
  const d1 = mm('d1');
  const d7 = mm('d7');
  if (d1 == null && d7 == null) return null;
  if (d1 != null && d7 != null) return `CHIRPS zona: ${d1} mm (1 d) – ${d7} mm (7 d)`;
  if (d1 != null) return `CHIRPS zona: ${d1} mm (1 d)`;
  return `CHIRPS zona: ${d7} mm (7 d)`;
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
  landsat9: 'L9',
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

function sceneKey(row: ImageryShortlistRow): string {
  return `${row.rank}:${row.scene_id}`;
}

function sceneLabel(row: ImageryShortlistRow): string {
  const sensor = SENSOR_SHORT[row.sensor] ?? row.sensor;
  const cloud =
    row.cloud_pct == null ? 'SAR' : `${Math.round(row.cloud_pct)}% nubes`;
  return `${row.rank}. ${sensor} ${row.scene_date} · ${cloud}`;
}

function EventShortlistPicker({
  rows,
  loading,
  onTry,
}: {
  rows: ImageryShortlistRow[];
  loading: boolean;
  onTry?: (row: ImageryShortlistRow) => void;
}) {
  const [selected, setSelected] = useState(rows[0] ? sceneKey(rows[0]) : '');
  const current = rows.find((row) => sceneKey(row) === selected) ?? rows[0];
  if (rows.length === 0) return null;
  return (
    <>
      <NativeSelect
        mt="sm"
        size="xs"
        label="Escenas ranqueadas"
        value={selected}
        onChange={(event) => setSelected(event.currentTarget.value)}
        data={rows.map((row) => ({ value: sceneKey(row), label: sceneLabel(row) }))}
      />
      <Button
        mt="xs"
        size="xs"
        fullWidth
        variant="light"
        disabled={loading || !current}
        onClick={() => {
          if (current) onTry?.(current);
        }}
      >
        Probar este
      </Button>
    </>
  );
}

export function ImageExplorerExtremeEvents({
  events,
  onLoadHistoricFlood,
  onTryShortlist,
  shortlists = {},
  loading = false,
}: ImageExplorerExtremeEventsProps) {
  const [onlyWithImagery, setOnlyWithImagery] = useState(false);

  const visibleEvents = useMemo(() => {
    const filtered = onlyWithImagery ? events.filter(isImageryEligible) : events;
    return [...filtered].sort((a, b) => b.date.localeCompare(a.date));
  }, [events, onlyWithImagery]);

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
        label="Solo con imagen Sentinel"
        checked={onlyWithImagery}
        onChange={(event) => setOnlyWithImagery(event.currentTarget.checked)}
        mb="sm"
        size="sm"
      />
      <SimpleGrid cols={1} style={{ maxHeight: 480, overflow: 'auto' }}>
        {visibleEvents.map((flood) => {
          const canSearch = isImageryEligible(flood);
          const mmLine = chirpsZoneMmLine(flood.fired_windows);
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
              {mmLine ? (
                <Text size="xs" mt={4}>
                  {mmLine}
                </Text>
              ) : null}
              {flood.imagery_note ? (
                <Text size="xs" mt={4}>
                  {flood.imagery_note}
                </Text>
              ) : null}
              <EventShortlistPicker
                rows={shortlists[flood.id] ?? []}
                loading={loading}
                onTry={onTryShortlist}
              />
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
