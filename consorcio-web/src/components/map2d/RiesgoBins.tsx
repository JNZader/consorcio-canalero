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
import { ClassToggleCell, LowConfidenceBadge, SinCobertura, fmtHa, fmtPct } from './fichaShared';

/** Which legend the class labels are resolved against — the overlay dataset key. */
export type RiesgoLegendKey = 'flood_risk' | 'drainage_need';

function SeverityBar({
  dataset,
  legendKey,
  hiddenClases,
}: {
  readonly dataset: FichaDataset;
  readonly legendKey: RiesgoLegendKey;
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
            // A class turned off in the table is not painted on the map, so
            // the complement bar fades with it — the widths stay put because
            // the percentages are facts about the analysis, not about paint.
            opacity: hiddenClases.includes(clase.clase) ? 0.25 : 1,
          }}
        />
      ))}
    </Box>
  );
}

const NO_HIDDEN_CLASES: readonly string[] = [];

export const RiesgoBins = memo(function RiesgoBins({
  label,
  dataset,
  legendKey,
  testId,
  hiddenClases = NO_HIDDEN_CLASES,
  onToggleClase,
}: {
  readonly label: string;
  readonly dataset: FichaDataset;
  /** Dataset key used to resolve each class label to the overlay's color. */
  readonly legendKey: RiesgoLegendKey;
  readonly testId: string;
  /**
   * Classes currently NOT painted on the map (T3b, fix 3). Their rows render
   * dimmed with a hollow chip. Empty (the default) = every class is painted.
   */
  readonly hiddenClases?: readonly string[];
  /**
   * Toggles one class in the painted overlay. Omitted, the table stays static —
   * this component is also mounted in contexts with no overlay to drive.
   */
  readonly onToggleClase?: (clase: string) => void;
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
          <SeverityBar dataset={dataset} legendKey={legendKey} hiddenClases={hiddenClases} />
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
                      color={riesgoClassColor(legendKey, clase.clase)}
                      clase={clase.clase}
                      hidden={hiddenClases.includes(clase.clase)}
                      onToggle={onToggleClase}
                      chipTestId={`${testId}-chip-${clase.clase}`}
                      rowTestId={`${testId}-row-${clase.clase}`}
                    >
                      <Text component="span" size="xs">
                        {clase.clase}
                      </Text>
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
