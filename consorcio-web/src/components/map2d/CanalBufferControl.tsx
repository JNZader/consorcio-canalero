/**
 * CanalBufferControl — the canal analysis control for `'ficha-canal'` mode (A6 + A7).
 *
 * A header section rendered at the TOP of `FichaTerritorialPanel` (like
 * `ParcelaIdentityHeader` is for a parcel) whenever the analyzed tipo is
 * `canal_buffer` or `canal_cuenca`. It shows which curated consorcio canal is
 * active (by name) and lets the user choose HOW to analyze it with a segmented
 * control:
 *   - "Zona de influencia" → a fixed-width buffer strip (`tipo=canal_buffer`);
 *   - "Cuenca"             → the real upstream catchment (`tipo=canal_cuenca`).
 *
 * In buffer mode a distance input dials the influence-strip half-width in metres;
 * the value is committed (and the ficha request re-fired) ONLY on blur or Enter —
 * never per keystroke — so typing "1500" fires one request, not four
 * self-rate-limiting ones. In cuenca mode there is no distance to pick (the
 * catchment is precomputed), so the input is hidden.
 *
 * Living INSIDE the ficha panel (instead of a separate floating card) keeps the
 * mode toggle reachable in every ficha state — loading, error (including the
 * `cuenca_no_computada` 503, so the user can switch back to buffer) and result —
 * because the header renders above the analysis body regardless of fetch status.
 *
 * Pure presentational component — it owns no state beyond the buffer draft. The
 * selected canal, current buffer and analysis mode live in `useFichaInteraction`;
 * the max is the wire cap (`FICHA_MAX_BUFFER_M`) so the input can never request a
 * value the server would reject with 422 `cap_excedido`. Closing the panel is
 * owned by the ficha panel's own close button, so this header has none.
 */

import { Group, NumberInput, SegmentedControl, Stack, Text } from '@mantine/core';
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
}

export const CanalBufferControl = memo(function CanalBufferControl({
  canalNombre,
  analysisMode,
  onAnalysisModeChange,
  bufferM,
  maxBufferM,
  onBufferChange,
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
    <Stack gap={6} data-testid="canal-buffer-control">
      <Group gap={6} wrap="nowrap">
        <IconRoute size={16} color="#06b6d4" />
        <Text size="sm" fw={600} lineClamp={1} title={canalNombre}>
          {canalNombre}
        </Text>
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
  );
});
