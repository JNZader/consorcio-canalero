/**
 * Thematic map presets (UX PDF R1).
 *
 * Each preset turns ON a small set of catalog vector ids. `applyPreset` in
 * the layer store turns the rest of the catalog OFF and leaves per-canal
 * `canal_*` keys alone (masters still gate them).
 */

export const MAP_PRESET_IDS = [
  'agua',
  'canales',
  'caminos',
  'pilar-verde',
  'catastro',
] as const;

export type MapPresetId = (typeof MAP_PRESET_IDS)[number];

export interface MapPreset {
  id: MapPresetId;
  label: string;
  description: string;
  /** Catalog ids to turn on. Missing catalog ids are turned off. */
  visibleOn: readonly string[];
}

const WATERWAY_IDS = [
  'waterways',
  'waterways_rio_tercero',
  'waterways_canal_desviador',
  'waterways_canal_litin_tortugas',
  'waterways_arroyo_algodon',
  'waterways_arroyo_las_mojarras',
] as const;

export const MAP_PRESETS: readonly MapPreset[] = [
  {
    id: 'agua',
    label: 'Agua',
    description: 'Dónde se acumula el agua',
    visibleOn: [...WATERWAY_IDS, 'approved_zones', 'basins', 'canales_relevados'],
  },
  {
    id: 'canales',
    label: 'Canales',
    description: 'Red de canales y conflictos',
    visibleOn: ['canales_relevados', 'canales_propuestos', 'basins', 'puntos_conflicto'],
  },
  {
    id: 'caminos',
    label: 'Caminos',
    description: 'Red vial y cruces',
    visibleOn: ['roads', 'road_flow', 'sentido_camino', 'red_vial_oficial', 'caminos_huecos'],
  },
  {
    id: 'pilar-verde',
    label: 'Pilar Verde',
    description: 'BPA y agroforestal',
    visibleOn: [
      'pilar_verde_bpa_historico',
      'pilar_verde_agro_aceptada',
      'pilar_verde_agro_presentada',
      'pilar_verde_agro_zonas',
      'pilar_verde_porcentaje_forestacion',
    ],
  },
  {
    id: 'catastro',
    label: 'Catastro',
    description: 'Parcela y suelos — clic abre ficha',
    visibleOn: ['catastro', 'soil'],
  },
];

export function getMapPreset(id: MapPresetId): MapPreset {
  const preset = MAP_PRESETS.find((item) => item.id === id);
  if (!preset) {
    throw new Error(`Unknown map preset: ${id}`);
  }
  return preset;
}
