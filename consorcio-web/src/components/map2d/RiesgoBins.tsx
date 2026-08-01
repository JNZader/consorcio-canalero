/**
 * RiesgoBins.tsx
 *
 * Renders one risk/need dataset (`flood_risk` or `drainage_need`) as a table
 * with clase / ha / % rows per bin (the contract) plus a colored severity bar
 * as a visual complement. Percentages are rendered from the server, never
 * recomputed from hectares (spec "Card rendering").
 *
 * The bar color is a green→red severity ramp indexed by bin order — it is
 * decoration for the table, not a data source, so a simple deterministic ramp
 * is honest here (the real `class_breaks` colors live server-side).
 */

import { Box, Group, Stack, Table, Text } from '@mantine/core';
import { memo } from 'react';

import type { FichaDataset } from '../../lib/api/ficha';
import { LowConfidenceBadge, SinCobertura, fmtHa, fmtPct } from './fichaShared';

/** Green (low) → red (high) severity ramp for the complement bar. */
const SEVERITY_RAMP = ['#2e7d32', '#9ccc65', '#f9a825', '#fb8c00', '#e53935'] as const;

function severityColor(index: number, total: number): string {
  if (total <= 1) return SEVERITY_RAMP[0];
  const pos = Math.round((index / (total - 1)) * (SEVERITY_RAMP.length - 1));
  return SEVERITY_RAMP[Math.min(pos, SEVERITY_RAMP.length - 1)];
}

function SeverityBar({ dataset }: { readonly dataset: FichaDataset }) {
  const total = dataset.clases.length;
  return (
    <Box
      style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden' }}
      aria-hidden="true"
      data-testid="riesgo-severity-bar"
    >
      {dataset.clases.map((clase, index) => (
        <Box
          key={clase.clase}
          style={{
            width: `${Math.max(0, clase.pct)}%`,
            backgroundColor: severityColor(index, total),
          }}
        />
      ))}
    </Box>
  );
}

export const RiesgoBins = memo(function RiesgoBins({
  label,
  dataset,
  testId,
}: {
  readonly label: string;
  readonly dataset: FichaDataset;
  readonly testId: string;
}) {
  const hasData = dataset.cobertura !== 'sin_cobertura' && dataset.clases.length > 0;

  return (
    <Stack gap={6} data-testid={testId}>
      <Group gap="xs" justify="space-between" wrap="nowrap">
        <Text size="sm" fw={600}>
          {label}
        </Text>
        {dataset.low_confidence && <LowConfidenceBadge pixelCount={dataset.pixel_count} />}
      </Group>

      {!hasData ? (
        <SinCobertura testId={`${testId}-sin-cobertura`} />
      ) : (
        <>
          <SeverityBar dataset={dataset} />
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
                  <Table.Td>{clase.clase}</Table.Td>
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
