import type { Geometry } from 'geojson';

export const HAZARD_RISK_CLASS = {
  LOW: 'Bajo',
  MEDIUM: 'Medio',
  HIGH: 'Alto',
  CRITICAL: 'Crítico',
} as const;

export type HazardRiskClass = (typeof HAZARD_RISK_CLASS)[keyof typeof HAZARD_RISK_CLASS];

export const HAZARD_RISK_CLASSES = Object.values(HAZARD_RISK_CLASS);

export const PRECIPITATION_PERIOD = {
  ANNUAL: 'anual',
  JANUARY: '01',
  FEBRUARY: '02',
  MARCH: '03',
  APRIL: '04',
  MAY: '05',
  JUNE: '06',
  JULY: '07',
  AUGUST: '08',
  SEPTEMBER: '09',
  OCTOBER: '10',
  NOVEMBER: '11',
  DECEMBER: '12',
} as const;

export type PrecipitationPeriod =
  (typeof PRECIPITATION_PERIOD)[keyof typeof PRECIPITATION_PERIOD];

export interface HazardBasinOption {
  readonly id: string;
  readonly label: string;
  readonly geometry?: Geometry | null;
}

export interface HazardControlsProps {
  readonly basins: readonly HazardBasinOption[];
  readonly selectedBasinId: string | null;
  readonly onBasinChange: (basinId: string | null) => void;
  readonly visibleRiskClasses: readonly HazardRiskClass[];
  readonly onRiskClassChange: (riskClass: HazardRiskClass, visible: boolean) => void;
  readonly precipitationPeriod: PrecipitationPeriod;
  readonly onPrecipitationPeriodChange: (period: PrecipitationPeriod) => void;
  readonly onReset: () => void;
  readonly collapsed: boolean;
  readonly onCollapsedChange: (collapsed: boolean) => void;
  /** The surrounding map owns ficha state; controls only reflect and signal its precedence. */
  readonly fichaOpen?: boolean;
  readonly onFichaMinimize?: () => void;
}
