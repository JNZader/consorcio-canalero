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
 *
 * T3a, fix 1a — each row also leads with a `ClassColorChip` painted by that same
 * `getSoilColor`, so this table doubles as the legend for the clipped on-map
 * overlay (`fichaOverlayLayers` uses the identical palette).
 */

import { Box, Group, Stack, Table, Text, Tooltip } from '@mantine/core';
import { memo } from 'react';

import { getSoilColor } from '../../hooks/useSoilMap';
import type { FichaDataset } from '../../lib/api/ficha';
import {
  ClassToggleCell,
  DATASET_LABELS,
  LowConfidenceBadge,
  SinCobertura,
  fmtHa,
  fmtPct,
} from './fichaShared';

const NO_HIDDEN_CLASES: readonly string[] = [];

function StackedBar({
  dataset,
  hiddenClases,
}: {
  readonly dataset: FichaDataset;
  readonly hiddenClases: readonly string[];
}) {
  return (
    <Box
      style={{
        display: 'flex',
        height: 8,
        borderRadius: 4,
        overflow: 'hidden',
      }}
      aria-hidden="true"
      data-testid="suelos-stacked-bar"
    >
      {dataset.clases.map((clase) => (
        <Box
          key={clase.clase}
          style={{
            width: `${Math.max(0, clase.pct)}%`,
            backgroundColor: getSoilColor(clase.clase),
            // Mirrors the table: a class turned off is not painted on the map.
            opacity: hiddenClases.includes(clase.clase) ? 0.25 : 1,
          }}
        />
      ))}
    </Box>
  );
}

export const SuelosBreakdown = memo(function SuelosBreakdown({
  dataset,
  hiddenClases = NO_HIDDEN_CLASES,
  onToggleClase,
}: {
  readonly dataset: FichaDataset;
  /**
   * Soil classes currently NOT painted on the map (T3b, fix 3). The overlay's
   * soils features carry the SAME `properties.clase` labels this table renders,
   * so a row label is a valid filter value with no translation step.
   */
  readonly hiddenClases?: readonly string[];
  /** Toggles one class in the painted overlay. Omitted → static table. */
  readonly onToggleClase?: (clase: string) => void;
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
          <StackedBar dataset={dataset} hiddenClases={hiddenClases} />
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
                    <ClassToggleCell
                      color={getSoilColor(clase.clase)}
                      clase={clase.clase}
                      hidden={hiddenClases.includes(clase.clase)}
                      onToggle={onToggleClase}
                      chipTestId={`ficha-suelos-chip-${clase.clase}`}
                      rowTestId={`ficha-suelos-row-${clase.clase}`}
                    >
                      {clase.detalle ? (
                        <Tooltip label={clase.detalle} withArrow>
                          <Text component="span" size="xs" style={{ borderBottom: '1px dotted' }}>
                            {clase.clase}
                          </Text>
                        </Tooltip>
                      ) : (
                        <Text component="span" size="xs">
                          {clase.clase}
                        </Text>
                      )}
                    </ClassToggleCell>
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
