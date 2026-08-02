/**
 * CanalBufferControl — the canal analysis control for `'ficha-canal'` mode (A6 + A7).
 *
 * A small floating control that appears once the user has selected a CURATED
 * consorcio canal. It shows which canal is active (by name) and lets the user
 * choose HOW to analyze it with a segmented control:
 *   - "Zona de influencia" → a fixed-width buffer strip (`tipo=canal_buffer`);
 *   - "Cuenca"             → the real upstream catchment (`tipo=canal_cuenca`).
 *
 * In buffer mode a distance input dials the influence-strip half-width in metres;
 * the value is committed (and the ficha request re-fired) ONLY on blur or Enter —
 * never per keystroke — so typing "1500" fires one request, not four
 * self-rate-limiting ones. In cuenca mode there is no distance to pick (the
 * catchment is precomputed), so the input is hidden.
 *
 * Pure presentational component — it owns no state beyond the buffer draft. The
 * selected canal, current buffer and analysis mode live in `useFichaInteraction`;
 * the max is the wire cap (`FICHA_MAX_BUFFER_M`) so the input can never request a
 * value the server would reject with 422 `cap_excedido`.
 */

import { Box, CloseButton, Group, NumberInput, SegmentedControl, Stack, Text } from '@mantine/core';
import { memo, useEffect, useState } from 'react';

import type { CanalAnalysisMode } from './useFichaInteraction';
import { IconRoute } from '../ui/icons';

export interface CanalBufferControlProps {
  readonly canalNombre: string;
  readonly analysisMode: CanalAnalysisMode;
  readonly onAnalysisModeChange: (mode: CanalAnalysisMode) => void;
  readonly bufferM: number;
  readonly maxBufferM: number;
  readonly onBufferChange: (bufferM: number) => void;
  readonly onClose: () => void;
}

export const CanalBufferControl = memo(function CanalBufferControl({
  canalNombre,
  analysisMode,
  onAnalysisModeChange,
  bufferM,
  maxBufferM,
  onBufferChange,
  onClose,
}: CanalBufferControlProps) {
  // Local draft: the committed `bufferM` prop stays the source of truth. Typing
  // only mutates the draft; nothing fires until blur or Enter.
  const [draft, setDraft] = useState<number | string>(bufferM);

  // Re-sync when the committed value changes upstream (e.g. a different canal is
  // picked, or setBuffer clamps the committed value).
  useEffect(() => {
    setDraft(bufferM);
  }, [bufferM]);

  const commit = () => {
    const next = typeof draft === 'number' ? draft : Number(draft);
    if (Number.isFinite(next) && next >= 1) {
      const clamped = Math.min(next, maxBufferM);
      setDraft(clamped);
      if (clamped !== bufferM) onBufferChange(clamped);
    } else {
      // Invalid draft (empty, NaN, < 1): discard it, snap back to the committed value.
      setDraft(bufferM);
    }
  };

  return (
    <Box
      data-testid="canal-buffer-control"
      style={{
        position: 'absolute',
        top: 180,
        right: 50,
        zIndex: 16,
        background: 'rgba(255,255,255,0.96)',
        borderRadius: 6,
        padding: '10px 12px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
        width: 240,
      }}
    >
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap">
          <Group gap={6} wrap="nowrap">
            <IconRoute size={16} color="#06b6d4" />
            <Text size="sm" fw={600} lineClamp={1} title={canalNombre}>
              {canalNombre}
            </Text>
          </Group>
          <CloseButton size="sm" aria-label="Cerrar selección de canal" onClick={onClose} />
        </Group>

        <SegmentedControl
          size="xs"
          fullWidth
          value={analysisMode}
          onChange={(value) => onAnalysisModeChange(value as CanalAnalysisMode)}
          data={[
            { value: 'buffer', label: 'Zona de influencia' },
            { value: 'cuenca', label: 'Cuenca' },
          ]}
          aria-label="Tipo de análisis del canal"
        />

        {analysisMode === 'buffer' ? (
          <>
            <NumberInput
              label="Distancia de influencia (m)"
              aria-label="Distancia de influencia en metros"
              value={draft}
              min={1}
              max={maxBufferM}
              step={100}
              clampBehavior="strict"
              allowNegative={false}
              onChange={setDraft}
              onBlur={commit}
              onKeyDown={(event) => {
                if (event.key === 'Enter') commit();
              }}
            />
            <Text size="xs" c="dimmed">
              Máximo {maxBufferM} m a cada lado del canal.
            </Text>
          </>
        ) : (
          <Text size="xs" c="dimmed">
            Cuenca de aporte real del canal (aguas arriba).
          </Text>
        )}
      </Stack>
    </Box>
  );
});
