import type { FeatureCollection } from 'geojson';
import { getSoilColor } from '../../hooks/useSoilMap';
import { WATERWAY_DEFS } from '../../hooks/useWaterways';

function pushApprovedZoneLegendItems(
  items: Array<{ color: string; label: string; type: string }>,
  approvedZones: FeatureCollection
) {
  for (const feature of approvedZones.features) {
    items.push({
      color: (feature.properties?.__color as string | undefined) || '#1971c2',
      label: String(feature.properties?.nombre || 'Cuenca'),
      type: 'fill',
    });
  }
}

function pushSoilLegendItems(
  items: Array<{ color: string; label: string; type: string }>,
  soilMap: FeatureCollection
) {
  const capOrder = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII'];
  const presentCaps = new Set<string>();
  for (const feature of soilMap.features) {
    const cap = (feature.properties as { cap?: string | null } | null)?.cap;
    if (!cap) continue;
    const normalized = cap.trim().toUpperCase();
    const match = normalized.match(/^(VIII|VII|VI|IV|III|II|I)/);
    if (match) presentCaps.add(match[1]);
  }
  for (const cap of capOrder) {
    if (presentCaps.has(cap)) {
      items.push({
        color: getSoilColor(cap),
        label: `Clase ${cap}`,
        type: 'fill',
      });
    }
  }
}

function pushWaterwayLegendItems(items: Array<{ color: string; label: string; type: string }>) {
  const waterwayEntries = WATERWAY_DEFS.map((waterway) => ({
    color: waterway.style.color,
    label: waterway.nombre,
  }));
  for (const entry of waterwayEntries) {
    items.push({ ...entry, type: 'line' });
  }
}

export function buildActiveLegendItems(params: {
  zonaCollection: FeatureCollection | null;
  vectorVisibility: Record<string, boolean>;
  hasApprovedZones: boolean;
  approvedZones: FeatureCollection | null | undefined;
  basins: FeatureCollection | null | undefined;
  soilMap: FeatureCollection | null | undefined;
}) {
  const { zonaCollection, vectorVisibility, hasApprovedZones, approvedZones, basins, soilMap } =
    params;

  const items: Array<{ color: string; label: string; type: string }> = [];

  if (zonaCollection && zonaCollection.features.length > 0) {
    items.push({ color: '#FF0000', label: 'Zona Consorcio', type: 'border' });
  }

  if (vectorVisibility.approved_zones && hasApprovedZones && approvedZones) {
    pushApprovedZoneLegendItems(items, approvedZones);
  }

  if (vectorVisibility.basins && basins && basins.features.length > 0) {
    items.push({
      color: '#00897B',
      label: 'Subcuencas operativas',
      type: 'border',
    });
  }

  if (vectorVisibility.soil && soilMap && soilMap.features.length > 0) {
    pushSoilLegendItems(items, soilMap);
  }

  if (vectorVisibility.waterways) {
    pushWaterwayLegendItems(items);
  }

  return items;
}

/**
 * Layer families for the 2D control panel accordion (change
 * `rediseno-ux-mapa`, Phase 2). Every entry returned by
 * `buildVectorLayerItems` carries a `category` so `LayerControlsPanel` can
 * group checkboxes by family. `BASE` is reserved for the structural controls
 * (capa base / IGN / DEM) that live in the panel — not in this array.
 */
export const LAYER_CATEGORY = {
  BASE: 'base',
  HIDROGRAFIA: 'hidrografia',
  TERRITORIO: 'territorio',
  PRECIPITATION: 'precipitation',
  PILAR_VERDE: 'pilar_verde',
  CANALES: 'canales',
  ANALISIS: 'analisis',
} as const;

export type LayerCategory = (typeof LAYER_CATEGORY)[keyof typeof LAYER_CATEGORY];

export function buildVectorLayerItems(params: {
  basins: FeatureCollection | null | undefined;
  approvedZonesCollection: FeatureCollection | null | undefined;
  roadsCollection: FeatureCollection | null | undefined;
  intersectionsLength: number;
  /**
   * Whether the Pilar Verde static data has loaded (at least one slot non-null).
   * Callers can simply pass `!!pilarVerde?.aggregates` or similar — the flag
   * decides whether the 5 Pilar Verde toggles render in the layer control.
   * Defaults to `false` for backwards compatibility (no behavior change for
   * existing callers that haven't wired Pilar Verde yet).
   */
  showPilarVerde?: boolean;
  /**
   * Whether the Pilar Azul (Canales) static data has loaded (at least
   * `index.json` non-null). When true, the 2 master toggles render in the
   * layer control. Per-canal sub-toggles are rendered by Phase 4.
   */
  showPilarAzul?: boolean;
  /**
   * Whether the Pilar Azul (Escuelas rurales) static data has loaded
   * (collection non-null). When true, the single "Escuelas rurales" master
   * toggle renders in the layer control. There are NO per-school sub-toggles
   * — one master covers all 7 features (design §7). Defaults to `false` for
   * backwards compatibility (callers who haven't wired `useEscuelas` yet
   * see no behavior change).
   */
  showEscuelas?: boolean;
}) {
  const {
    basins,
    approvedZonesCollection,
    roadsCollection,
    intersectionsLength,
    showPilarVerde = false,
    showPilarAzul = false,
    showEscuelas = false,
  } = params;

  return [
    {
      id: 'basins',
      label: 'Subcuencas',
      category: LAYER_CATEGORY.HIDROGRAFIA,
      // Subcuencas públicas a pedido del consorcio (2026-07-30): el endpoint
      // backend (`/geo/basins`) siempre fue público, solo faltaba mostrarlas.
      show: !!basins && basins.features.length > 0,
    },
    {
      id: 'approved_zones',
      label: 'Cuencas',
      category: LAYER_CATEGORY.HIDROGRAFIA,
      show: !!approvedZonesCollection,
    },
    {
      id: 'waterways',
      label: 'Hidrografía',
      category: LAYER_CATEGORY.HIDROGRAFIA,
      show: true,
    },
    {
      id: 'roads',
      // Label normalised with the 3D viewer (PRIORITY_3D_VECTOR_LAYERS).
      label: 'Red Vial',
      category: LAYER_CATEGORY.TERRITORIO,
      show: !!roadsCollection && roadsCollection.features.length > 0,
    },
    // Labels match the 3D toggles panel so the user sees the same wording
    // across views (terrainLayerConfig.ts:35-42).
    {
      id: 'soil',
      label: 'Suelos IDECOR 1:50.000',
      category: LAYER_CATEGORY.TERRITORIO,
      show: true,
    },
    {
      id: 'catastro',
      label: 'Catastro rural IDECOR',
      category: LAYER_CATEGORY.TERRITORIO,
      show: true,
    },
    {
      id: 'puntos_conflicto',
      label: 'Puntos conflicto',
      category: LAYER_CATEGORY.ANALISIS,
      show: intersectionsLength > 0,
    },
    // ── Pilar Verde (Phase 2/7) — Spanish (Rioplatense) labels per spec ──
    {
      id: 'pilar_verde_bpa_historico',
      label: 'BPA histórico (por años)',
      category: LAYER_CATEGORY.PILAR_VERDE,
      show: showPilarVerde,
    },
    {
      id: 'pilar_verde_agro_aceptada',
      label: 'Agroforestal: Cumplen',
      category: LAYER_CATEGORY.PILAR_VERDE,
      show: showPilarVerde,
    },
    {
      id: 'pilar_verde_agro_presentada',
      label: 'Agroforestal: Presentaron',
      category: LAYER_CATEGORY.PILAR_VERDE,
      show: showPilarVerde,
    },
    {
      id: 'pilar_verde_agro_zonas',
      label: 'Zonas Agroforestales',
      category: LAYER_CATEGORY.PILAR_VERDE,
      show: showPilarVerde,
    },
    {
      id: 'pilar_verde_porcentaje_forestacion',
      label: '% Forestación obligatoria',
      category: LAYER_CATEGORY.PILAR_VERDE,
      show: showPilarVerde,
    },
    // ── Pilar Azul (Canales) — master toggles per spec ──
    // Per-canal sub-toggles + the "Etapas propuestas" filter subsection are
    // rendered by Phase 4's `LayerControlsPanel` Canales section.
    {
      id: 'canales_relevados',
      label: 'Canales relevados',
      category: LAYER_CATEGORY.CANALES,
      show: showPilarAzul,
    },
    {
      id: 'canales_propuestos',
      label: 'Canales propuestos',
      category: LAYER_CATEGORY.CANALES,
      show: showPilarAzul,
    },
    // ── Pilar Azul (Escuelas rurales) — single master toggle (design §7) ──
    {
      id: 'escuelas',
      label: 'Escuelas rurales',
      category: LAYER_CATEGORY.TERRITORIO,
      show: showEscuelas,
    },
  ]
    .filter(({ show }) => show)
    .map(({ id, label, category }) => ({ id, label, category }));
}

export function buildDemLayerOptions(
  demLayers: Array<{
    id: string;
    tipo: string;
    nombre: string;
    label?: string;
  }>,
  geoLayerLabels: Record<string, string>
) {
  return demLayers
    .filter((layer) => layer.tipo !== 'precip_normal')
    .map((layer) => ({
      value: layer.id,
      // `layer.label` ya trae el sufijo de variante ("(natural)", "(escenario)")
      // que puso enrichLayer. Armar la etiqueta desde el tipo mostraba las tres
      // variantes IGUAL —tres "Acumulacion de Flujo" indistinguibles—, porque el
      // tipo es el mismo para las tres; lo unico que las separa es el nombre/label.
      label: layer.label ?? geoLayerLabels[layer.tipo] ?? layer.nombre,
    }));
}

/**
 * Per-family ACTIVE-layer counts — the SINGLE derivation behind EVERY
 * active-layer number in the app: the 2D family badges (`LayerControlsPanel`),
 * the 2D workspace "N capas activas" badge (`MapaMapLibre`) and, since the T3c
 * final round (R2-002), the 3D workspace badge (`TerrainViewer3DChrome`, which
 * feeds it `buildTerrain3DLayerItems`). The 3D viewer used to compute its badge
 * as `Object.values(vectorLayerVisibility).filter(Boolean).length`, i.e. the
 * exact raw-key formula this function exists to replace.
 *
 * Why it exists: the workspace badge used to be
 * `Object.values(vectorVisibility).filter(Boolean).length`, which counts the
 * per-canal and per-waterway sub-keys the panel never shows as rows — it
 * reported "68 activas" over a map with ~6 visible layers, contradicting the
 * per-family badges right next to it. Counting from the SAME inputs the panel
 * renders makes the two numbers agree by construction.
 *
 * Counting rules (identical to the panel's own badges):
 *   - BASE     → the structural overlays (IGN, DEM), not `layerItems`.
 *   - CANALES  → visible canal CHILDREN, not the master flags (a master can
 *                stay `true` after its last child is toggled off). `canalChildIds`
 *                must ALREADY be gated by each side's master — `collectCanalChildIds`
 *                does it (B2-2.6); children of a master that is off are not drawn,
 *                so counting them made the badge claim 60 over a map drawing 41.
 *   - others   → visible `layerItems` of that family.
 */
export function buildFamilyActiveCounts(params: {
  layerItems: ReadonlyArray<{ id: string; category: LayerCategory }>;
  vectorVisibility: Record<string, boolean>;
  canalChildIds?: readonly string[];
  showIGNOverlay?: boolean;
  showDemOverlay?: boolean;
  showPrecipitation?: boolean;
}): Record<LayerCategory, number> {
  const {
    layerItems,
    vectorVisibility,
    canalChildIds = [],
    showIGNOverlay = false,
    showDemOverlay = false,
    showPrecipitation = false,
  } = params;

  const counts: Record<LayerCategory, number> = {
    [LAYER_CATEGORY.BASE]: (showIGNOverlay ? 1 : 0) + (showDemOverlay ? 1 : 0),
    [LAYER_CATEGORY.HIDROGRAFIA]: 0,
    [LAYER_CATEGORY.TERRITORIO]: 0,
    [LAYER_CATEGORY.PRECIPITATION]: showPrecipitation ? 1 : 0,
    [LAYER_CATEGORY.PILAR_VERDE]: 0,
    [LAYER_CATEGORY.CANALES]: canalChildIds.reduce(
      (count, id) => (vectorVisibility[id] ? count + 1 : count),
      0
    ),
    [LAYER_CATEGORY.ANALISIS]: 0,
  };

  for (const item of layerItems) {
    // The CANALES family is counted from its children above; `layerItems`
    // only carries the two master toggles, which would double-count.
    if (item.category === LAYER_CATEGORY.CANALES) continue;
    if (vectorVisibility[item.id]) counts[item.category] += 1;
  }

  return counts;
}

/** Total of `buildFamilyActiveCounts` — what the workspace badge shows. */
export function sumFamilyActiveCounts(counts: Record<LayerCategory, number>): number {
  return Object.values(counts).reduce((total, count) => total + count, 0);
}

/**
 * Accent- and case-insensitive normalization for the layer search box (R3-003).
 *
 * The panel labels are Spanish and carry diacritics ("% Forestación
 * obligatoria", "Hidrografía"), while the data-driven ones do not ("Riesgo de
 * Inundacion"). A plain `toLowerCase().includes()` therefore failed BOTH ways:
 * typing "forestacion" missed the accented label and typing "inundación"
 * missed the unaccented one. NFD + stripping the combining-marks block folds
 * both sides onto the same key.
 */
export function normalizeSearchText(text: string): string {
  // `\p{Diacritic}` (needs the `u` flag) is what NFD splits the accents into.
  // A raw U+0300..U+036F character CLASS trips biome's
  // `noMisleadingCharacterClass` — combining marks are not standalone chars.
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

/**
 * Should the ~512 KB BPA-join payload be fetched for this ficha request?
 *
 * Extracted from `MapaMapLibre`'s latch effect (R3-001) so the gating rule is
 * testable: `PilarVerdeBadges` renders NOTHING for any tipo other than the
 * exact string `'parcela'`, so no other tipo may open the gate. `'parcelas'`,
 * `'poligono'` and `canal_*` must all stay false.
 */
export function shouldLatchBpaJoin(request: unknown, tipo: string | null | undefined): boolean {
  return request !== null && request !== undefined && tipo === 'parcela';
}
