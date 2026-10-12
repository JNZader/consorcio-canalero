/** Shared `/mapa` query: hazard keys plus camera/permalink/report pin. */

const HAZARD_KEYS = new Set(['hazard', 'basin', 'riskClasses', 'precipMonth']);

function keepScalar(value: unknown): string | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value === 'string' && value.trim() !== '') return value.trim();
  return undefined;
}

export function parseMapaRouteSearch(search: Record<string, unknown>): Record<string, unknown> {
  const riskClasses = Array.isArray(search.riskClasses)
    ? search.riskClasses.flatMap((value) => (typeof value === 'string' ? value.split(',') : []))
    : typeof search.riskClasses === 'string'
      ? search.riskClasses.split(',')
      : [];

  const lat = keepScalar(search.lat);
  const lng = keepScalar(search.lng);
  const zoom = keepScalar(search.zoom);
  const preset = keepScalar(search.preset);
  const layers = keepScalar(search.l);
  const rasterTipo = keepScalar(search.r);

  return {
    ...(search.hazard === '1' || search.hazard === true ? { hazard: '1' } : {}),
    ...(typeof search.basin === 'string' && search.basin.trim() ? { basin: search.basin.trim() } : {}),
    ...(riskClasses.length > 0 ? { riskClasses } : {}),
    ...(typeof search.precipMonth === 'string' ? { precipMonth: search.precipMonth } : {}),
    ...(lat ? { lat } : {}),
    ...(lng ? { lng } : {}),
    ...(zoom ? { zoom } : {}),
    ...(preset ? { preset } : {}),
    ...(layers ? { l: layers } : {}),
    ...(rasterTipo ? { r: rasterTipo } : {}),
    ...(search.report === '1' || search.report === true ? { report: '1' } : {}),
  };
}

export function mergeHazardCanonical(
  current: Record<string, unknown>,
  hazardCanonical: Record<string, string>
): Record<string, unknown> {
  const kept: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(current)) {
    if (HAZARD_KEYS.has(key) || value === undefined) continue;
    kept[key] = value;
  }
  return { ...kept, ...hazardCanonical };
}
