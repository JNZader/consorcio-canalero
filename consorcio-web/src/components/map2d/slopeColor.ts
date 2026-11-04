import type { Feature } from 'geojson';
import type { ProfileSample } from './profileRange';

function mix(from: string, to: string, t: number): string {
  const parse = (hex: string) => [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ];
  const a = parse(from);
  const b = parse(to);
  const channel = (index: number) => Math.round(a[index]! + (b[index]! - a[index]!) * t);
  return `#${[0, 1, 2].map((index) => channel(index).toString(16).padStart(2, '0')).join('')}`;
}

export const SLOPE_COLOR_STOPS = {
  LOW: '#0072b2',
  MEDIUM: '#e69f00',
  HIGH: '#d55e00',
} as const;

export const SLOPE_SEVERITY_LABELS = {
  LOW: 'Baja',
  MEDIUM: 'Media',
  HIGH: 'Alta',
} as const;

export type SlopeSeverityLabel = (typeof SLOPE_SEVERITY_LABELS)[keyof typeof SLOPE_SEVERITY_LABELS];

export interface SlopeScaleThresholds {
  readonly regime: 'canal' | 'transicion' | 'terreno';
  readonly regimeLabel: string;
  readonly lowMax: number;
  readonly mediumMax: number;
  readonly lowLabel: string;
  readonly mediumLabel: string;
  readonly highLabel: string;
}

export const DEFAULT_SLOPE_SCALE: SlopeScaleThresholds = {
  regime: 'terreno',
  regimeLabel: 'General',
  lowMax: 2,
  mediumMax: 5,
  lowLabel: 'Baja (<2%)',
  mediumLabel: 'Media (2–5%)',
  highLabel: 'Alta (≥5%)',
};

export const CANAL_SLOPE_SCALE: SlopeScaleThresholds = {
  regime: 'canal',
  regimeLabel: 'Canal / Llanura',
  lowMax: 0.05,
  mediumMax: 0.2,
  lowLabel: 'Baja (<0,05%)',
  mediumLabel: 'Media (0,05–0,2%)',
  highLabel: 'Alta (≥0,2%)',
};

export const TRANSICION_SLOPE_SCALE: SlopeScaleThresholds = {
  regime: 'transicion',
  regimeLabel: 'Transición',
  lowMax: 0.4,
  mediumMax: 1.0,
  lowLabel: 'Baja (<0,4%)',
  mediumLabel: 'Media (0,4–1%)',
  highLabel: 'Alta (≥1%)',
};

/**
 * Adaptively selects slope thresholds based on the characteristic slope (P90)
 * of the sampled trace. Avoids treating flat canal regions as uniform blue while
 * preserving hydraulic physical meaning.
 */
export function profileSlopeScale(samples: readonly ProfileSample[]): SlopeScaleThresholds {
  if (samples.length < 2) {
    return DEFAULT_SLOPE_SCALE;
  }
  const slopes: number[] = [];
  for (let index = 1; index < samples.length; index += 1) {
    const prev = samples[index - 1];
    const next = samples[index];
    if (!prev || !next || prev.elevation_m == null || next.elevation_m == null) continue;
    const run = next.distance_m - prev.distance_m;
    if (run <= 0) continue;
    slopes.push(Math.abs((next.elevation_m - prev.elevation_m) / run) * 100);
  }
  if (slopes.length === 0) {
    return DEFAULT_SLOPE_SCALE;
  }
  slopes.sort((a, b) => a - b);
  // P90 index avoids single-step DEM quantization artifacts
  const p90Idx = Math.min(slopes.length - 1, Math.floor(slopes.length * 0.9));
  const p90 = slopes[p90Idx] ?? 0;

  if (p90 <= 0.5) {
    return CANAL_SLOPE_SCALE;
  }
  if (p90 <= 2.0) {
    return TRANSICION_SLOPE_SCALE;
  }
  return DEFAULT_SLOPE_SCALE;
}

export function slopeSeverityLabel(
  pct: number,
  scale: SlopeScaleThresholds = DEFAULT_SLOPE_SCALE
): SlopeSeverityLabel {
  const abs = Math.abs(pct);
  if (abs < scale.lowMax) return SLOPE_SEVERITY_LABELS.LOW;
  if (abs < scale.mediumMax) return SLOPE_SEVERITY_LABELS.MEDIUM;
  return SLOPE_SEVERITY_LABELS.HIGH;
}

/** Okabe-Ito colorblind-safe ramp: blue (#0072b2) when flat, amber (#e69f00) at lowMax, vermilion (#d55e00) from mediumMax up. */
export function slopeColor(
  pct: number,
  scale: SlopeScaleThresholds = DEFAULT_SLOPE_SCALE
): string {
  const abs = Math.abs(pct);
  if (abs <= scale.lowMax) {
    const t = scale.lowMax > 0 ? abs / scale.lowMax : 0;
    return mix(SLOPE_COLOR_STOPS.LOW, SLOPE_COLOR_STOPS.MEDIUM, t);
  }
  if (abs >= scale.mediumMax) {
    return SLOPE_COLOR_STOPS.HIGH;
  }
  const span = scale.mediumMax - scale.lowMax;
  const t = span > 0 ? (abs - scale.lowMax) / span : 0;
  return mix(SLOPE_COLOR_STOPS.MEDIUM, SLOPE_COLOR_STOPS.HIGH, t);
}

export interface SlopeSegment {
  readonly points: readonly { distance_m: number; elevation_m: number }[];
  readonly color: string;
}

export function slopeSegments(
  samples: readonly ProfileSample[],
  customScale?: SlopeScaleThresholds
): SlopeSegment[] {
  const scale = customScale ?? profileSlopeScale(samples);
  const segments: SlopeSegment[] = [];
  for (let index = 1; index < samples.length; index += 1) {
    const prev = samples[index - 1];
    const next = samples[index];
    if (!prev || !next || prev.elevation_m == null || next.elevation_m == null) continue;
    const run = next.distance_m - prev.distance_m;
    const slope = run > 0 ? ((next.elevation_m - prev.elevation_m) / run) * 100 : 0;
    segments.push({
      color: slopeColor(slope, scale),
      points: [
        { distance_m: prev.distance_m, elevation_m: prev.elevation_m },
        { distance_m: next.distance_m, elevation_m: next.elevation_m },
      ],
    });
  }
  return segments;
}

export function slopeLineFeatures(
  samples: readonly (ProfileSample & { lon?: number; lat?: number })[],
  customScale?: SlopeScaleThresholds
): Feature[] {
  const scale = customScale ?? profileSlopeScale(samples);
  const features: Feature[] = [];
  for (let index = 1; index < samples.length; index += 1) {
    const prev = samples[index - 1];
    const next = samples[index];
    if (
      !prev ||
      !next ||
      prev.lon == null ||
      prev.lat == null ||
      next.lon == null ||
      next.lat == null ||
      prev.elevation_m == null ||
      next.elevation_m == null
    ) {
      continue;
    }
    const run = next.distance_m - prev.distance_m;
    const slope = run > 0 ? ((next.elevation_m - prev.elevation_m) / run) * 100 : 0;
    features.push({
      type: 'Feature',
      properties: {
        color: slopeColor(slope, scale),
      },
      geometry: {
        type: 'LineString',
        coordinates: [
          [prev.lon, prev.lat],
          [next.lon, next.lat],
        ],
      },
    });
  }
  return features;
}
