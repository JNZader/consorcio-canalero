/**
 * Shared presentational atoms for the ficha territorial card tree.
 *
 * Kept tiny and dependency-light so `FichaResumen`, `SuelosBreakdown` and
 * `RiesgoBins` render identical badges / labels / number formats without
 * duplicating them.
 */

import { Badge, Box, Group, Text, Tooltip, UnstyledButton } from '@mantine/core';
import type { ReactNode } from 'react';

export const DATASET_LABELS = {
  suelos: 'Suelos',
  flood_risk: 'Riesgo de inundación',
  drainage_need: 'Necesidad de drenaje',
} as const;

/**
 * Color chip rendered at the start of every class row in the ficha tables
 * (T3a, fix 1a).
 *
 * The on-map overlay paints one color per class, but nothing on screen said WHICH
 * color meant which class: the owner read matching percentages as wrong because
 * the painted classes had no legend. The tables now ARE that legend — the chip's
 * color MUST come from the same source the overlay paints with
 * (`riesgoClassColor` / `getSoilColor`), never from a chip-local palette.
 */
export const CLASS_CHIP_SIZE = 12;

export function ClassColorChip({
  color,
  testId,
  hollow = false,
}: {
  readonly color: string;
  readonly testId?: string;
  /**
   * Class currently HIDDEN from the painted overlay (T3b, fix 3). The chip keeps
   * the class color in its outline — so the row still reads as the legend entry
   * for that class — but drops the fill, mirroring "nothing of this color is on
   * the map right now". `data-chip-color` is unchanged: the color the row stands
   * for does not depend on whether it is painted.
   */
  readonly hollow?: boolean;
}) {
  return (
    <Box
      aria-hidden="true"
      data-testid={testId}
      data-chip-color={color}
      data-chip-hollow={hollow ? 'true' : undefined}
      style={{
        display: 'inline-block',
        flex: '0 0 auto',
        width: CLASS_CHIP_SIZE,
        height: CLASS_CHIP_SIZE,
        borderRadius: 3,
        backgroundColor: hollow ? 'transparent' : color,
        border: hollow ? `1px solid ${color}` : '1px solid rgba(0, 0, 0, 0.2)',
      }}
    />
  );
}

/**
 * The "Clase" cell of a ficha table row (T3b, fix 3).
 *
 * Two shapes, one component, so the soils and risk tables can never drift on
 * semantics or on keyboard behaviour:
 *
 *   - no `onToggle` → a plain chip + label, exactly the pre-T3b row. Panels that
 *     do not wire the overlay (and every existing test) keep the static table.
 *   - `onToggle` → the row is a TOGGLE for the painted overlay: `role=button`
 *     with `aria-pressed` reflecting "this class is painted", so a screen reader
 *     announces the state, and Enter/Space activate it (`UnstyledButton` renders
 *     a real `<button>`, which gives both for free).
 *
 * A hidden class is DIMMED rather than removed: the row is still the legend
 * entry for its color and still carries its ha/% figures, which are facts about
 * the analysis and do not change with what is painted.
 */
export function ClassToggleCell({
  color,
  clase,
  hidden = false,
  onToggle,
  chipTestId,
  rowTestId,
  children,
}: {
  readonly color: string;
  readonly clase: string;
  readonly hidden?: boolean;
  readonly onToggle?: (clase: string) => void;
  readonly chipTestId?: string;
  readonly rowTestId?: string;
  /** Label content — plain text, or the soils tooltip trigger. */
  readonly children: ReactNode;
}) {
  const chip = <ClassColorChip color={color} testId={chipTestId} hollow={hidden} />;

  if (!onToggle) {
    return (
      <Group gap={6} wrap="nowrap">
        {chip}
        {children}
      </Group>
    );
  }

  return (
    <UnstyledButton
      onClick={() => onToggle(clase)}
      aria-pressed={!hidden}
      aria-label={`${clase}: ${hidden ? 'mostrar' : 'ocultar'} en el mapa`}
      data-testid={rowTestId}
      data-hidden={hidden ? 'true' : 'false'}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        width: '100%',
        cursor: 'pointer',
        opacity: hidden ? 0.45 : 1,
      }}
    >
      {chip}
      {children}
    </UnstyledButton>
  );
}

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
