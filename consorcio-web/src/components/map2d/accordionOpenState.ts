export const LAYER_ACCORDION_ALL = [
  'base',
  'hidrografia',
  'canales',
  'territorio',
  'pilar_verde',
  'analisis',
  'raster',
  'ajustes',
] as const;

export type LayerAccordionSection = (typeof LAYER_ACCORDION_ALL)[number];

export function idleAccordionValue(activeFamilies: readonly string[], rasterOpen: boolean): string[] {
  const next = [...activeFamilies];
  if (rasterOpen && !next.includes('raster')) next.push('raster');
  return next;
}

export function displayedAccordionValue(
  isSearching: boolean,
  stored: readonly string[] | null,
  idle: readonly string[],
  available: readonly string[] = LAYER_ACCORDION_ALL,
): string[] {
  if (isSearching) return available.length > 0 ? [...available] : [...LAYER_ACCORDION_ALL];
  return stored && stored.length > 0 ? [...stored] : [...idle];
}

export function rememberAccordionChange(
  isSearching: boolean,
  next: string[],
  previous: string[] | null,
): string[] | null {
  if (isSearching) return previous;
  return next;
}
