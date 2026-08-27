export interface PrecipitationRange {
  readonly colorStops: readonly string[];
  readonly label: string;
  readonly max: number;
  readonly min: number;
  readonly unit: string;
}

const PRECIPITATION_COLOR_STOPS = [
  '#ffffcc',
  '#c7e9b4',
  '#7fcdbb',
  '#41b6c4',
  '#1d91c0',
  '#0c2c84',
] as const;

const ANNUAL_PRECIPITATION_RANGE: PrecipitationRange = {
  colorStops: PRECIPITATION_COLOR_STOPS,
  label: 'CHIRPS 1991-2020 normal anual',
  max: 1800,
  min: 0,
  unit: 'mm',
};

const MONTHLY_PRECIPITATION_RANGE: PrecipitationRange = {
  colorStops: PRECIPITATION_COLOR_STOPS,
  label: 'CHIRPS 1991-2020 normal mensual',
  max: 200,
  min: 0,
  unit: 'mm',
};

/** The tile rescale and legend must always use the same precipitation range. */
export function getPrecipitationRange(period: string): PrecipitationRange {
  return period === 'anual' ? ANNUAL_PRECIPITATION_RANGE : MONTHLY_PRECIPITATION_RANGE;
}
