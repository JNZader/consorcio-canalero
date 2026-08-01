/**
 * CanalBufferControl — the buffer-distance input for `tipo=canal_buffer` (A6).
 *
 * A small floating control that appears once the user has selected a canal in
 * `'ficha-canal'` mode. It shows which canal is active and lets the user dial the
 * influence-strip half-width in metres; the value is committed (and the ficha
 * request re-fired) ONLY on blur or Enter — never per keystroke — so typing
 * "1500" fires one `tipo=canal_buffer` request, not four self-rate-limiting ones
 * (the container threads `onBufferChange` to `useFichaInteraction.setBuffer`).
 *
 * Pure presentational component — it owns no state. The selected canal + current
 * buffer live in `useFichaInteraction`; the max is the wire cap
 * (`FICHA_MAX_BUFFER_M`) so the input can never request a value the server would
 * reject with 422 `cap_excedido`.
 */

import { Box, CloseButton, Group, NumberInput, Stack, Text } from '@mantine/core';
import { memo, useEffect, useState } from 'react';

import { IconRoute } from '../ui/icons';

export interface CanalBufferControlProps {
  readonly canalId: number;
  readonly bufferM: number;
  readonly maxBufferM: number;
  readonly onBufferChange: (bufferM: number) => void;
  readonly onClose: () => void;
}

export const CanalBufferControl = memo(function CanalBufferControl({
  canalId,
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
        width: 210,
      }}
    >
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap">
          <Group gap={6} wrap="nowrap">
            <IconRoute size={16} color="#06b6d4" />
            <Text size="sm" fw={600}>
              Canal #{canalId}
            </Text>
          </Group>
          <CloseButton size="sm" aria-label="Cerrar selección de canal" onClick={onClose} />
        </Group>
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
      </Stack>
    </Box>
  );
});
