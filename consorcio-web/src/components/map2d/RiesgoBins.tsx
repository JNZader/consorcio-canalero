/**
 * RiesgoBins.tsx
 *
 * Renders one risk/need dataset (`flood_risk` or `drainage_need`) as a table
 * with clase / ha / % rows per bin (the contract) plus a colored bar as a visual
 * complement. Percentages are rendered from the server, never recomputed from
 * hectares (spec "Card rendering").
 *
 * T3a, fix 1a — THE TABLE IS THE OVERLAY'S LEGEND. Each row leads with a color
 * chip and the complement bar uses those same colors. Every color comes from
 * `riesgoClassColor`, the SAME lookup `fichaOverlayLayers` paints the on-map
 * overlay with (`LAYER_LEGEND_CONFIG[dataset].ranges`, label → color). The old
 * decorative green→red `SEVERITY_RAMP` is gone: a second palette sitting right
 * above the legend is exactly what made the owner read matching percentages as
 * wrong.
 */

import { Box, Group, Stack, Table, Text } from '@mantine/core';
import { memo } from 'react';

import type { FichaDataset } from '../../lib/api/ficha';
import { riesgoClassColor } from './fichaOverlayLayers';
import { ClassColorChip, LowConfidenceBadge, SinCobertura, fmtHa, fmtPct } from './fichaShared';

/** Which legend the class labels are resolved against — the overlay dataset key. */
export type RiesgoLegendKey = 'flood_risk' | 'drainage_need';

function SeverityBar({
  dataset,
  legendKey,
}: {
  readonly dataset: FichaDataset;
  readonly legendKey: RiesgoLegendKey;
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
      data-testid="riesgo-severity-bar"
    >
      {dataset.clases.map((clase) => (
        <Box
          key={clase.clase}
          style={{
            width: `${Math.max(0, clase.pct)}%`,
            backgroundColor: riesgoClassColor(legendKey, clase.clase),
            // Same hairline the row chips carry. Several legend colors are
            // near-white (drainage "Bajo" is #fff7ec) and the panel background
            // is near-white too, so an unbordered segment read as a BLANK HOLE
            // in the bar. An INSET shadow rather than a border: a border would
            // add to each segment's box and make the percentage widths (which
            // must sum to 100%) overflow.
            boxShadow: 'inset 0 0 0 1px rgba(0, 0, 0, 0.2)',
          }}
        />
      ))}
    </Box>
  );
}

export const RiesgoBins = memo(function RiesgoBins({
  label,
  dataset,
  legendKey,
  testId,
}: {
  readonly label: string;
  readonly dataset: FichaDataset;
  /** Dataset key used to resolve each class label to the overlay's color. */
  readonly legendKey: RiesgoLegendKey;
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
          <SeverityBar dataset={dataset} legendKey={legendKey} />
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
                    <Group gap={6} wrap="nowrap">
                      <ClassColorChip
                        color={riesgoClassColor(legendKey, clase.clase)}
                        testId={`${testId}-chip-${clase.clase}`}
                      />
                      <Text component="span" size="xs">
                        {clase.clase}
                      </Text>
                    </Group>
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
