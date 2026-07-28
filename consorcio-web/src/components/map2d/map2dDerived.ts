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
      items.push({ color: getSoilColor(cap), label: `Clase ${cap}`, type: 'fill' });
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
    items.push({ color: '#00897B', label: 'Subcuencas operativas', type: 'border' });
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
  isAdmin: boolean;
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
    isAdmin,
    showPilarVerde = false,
    showPilarAzul = false,
    showEscuelas = false,
  } = params;

  return [
    {
      id: 'basins',
      label: 'Subcuencas',
      category: LAYER_CATEGORY.HIDROGRAFIA,
      show: isAdmin && !!basins && basins.features.length > 0,
    },
    {
      id: 'approved_zones',
      label: 'Cuencas',
      category: LAYER_CATEGORY.HIDROGRAFIA,
      show: !!approvedZonesCollection,
    },
    { id: 'waterways', label: 'Hidrografía', category: LAYER_CATEGORY.HIDROGRAFIA, show: true },
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
  demLayers: Array<{ id: string; tipo: string; nombre: string; label?: string }>,
  geoLayerLabels: Record<string, string>
) {
  return demLayers.map((layer) => ({
    value: layer.id,
    // `layer.label` ya trae el sufijo de variante ("(natural)", "(escenario)")
    // que puso enrichLayer. Armar la etiqueta desde el tipo mostraba las tres
    // variantes IGUAL —tres "Acumulacion de Flujo" indistinguibles—, porque el
    // tipo es el mismo para las tres; lo unico que las separa es el nombre/label.
    label: layer.label ?? geoLayerLabels[layer.tipo] ?? layer.nombre,
  }));
}
