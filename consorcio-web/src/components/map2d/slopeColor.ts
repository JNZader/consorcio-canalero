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

export function slopeSeverityLabel(pct: number): SlopeSeverityLabel {
  const abs = Math.abs(pct);
  if (abs < 2) return SLOPE_SEVERITY_LABELS.LOW;
  if (abs < 5) return SLOPE_SEVERITY_LABELS.MEDIUM;
  return SLOPE_SEVERITY_LABELS.HIGH;
}

/** Okabe-Ito colorblind-safe ramp: blue (#0072b2) when flat, amber (#e69f00) around 2 %, vermilion (#d55e00) from 5 % up. Sign does not matter. */
export function slopeColor(pct: number): string {
  const t = Math.min(1, Math.abs(pct) / 5);
  if (t < 0.4) return mix(SLOPE_COLOR_STOPS.LOW, SLOPE_COLOR_STOPS.MEDIUM, t / 0.4);
  return mix(SLOPE_COLOR_STOPS.MEDIUM, SLOPE_COLOR_STOPS.HIGH, (t - 0.4) / 0.6);
}

export interface SlopeSegment {
  readonly points: readonly { distance_m: number; elevation_m: number }[];
  readonly color: string;
}

export function slopeSegments(samples: readonly ProfileSample[]): SlopeSegment[] {
  const segments: SlopeSegment[] = [];
  for (let index = 1; index < samples.length; index += 1) {
    const prev = samples[index - 1];
    const next = samples[index];
    if (!prev || !next || prev.elevation_m == null || next.elevation_m == null) continue;
    const run = next.distance_m - prev.distance_m;
    const slope = run > 0 ? ((next.elevation_m - prev.elevation_m) / run) * 100 : 0;
    segments.push({
      color: slopeColor(slope),
      points: [
        { distance_m: prev.distance_m, elevation_m: prev.elevation_m },
        { distance_m: next.distance_m, elevation_m: next.elevation_m },
      ],
    });
  }
  return segments;
}

export function slopeLineFeatures(
  samples: readonly (ProfileSample & { lon?: number; lat?: number })[]
): Feature[] {
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
    features.push({
      type: 'Feature',
      properties: {
        color: slopeColor(
          next.distance_m > prev.distance_m
            ? ((next.elevation_m - prev.elevation_m) / (next.distance_m - prev.distance_m)) * 100
            : 0
        ),
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
