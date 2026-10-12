import { GEO_LAYER_LABELS } from '../../hooks/useGeoLayers';

/** Raster types the map can paint even when the DEM catalog request failed (UX-12). */
export const KNOWN_RASTER_TIPOS = [
  'dem_raw',
  'slope',
  'hand',
  'twi',
  'flood_risk',
  'drainage_need',
  'terrain_class',
  'flow_acc',
  'aspect',
] as const;

export type KnownRasterTipo = (typeof KNOWN_RASTER_TIPOS)[number];

export function knownRasterCatalog(): Array<{ value: string; label: string; available: boolean }> {
  return KNOWN_RASTER_TIPOS.map((tipo) => ({
    value: `catalog:${tipo}`,
    label: GEO_LAYER_LABELS[tipo] ?? tipo,
    available: false,
  }));
}

export function mergeRasterSearchOptions(
  demOptions: readonly { value: string; label: string }[],
  query: string,
): Array<{ value: string; label: string; available: boolean }> {
  const live = demOptions.map((option) => ({ ...option, available: true }));
  if (live.length > 0) return [...live];
  const catalog = knownRasterCatalog();
  if (!query) return catalog;
  const needle = query.trim().toLowerCase();
  return catalog.filter((option) => option.label.toLowerCase().includes(needle) || option.value.includes(needle));
}
