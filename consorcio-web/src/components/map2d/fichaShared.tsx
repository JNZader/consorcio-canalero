/**
 * Shared presentational atoms for the ficha territorial card tree.
 *
 * Kept tiny and dependency-light so `FichaResumen`, `SuelosBreakdown` and
 * `RiesgoBins` render identical badges / labels / number formats without
 * duplicating them.
 */

import { Badge, Text, Tooltip } from '@mantine/core';

export const DATASET_LABELS = {
  suelos: 'Suelos',
  flood_risk: 'Riesgo de inundación',
  drainage_need: 'Necesidad de drenaje',
} as const;

/** Hectares with one decimal. Numbers come from the server; only the display is ours. */
export function fmtHa(value: number): string {
  return `${value.toFixed(1)} ha`;
}

/**
 * Percentages are rendered from the server value at a fixed precision and are
 * NEVER recomputed client-side from hectares (spec "Card rendering").
 */
export function fmtPct(value: number): string {
  return `${value.toFixed(1)}%`;
}

/**
 * Visible badge shown next to a dataset that reports `low_confidence: true`:
 * the area is small relative to the 30 m raster so the percentages are
 * approximate (spec "Low-confidence badge").
 */
export function LowConfidenceBadge({ pixelCount }: { readonly pixelCount: number }) {
  return (
    <Tooltip
      multiline
      w={240}
      label={`El área es chica frente a la resolución del raster (30 m): sólo ${pixelCount} píxeles la cubren, así que los porcentajes son aproximados.`}
    >
      <Badge size="xs" color="yellow" variant="light" data-testid="ficha-low-confidence">
        Baja confianza
      </Badge>
    </Tooltip>
  );
}

/**
 * Explicit "sin cobertura" line for a dataset the raster did not cover. NOT a
 * `0 %` row and NOT an empty table (spec "No coverage is not zero").
 */
export function SinCobertura({ testId }: { readonly testId?: string }) {
  return (
    <Text size="xs" c="dimmed" fs="italic" data-testid={testId ?? 'ficha-sin-cobertura'}>
      Sin cobertura de datos en esta zona.
    </Text>
  );
}
