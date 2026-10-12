import {
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  NativeSelect,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Text,
  Title,
} from '@mantine/core';
import { useEffect, useMemo, useState } from 'react';

import { apiFetch, GEE_TIMEOUT } from '../../../lib/api';
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

export interface ImageryPair {
  pre: ImageryShortlistRow | null;
  post: ImageryShortlistRow | null;
}

export type WaterDeltaPayload = {
  comparable: boolean;
  reason?: string | null;
  delta_ha?: number;
  pre?: { water_ha?: number | null; scene_date: string; sensor: string; tile_url?: string | null };
  post?: { water_ha?: number | null; scene_date: string; sensor: string; tile_url?: string | null };
};

export function formatWaterDelta(payload: WaterDeltaPayload): string {
  if (payload.comparable && payload.delta_ha != null) {
    const sign = payload.delta_ha > 0 ? '+' : '';
    return `Δ agua: ${sign}${payload.delta_ha} ha (${payload.pre?.water_ha ?? '—'} → ${payload.post?.water_ha ?? '—'})`;
  }
  if (payload.reason === 'not_optical') return 'Δ agua: hace falta par óptico (no SAR)';
  if (payload.reason === 'missing_pair') return 'Δ agua: falta Antes o Después';
  if (payload.reason === 'scene_unavailable') return 'Δ agua: no se pudo medir la escena';
  return 'Δ agua: no comparable';
}

export function opticalShortlist(rows: ImageryShortlistRow[]): ImageryShortlistRow[] {
  return rows.filter((row) => row.sensor !== 'sentinel1');
}

export function defaultOpticalPair(
  rows: ImageryShortlistRow[]
): { pre: string; post: string } | null {
  const unique = new Map<string, ImageryShortlistRow>();
  for (const row of opticalShortlist(rows)) {
    unique.set(row.scene_id, row);
  }
  const sorted = [...unique.values()].sort(
    (a, b) => a.scene_date.localeCompare(b.scene_date) || a.scene_id.localeCompare(b.scene_id)
  );
  if (sorted.length < 2) return null;
  return { pre: sorted[0].scene_id, post: sorted[sorted.length - 1].scene_id };
}

interface ImageExplorerExtremeEventsProps {
  events: HistoricFloodEvent[];
  onLoadHistoricFlood: (floodId: string) => void;
  onTryShortlist?: (row: ImageryShortlistRow) => void;
  shortlists?: Record<string, ImageryShortlistRow[]>;
  pairs?: Record<string, ImageryPair>;
  loading?: boolean;
  onShowWaterMask?: (tileUrl: string | null) => void;
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
  const cloud = row.cloud_pct == null ? 'SAR' : `${Math.round(row.cloud_pct)}% nubes`;
  return `${row.rank}. ${sensor} ${row.scene_date} · ${cloud}`;
}

function WaterMaskButtons({
  delta,
  onShowWaterMask,
}: {
  delta: WaterDeltaPayload;
  onShowWaterMask?: (tileUrl: string | null) => void;
}) {
  const preUrl = delta.pre?.tile_url ?? null;
  const postUrl = delta.post?.tile_url ?? null;
  const [slot, setSlot] = useState<'off' | 'pre' | 'post'>(postUrl ? 'post' : preUrl ? 'pre' : 'off');
  useEffect(() => {
    setSlot(postUrl ? 'post' : preUrl ? 'pre' : 'off');
  }, [preUrl, postUrl]);
  if (!preUrl && !postUrl) return null;
  const options = [
    { value: 'off', label: 'Sin máscara' },
    ...(preUrl ? [{ value: 'pre', label: 'Antes' }] : []),
    ...(postUrl ? [{ value: 'post', label: 'Después' }] : []),
  ];
  return (
    <>
      <SegmentedControl
        mt="xs"
        fullWidth
        size="xs"
        aria-label="Máscara de agua"
        value={slot}
        data={options}
        onChange={(value) => {
          const next = value === 'pre' || value === 'post' ? value : 'off';
          setSlot(next);
          if (next === 'pre') onShowWaterMask?.(preUrl);
          else if (next === 'post') onShowWaterMask?.(postUrl);
          else onShowWaterMask?.(null);
        }}
      />
      <Text size="xs" c="dimmed" mt={6}>
        Azul = agua (MNDWI ≥ 0.1). Se apaga al cambiar de escena.
      </Text>
    </>
  );
}

function OpticalDeltaControls({
  floodId,
  optical,
  pick,
  loading,
  measuringId,
  onChange,
  onStart,
  onMeasured,
}: {
  floodId: string;
  optical: ImageryShortlistRow[];
  pick: { pre: string; post: string };
  loading: boolean;
  measuringId: string | null;
  onChange: (next: { pre: string; post: string }) => void;
  onStart: () => void;
  onMeasured: (payload: WaterDeltaPayload | 'error') => void;
}) {
  const options = optical.map((row) => ({ value: row.scene_id, label: sceneLabel(row) }));
  return (
    <>
      <NativeSelect
        mt="sm"
        size="xs"
        label="Antes (óptico)"
        value={pick.pre}
        onChange={(event) => onChange({ pre: event.currentTarget.value, post: pick.post })}
        data={options}
      />
      <NativeSelect
        mt="xs"
        size="xs"
        label="Después (óptico)"
        value={pick.post}
        onChange={(event) => onChange({ pre: pick.pre, post: event.currentTarget.value })}
        data={options}
      />
      <Button
        mt="xs"
        size="xs"
        fullWidth
        variant="light"
        disabled={loading || measuringId === floodId || pick.pre === pick.post}
        onClick={() => {
          onStart();
          const query = new URLSearchParams({
            pre_scene_id: pick.pre,
            post_scene_id: pick.post,
          });
          void apiFetch<WaterDeltaPayload>(
            `/geo/gee/images/historic-floods/${floodId}/water-delta?${query.toString()}`,
            { timeout: GEE_TIMEOUT }
          )
            .then((payload) => onMeasured(payload))
            .catch(() => onMeasured('error'));
        }}
      >
        {measuringId === floodId ? 'Midiendo agua…' : 'Medir Δ agua'}
      </Button>
    </>
  );
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
  pairs = {},
  loading = false,
  onShowWaterMask,
}: ImageExplorerExtremeEventsProps) {
  const [onlyWithImagery, setOnlyWithImagery] = useState(false);
  const [waterDeltas, setWaterDeltas] = useState<Record<string, WaterDeltaPayload | 'error'>>({});
  const [measuringId, setMeasuringId] = useState<string | null>(null);
  const [deltaPick, setDeltaPick] = useState<Record<string, { pre: string; post: string }>>({});

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
        CHIRPS ordena de forma relativa, no en milímetros. Probar este usa la escena ya ranqueada;
        Buscar imagen arma el compuesto. Después publicá con Usar esta imagen.
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
          const pair = pairs[flood.id];
          const pre = pair?.pre ?? null;
          const post = pair?.post ?? null;
          const ranked = shortlists[flood.id] ?? [];
          const optical = opticalShortlist(ranked);
          const autoPair = defaultOpticalPair(optical);
          const pick = deltaPick[flood.id] ?? autoPair;
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
              {pre ? (
                <Button
                  mt="sm"
                  size="xs"
                  fullWidth
                  variant="outline"
                  disabled={loading}
                  onClick={() => onTryShortlist?.(pre)}
                >
                  Antes · {SENSOR_SHORT[pre.sensor] ?? pre.sensor} {pre.scene_date}
                </Button>
              ) : null}
              {post ? (
                <Button
                  mt="xs"
                  size="xs"
                  fullWidth
                  variant="outline"
                  disabled={loading}
                  onClick={() => onTryShortlist?.(post)}
                >
                  Después · {SENSOR_SHORT[post.sensor] ?? post.sensor} {post.scene_date}
                </Button>
              ) : null}
              <EventShortlistPicker
                rows={shortlists[flood.id] ?? []}
                loading={loading}
                onTry={onTryShortlist}
              />
              {autoPair && pick ? (
                <OpticalDeltaControls
                  floodId={flood.id}
                  optical={optical}
                  pick={pick}
                  loading={loading}
                  measuringId={measuringId}
                  onChange={(next) => {
                    setDeltaPick((current) => ({ ...current, [flood.id]: next }));
                  }}
                  onStart={() => setMeasuringId(flood.id)}
                  onMeasured={(payload) => {
                    setWaterDeltas((current) => ({ ...current, [flood.id]: payload }));
                    setMeasuringId((current) => (current === flood.id ? null : current));
                    if (payload !== 'error' && payload.comparable) {
                      const maskUrl = payload.post?.tile_url ?? payload.pre?.tile_url;
                      if (maskUrl) onShowWaterMask?.(maskUrl);
                    }
                  }}
                />
              ) : null}
              {waterDeltas[flood.id] && waterDeltas[flood.id] !== 'error' ? (
                <Text size="xs" mt={4} data-testid="water-delta-line">
                  {formatWaterDelta(waterDeltas[flood.id] as WaterDeltaPayload)}
                </Text>
              ) : null}
              {waterDeltas[flood.id] && waterDeltas[flood.id] !== 'error' ? (
                <WaterMaskButtons
                  delta={waterDeltas[flood.id] as WaterDeltaPayload}
                  onShowWaterMask={onShowWaterMask}
                />
              ) : null}
              {waterDeltas[flood.id] === 'error' ? (
                <Text size="xs" mt={4} c="red">
                  Δ agua: error al medir
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
