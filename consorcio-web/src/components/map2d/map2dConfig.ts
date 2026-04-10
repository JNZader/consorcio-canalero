import type { WATERWAY_DEFS } from '../../hooks/useWaterways';

export const GEE_LAYER_NAMES = ['zona'] as const;

export const SOURCE_IDS = {
  WATERWAYS: 'map2d-waterways',
  SOIL: 'map2d-soil',
  CATASTRO: 'map2d-catastro',
  ROADS: 'map2d-roads',
  BASINS: 'map2d-basins',
  APPROVED_ZONES: 'map2d-approved-zones',
  SUGGESTED_ZONES: 'map2d-suggested-zones',
  ZONA: 'map2d-zona',
  INFRASTRUCTURE: 'map2d-infrastructure',
  PUBLIC_LAYERS_PREFIX: 'map2d-public-',
  IGN: 'map2d-ign-overlay',
  SATELLITE_IMAGE: 'map2d-selected-image',
  COMPARISON_LEFT: 'map2d-comparison-left',
  COMPARISON_RIGHT: 'map2d-comparison-right',
  DEM_RASTER: 'map2d-dem-raster',
  MARTIN_PUNTOS: 'map2d-martin-puntos',
  MARTIN_CANALES: 'map2d-martin-canales',
} as const;

type WaterwayDef = (typeof WATERWAY_DEFS)[number];

const WATERWAY_FILE_SPECS = [
  {
    suffix: 'rio-tercero',
    url: 'pmtiles:///waterways/rio_tercero.pmtiles',
    layer: 'rio_tercero',
    waterwayId: 'rio_tercero',
    fallbackColor: '#1565C0',
  },
  {
    suffix: 'canal-desviador',
    url: 'pmtiles:///waterways/canal_desviador.pmtiles',
    layer: 'canal_desviador',
    waterwayId: 'canal_desviador',
    fallbackColor: '#00897B',
  },
  {
    suffix: 'canal-litin',
    url: 'pmtiles:///waterways/canal_litin_tortugas.pmtiles',
    layer: 'canal_litin_tortugas',
    waterwayId: 'canal_litin_tortugas',
    fallbackColor: '#00ACC1',
  },
  {
    suffix: 'arroyo-algodon',
    url: 'pmtiles:///waterways/arroyo_algodon.pmtiles',
    layer: 'arroyo_algodon',
    waterwayId: 'arroyo_algodon',
    fallbackColor: '#42A5F5',
  },
  {
    suffix: 'arroyo-mojarras',
    url: 'pmtiles:///waterways/arroyo_las_mojarras.pmtiles',
    layer: 'arroyo_las_mojarras',
    waterwayId: 'arroyo_las_mojarras',
    fallbackColor: '#64B5F6',
  },
  {
    suffix: 'canales-existentes',
    url: 'pmtiles:///waterways/canales_existentes.pmtiles',
    layer: 'canales_existentes',
    waterwayId: 'canales_existentes',
    fallbackColor: '#0B3D91',
  },
];

export function buildWaterwayLayerConfigs(waterwayDefs: readonly WaterwayDef[]) {
  return WATERWAY_FILE_SPECS.map((spec) => ({
    id: `${SOURCE_IDS.WATERWAYS}-${spec.suffix}`,
    url: spec.url,
    layer: spec.layer,
    color: waterwayDefs.find((item) => item.id === spec.waterwayId)?.style.color ?? spec.fallbackColor,
  }));
}
