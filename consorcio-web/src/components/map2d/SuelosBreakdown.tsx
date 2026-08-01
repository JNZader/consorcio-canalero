/**
 * SuelosBreakdown.tsx
 *
 * Soils dataset block of the ficha: a table with clase / ha / % rows (the
 * contract, JD-A-012) plus a stacked bar as a visual complement only. The
 * server already emits the `sin dato` residual row and the `sin clasificar`
 * row and computes every `pct`, so this component never recomputes a percentage
 * from hectares — it renders what it is given (spec "Card rendering").
 *
 * Colors reuse `getSoilColor` (roman-prefix aware) from `useSoilMap` so the bar
 * matches the soil-capability palette used elsewhere on the map.
 */

import { Box, Group, Stack, Table, Text, Tooltip } from '@mantine/core';
import { memo } from 'react';

import { getSoilColor } from '../../hooks/useSoilMap';
import type { FichaDataset } from '../../lib/api/ficha';
import { DATASET_LABELS, LowConfidenceBadge, SinCobertura, fmtHa, fmtPct } from './fichaShared';

function StackedBar({ dataset }: { readonly dataset: FichaDataset }) {
  return (
    <Box
      style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden' }}
      aria-hidden="true"
      data-testid="suelos-stacked-bar"
    >
      {dataset.clases.map((clase) => (
        <Box
          key={clase.clase}
          style={{
            width: `${Math.max(0, clase.pct)}%`,
            backgroundColor: getSoilColor(clase.clase),
          }}
        />
      ))}
    </Box>
  );
}

export const SuelosBreakdown = memo(function SuelosBreakdown({
  dataset,
}: {
  readonly dataset: FichaDataset;
}) {
  const hasData = dataset.cobertura !== 'sin_cobertura' && dataset.clases.length > 0;

  return (
    <Stack gap={6} data-testid="ficha-suelos">
      <Group gap="xs" justify="space-between" wrap="nowrap">
        <Text size="sm" fw={600}>
          {DATASET_LABELS.suelos}
        </Text>
        {dataset.low_confidence && <LowConfidenceBadge pixelCount={dataset.pixel_count} />}
      </Group>

      {!hasData ? (
        <SinCobertura testId="ficha-suelos-sin-cobertura" />
      ) : (
        <>
          <StackedBar dataset={dataset} />
          <Table withRowBorders={false} verticalSpacing={2} fz="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Clase</Table.Th>
                <Table.Th ta="right">ha</Table.Th>
                <Table.Th ta="right">%</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {dataset.clases.map((clase) => (
                <Table.Tr key={clase.clase}>
                  <Table.Td>
                    {clase.detalle ? (
                      <Tooltip label={clase.detalle} withArrow>
                        <Text component="span" size="xs" style={{ borderBottom: '1px dotted' }}>
                          {clase.clase}
                        </Text>
                      </Tooltip>
                    ) : (
                      clase.clase
                    )}
                  </Table.Td>
                  <Table.Td ta="right">{fmtHa(clase.ha)}</Table.Td>
                  <Table.Td ta="right">{fmtPct(clase.pct)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  );
});
