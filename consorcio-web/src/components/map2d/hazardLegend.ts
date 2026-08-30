import { LAYER_LEGEND_CONFIG } from '../../config/rasterLegend';
import { HAZARD_RISK_CLASSES, type HazardRiskClass } from '../../hooks/useHazardUrlState';
import type { HazardBasinOption } from './hazardControls.types';

export interface HazardLegendInput {
  readonly active: boolean;
  readonly riskClasses: readonly HazardRiskClass[];
  readonly selectedBasinId: string | null;
  readonly basinOptions: readonly HazardBasinOption[];
}

export interface HazardLegendView {
  readonly visibleClasses: readonly HazardRiskClass[];
  readonly hasHiddenClasses: boolean;
  readonly basinLabel: string | null;
}

const FALLBACK_RISK_CLASS_COLOR = '#888888';

export const HAZARD_BASIN_OUTLINE_COLOR = '#2563eb';

function resolveBasinLabel(
  selectedBasinId: string | null,
  basinOptions: readonly HazardBasinOption[]
): string | null {
  if (!selectedBasinId) return null;
  const match = basinOptions.find((option) => option.id === selectedBasinId);
  return match?.label ?? `Cuenca ${selectedBasinId}`;
}

/** Discrete flood-risk colormap; drainage uses the same four class names. */
export function colorForHazardRiskClass(riskClass: HazardRiskClass): string {
  return (
    LAYER_LEGEND_CONFIG.flood_risk.ranges?.find((range) => range.label === riskClass)?.color ??
    FALLBACK_RISK_CLASS_COLOR
  );
}

export function buildHazardLegendView(input: HazardLegendInput): HazardLegendView | null {
  if (!input.active) return null;

  const visibleClasses = HAZARD_RISK_CLASSES.filter((riskClass) =>
    input.riskClasses.includes(riskClass)
  );

  return {
    visibleClasses,
    hasHiddenClasses: visibleClasses.length < HAZARD_RISK_CLASSES.length,
    basinLabel: resolveBasinLabel(input.selectedBasinId, input.basinOptions),
  };
}
