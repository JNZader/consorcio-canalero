/**
 * FichaResumen.tsx
 *
 * Header block of the ficha: total hectares of the analysed area plus a compact
 * per-dataset coverage summary (with the low-confidence badge repeated here so
 * the state is visible before the user scrolls to the tables). Design §6.4.
 */

import { Group, Stack, Text } from '@mantine/core';
import { memo } from 'react';

import type { FichaResponse } from '../../lib/api/ficha';
import { DATASET_LABELS, LowConfidenceBadge, fmtHa } from './fichaShared';

const COBERTURA_LABEL: Record<string, string> = {
  total: 'cobertura total',
  parcial: 'cobertura parcial',
  sin_cobertura: 'sin cobertura',
};

const DATASET_ORDER = ['suelos', 'flood_risk', 'drainage_need'] as const;

export const FichaResumen = memo(function FichaResumen({ ficha }: { readonly ficha: FichaResponse }) {
  return (
    <Stack gap={4} data-testid="ficha-resumen">
      <Text size="sm">
        <Text component="span" fw={600}>
          Superficie analizada:
        </Text>{' '}
        {fmtHa(ficha.area_ha)}
      </Text>
      <Stack gap={2}>
        {DATASET_ORDER.map((key) => {
          const dataset = ficha[key];
          return (
            <Group key={key} gap="xs" wrap="nowrap">
              <Text size="xs" c="dimmed">
                {DATASET_LABELS[key]}: {COBERTURA_LABEL[dataset.cobertura] ?? dataset.cobertura}
              </Text>
              {dataset.low_confidence && <LowConfidenceBadge pixelCount={dataset.pixel_count} />}
            </Group>
          );
        })}
      </Stack>
    </Stack>
  );
});
