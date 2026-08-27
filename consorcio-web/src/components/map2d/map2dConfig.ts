import type { WATERWAY_DEFS } from '../../hooks/useWaterways';

export const GEE_LAYER_NAMES = ['zona'] as const;

/**
 * Startup default for the 2D map base layer. On first load we show the
 * satellite imagery so the 4 canonical layers — Satélite, Imagen (when an
 * image is selected), Hidrografía, Red Vial — are active out of the box.
 *
 * This is component-local state (see `MapaMapLibre.tsx`), not persisted —
 * users can switch to OSM from the layer-controls panel and the choice is
 * forgotten on reload.
 */
export const DEFAULT_BASE_LAYER: 'osm' | 'satellite' = 'satellite';

/**
 * Fill opacity of the clickable catastro parcels — SINGLE SOURCE OF TRUTH.
 *
 * This fill is the ONLY visual affordance telling a citizen the parcels are
 * clickable (they open the ficha territorial), so it must not silently drift
 * back towards invisible.
 *
 * It lives in this leaf module (no runtime imports) because BOTH the paint
 * (`mapLayerEffectHelpers.ts::syncCatastroLayers`) and the opacity-multiplier
 * registry (`layerRenderRegistry.ts`) must read the exact same number: the
 * registry's `defaultOpacity` is multiplied by the persisted per-layer
 * multiplier, so a stale mirror there stomps the paint back down.
 * `tests/unit/layerRenderRegistry.test.ts` pins the two together.
 */
export const CATASTRO_FILL_OPACITY = 0.12;

/**
 * Glyph edge, in px, of EVERY icon in the floating map-control column —
 * SINGLE SOURCE OF TRUTH for the custom (Tabler) half of it.
 *
 * The column mixes controls we render (`MapActionsPanel`, `MeasurementToolbar`)
 * with the ones MapLibre renders itself (zoom, compass, fullscreen). MapLibre's
 * are sprites on a `<span>`, so they cannot take a React prop: their size comes
 * from `--map-ctrl-glyph-size` in `map.module.css`, and this constant is the
 * mirror image of that variable for the icons that DO take a prop.
 *
 * NOT for `CanalBufferControl`: its `IconRoute` is a heading icon inside the
 * ficha PANEL, not a button in the floating column, so it correctly stays at the
 * panel's own 16px. Do not "fix" it to match this constant.
 *
 * The two used to disagree by accident (custom glyphs at 16px next to the
 * library's chunkier ~14–20px filled sprites), which is the ragged column the
 * owner reported. `tests/unit/MapCtrlTouchTargets.test.tsx` asserts the mirror.
 */
export const MAP_CTRL_GLYPH_SIZE = 18;

export const SOURCE_IDS = {
  WATERWAYS: 'map2d-waterways',
  SOIL: 'map2d-soil',
  CATASTRO: 'map2d-catastro',
  ROADS: 'map2d-roads',
  BASINS: 'map2d-basins',
  APPROVED_ZONES: 'map2d-approved-zones',
  ZONA: 'map2d-zona',
  IGN: 'map2d-ign-overlay',
  SATELLITE_IMAGE: 'map2d-selected-image',
  COMPARISON_LEFT: 'map2d-comparison-left',
  COMPARISON_RIGHT: 'map2d-comparison-right',
  DEM_RASTER: 'map2d-dem-raster',
  PRECIP_NORMAL: 'map2d-precip-normal',
  FLOOD_RISK: 'map2d-flood-risk',
  DRAINAGE_NEED: 'map2d-drainage-need',
  MARTIN_PUNTOS: 'map2d-martin-puntos',
  // ── flujo-caminos (design D6) — ranked road crossings ──
  // ONE geojson source feeding BOTH `road_flow-flujo` and `road_flow-canal`,
  // populated from the SAME response object the ranked list renders, so the two
  // surfaces cannot disagree about a direction, an area, a rank or a segment
  // (RFA-R2). It is NOT a Martin source: the payload is authenticated and
  // operator-only, and this capability publishes nothing.
  ROAD_FLOW: 'road_flow',
  // ── Pilar Verde (Phase 2/7) ──
  // Values match the `PilarVerdeLayerId` tuple in `stores/mapLayerSyncStore.ts`
  // so the source id == the visibility-toggle id (no translation table).
  // Phase 7 replaced single-year `pilar_verde_bpa` with the gradient-based
  // `pilar_verde_bpa_historico` — same slot on the map, broader coverage.
  PILAR_VERDE_BPA_HISTORICO: 'pilar_verde_bpa_historico',
  PILAR_VERDE_AGRO_ACEPTADA: 'pilar_verde_agro_aceptada',
  PILAR_VERDE_AGRO_PRESENTADA: 'pilar_verde_agro_presentada',
  PILAR_VERDE_AGRO_ZONAS: 'pilar_verde_agro_zonas',
  PILAR_VERDE_PORCENTAJE_FORESTACION: 'pilar_verde_porcentaje_forestacion',
  // ── Pilar Azul (Canales) ──
  // Values match the `PILAR_AZUL_LAYER_IDS` tuple in `stores/mapLayerSyncStore.ts`
  // so the source id == the master-toggle id (no translation table).
  CANALES_RELEVADOS: 'canales_relevados',
  CANALES_PROPUESTOS: 'canales_propuestos',
  // ── Ficha territorial (A6) — the id-bearing canal network (Martin MVT) ──
  // Distinct from the static CANALES_* layers above: those come from geojson
  // and carry NO `canal_network.id`, so a `tipo=canal_buffer` request cannot be
  // built from them (design §6.3, JDB-013). `vt_canal_network` is Martin's view
  // over `canal_network` (SERIAL id) and is the ONLY canal layer clickable in
  // `'ficha-canal'` mode. Mounted/hidden on demand, never in the idle whitelist.
  CANAL_NETWORK: 'map2d-canal-network',
  // ── Pilar Azul (Escuelas rurales) ──
  // String value `'escuelas'` matches the master-toggle key in
  // `defaultVisibleVectors` AND `ESCUELAS_SOURCE_ID` in `escuelasLayers.ts`
  // (Batch C locked the identical-string contract — see apply-progress #2061).
  ESCUELAS: 'escuelas',
} as const;

/**
 * Default `area_id` the ranked crossings are read for while the DEM catalogue
 * has not answered yet (flujo-caminos).
 *
 * `zona_principal` is a ROLLOUT FACT — the single processing area of this
 * deployment, recorded in the change's task 2.2 — never a rule. The read
 * endpoint takes `area_id` as a query parameter precisely so a second area
 * costs a dispatch and not an edit, and the container prefers whatever area the
 * catalogue actually reports over this fallback.
 */
export const DEFAULT_ROAD_FLOW_AREA_ID = 'zona_principal';

type WaterwayDef = (typeof WATERWAY_DEFS)[number];

const WATERWAY_FILE_SPECS = [
  {
    suffix: 'rio-tercero',
    url: '/waterways/rio_tercero.geojson',
    layer: 'rio_tercero',
    waterwayId: 'rio_tercero',
    fallbackColor: '#1565C0',
  },
  {
    suffix: 'canal-desviador',
    url: '/waterways/canal_desviador.geojson',
    layer: 'canal_desviador',
    waterwayId: 'canal_desviador',
    fallbackColor: '#00897B',
  },
  {
    suffix: 'canal-litin',
    url: '/waterways/canal_litin_tortugas.geojson',
    layer: 'canal_litin_tortugas',
    waterwayId: 'canal_litin_tortugas',
    fallbackColor: '#00ACC1',
  },
  {
    suffix: 'arroyo-algodon',
    url: '/waterways/arroyo_algodon.geojson',
    layer: 'arroyo_algodon',
    waterwayId: 'arroyo_algodon',
    fallbackColor: '#42A5F5',
  },
  {
    suffix: 'arroyo-mojarras',
    url: '/waterways/arroyo_las_mojarras.geojson',
    layer: 'arroyo_las_mojarras',
    waterwayId: 'arroyo_las_mojarras',
    fallbackColor: '#64B5F6',
  },
];

export function buildWaterwayLayerConfigs(waterwayDefs: readonly WaterwayDef[]) {
  return WATERWAY_FILE_SPECS.map((spec) => ({
    id: `${SOURCE_IDS.WATERWAYS}-${spec.suffix}`,
    url: spec.url,
    layer: spec.layer,
    color:
      waterwayDefs.find((item) => item.id === spec.waterwayId)?.style.color ?? spec.fallbackColor,
  }));
}
