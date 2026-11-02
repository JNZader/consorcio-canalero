/**
 * Argentine display strings for the elevation profile.
 * The plot stays free of floating cards; these strings live in the header,
 * the cursor label and the legend beside the chart.
 */

const esFormatter = (digits: number) =>
  new Intl.NumberFormat('es-AR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export function formatEs(value: number, digits: number): string {
  return esFormatter(digits).format(value);
}

export function formatElevationM(value: number): string {
  return `${formatEs(value, 1)} m`;
}

/** Metres under 1 km, kilometres with two decimals from there up. */
export function formatProfileDistance(meters: number): string {
  if (Math.abs(meters) >= 1000) {
    return `${formatEs(meters / 1000, 2)} km`;
  }
  return `${formatEs(Math.round(meters), 0)} m`;
}

/**
 * Axis ticks. Long traces read in kilometres so a 4 km canal is not a row of
 * raw metres. A tick that lands on a whole kilometre drops the decimal.
 */
export function formatAxisDistance(meters: number, spanM: number): string {
  if (spanM >= 1000) {
    const km = meters / 1000;
    const digits = Math.abs(km - Math.round(km)) < 0.05 ? 0 : 1;
    return `${formatEs(km, digits)} km`;
  }
  return formatEs(Math.round(meters), 0);
}

export function usesKilometreAxis(spanM: number): boolean {
  return spanM >= 1000;
}

/** Percent slope. Two decimals under 1 %, one from there up. Unicode minus. */
export function formatSlopePct(value: number): string {
  const digits = Math.abs(value) < 1 ? 2 : 1;
  const body = formatEs(Math.abs(value), digits);
  return value < 0 ? `−${body} %` : `${body} %`;
}

export function formatSignedDeltaM(value: number): string {
  const body = formatEs(Math.abs(value), 1);
  return value < 0 ? `−${body} m` : `+${body} m`;
}

export function formatRelief(ascentM: number, descentM: number): string {
  return `+${formatEs(ascentM, 1)} / −${formatEs(descentM, 1)} m`;
}

/**
 * Y domain that refuses to stretch a couple of metres across the whole plot.
 * A 2 m trace keeps a span of at least 12 m, with a little air around it.
 */
export function elevationAxisDomain(minZ: number, maxZ: number): [number, number] {
  const lo = Math.min(minZ, maxZ);
  const hi = Math.max(minZ, maxZ);
  const relief = hi - lo;
  const span = Math.max(relief, 12);
  const pad = (span - relief) / 2 + Math.max(1, relief * 0.08);
  return [lo - pad, hi + pad];
}

export function profileToCsv(
  rows: readonly { distance_m: number; elevation_m: number | null }[]
): string {
  const lines = ['distancia_m,cota_m'];
  for (const row of rows) {
    const cota = row.elevation_m == null || !Number.isFinite(row.elevation_m) ? '' : String(row.elevation_m);
    lines.push(`${row.distance_m},${cota}`);
  }
  return `${lines.join('\n')}\n`;
}

export function formatCursorReadout(
  distanceM: number,
  elevationM: number | null,
  slopePct: number | null
): string {
  const elevation = elevationM == null ? 'sin dato' : formatElevationM(elevationM);
  const base = `${formatProfileDistance(distanceM)} · ${elevation}`;
  return slopePct == null ? base : `${base} · ${formatSlopePct(slopePct)}`;
}
