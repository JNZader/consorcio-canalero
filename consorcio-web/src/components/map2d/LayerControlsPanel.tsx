import {
  Accordion,
  Box,
  Button,
  CloseButton,
  Divider,
  Group,
  Paper,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import type { ReactNode } from 'react';
import { isValidElement, useEffect, useState } from 'react';
import { MAP_DEFAULT_ZOOM } from '../../constants';
import { useMapCameraStore } from '../../stores/mapCameraStore';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import styles from '../../styles/components/map.module.css';
import { RasterLegend } from '../RasterLegend';
import {
  type CanalToggleEntry,
  collectCanalChildIds,
  type EtapaGate,
} from '../shared/canalesGrouping';
import { CollapsibleSection } from '../ui/CollapsibleSection';
import { IconRefresh, IconSearch } from '../ui/icons';
import { ActiveLayersSection } from './ActiveLayersSection';
import {
  displayedAccordionValue,
  idleAccordionValue,
  rememberAccordionChange,
} from './accordionOpenState';
import { buildLayerAccordionItems, LAYER_FAMILIES } from './buildLayerAccordionItems';
import { mergeRasterSearchOptions } from './knownRasterCatalog';
import { LayerOrderSection } from './LayerOrderSection';
import { LeyendaPanel, type LeyendaPanelProps } from './LeyendaPanel';
import { getActiveAttributions } from './layerAttributions';
import { filterCanalEntries } from './layerControlWidgets';
import { buildHealthBannerText, type LayerHealth } from './layerHealth';
import { MapPresetChips } from './MapPresetChips';
import {
  buildFamilyActiveCounts,
  LAYER_CATEGORY,
  type LayerCategory,
  normalizeSearchText,
} from './map2dDerived';
import { pickPresetRasterId } from './mapPresets';

/**
 * Fine-grained per-layer render controls (map-redesign Fase 3 — Tanda B).
 * Grouped into ONE prop object (task 3.4) instead of ~4 loose fields, threaded
 * MapaMapLibre → MapUiPanels → LayerControlsPanel. All slots map 1:1 onto the
 * `mapLayerSyncStore` map2d slots + their setters.
 */
export interface LayerFineControl {
  /** Per-UI-layer opacity MULTIPLIER (0..1). Absent id → untouched default. */
  readonly opacityByLayer: Record<string, number>;
  /** Set a UI layer's opacity multiplier (0..1). `1` resets to the default. */
  readonly onLayerOpacityChange: (layerId: string, multiplier: number) => void;
  /** Current BOTTOM→TOP render order override (empty = hardcoded default). */
  readonly orderByLayer: readonly string[];
  /** Write a FULL bottom→top order (empty array = reset to default). */
  readonly onLayerOrderChange: (orderedIds: string[]) => void;
  /** Multiplier on road + POI label size. `1` = hardcoded default. */
  readonly labelSizeScale: number;
  readonly onLabelSizeScaleChange: (scale: number) => void;
  readonly lineWidthScale: number;
  readonly onLineWidthScaleChange: (scale: number) => void;
}

export interface HazardLayerControl {
  readonly active: boolean;
  readonly activeLayerCount: number;
  readonly onActiveChange: (active: boolean) => void;
  readonly visible: boolean;
}

/**
 * No-op default so panels/tests that don't wire fine-controls keep working —
 * the sliders seed from `?? 1` (untouched) and the order section falls back to
 * `DEFAULT_LAYER_ORDER`.
 */
const NOOP_FINE_CONTROL: LayerFineControl = {
  opacityByLayer: {},
  onLayerOpacityChange: () => {},
  orderByLayer: [],
  onLayerOrderChange: () => {},
  labelSizeScale: 1,
  onLabelSizeScaleChange: () => {},
  lineWidthScale: 1,
  onLineWidthScaleChange: () => {},
};

interface LayerItem {
  id: string;
  label: string;
  category: LayerCategory;
}

// Re-export so consumers still importing CanalToggleEntry from this file
// (MapaMapLibre, MapUiPanels, TerrainViewer3DChrome) keep compiling. The
// type itself now lives in ``shared/canalesGrouping`` and is shared with
// the 3D viewer.
export type { CanalToggleEntry };

interface SelectItem {
  value: string;
  label: string;
  tipo?: string;
}

interface LayerControlsPanelProps {
  /**
   * Selector "Capa base" + slot `viewModePanel`. When BOTH are omitted
   * (typical when the parent renders a separate `MapBaseSelectorPanel`
   * above the map), the "Capa base" segmented control inside the Base
   * accordion item is suppressed.
   */
  readonly baseLayer?: 'osm' | 'satellite';
  readonly onBaseLayerChange?: (value: 'osm' | 'satellite') => void;
  readonly viewModePanel?: ReactNode;
  readonly layerItems: LayerItem[];
  readonly vectorVisibility: Record<string, boolean>;
  readonly onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  readonly showIGNOverlay: boolean;
  readonly onShowIGNOverlayChange: (visible: boolean) => void;
  readonly showHillshade?: boolean;
  readonly onShowHillshadeChange?: (visible: boolean) => void;
  readonly hillshadeAvailable?: boolean;
  readonly demEnabled: boolean;
  readonly showDemOverlay: boolean;
  readonly onShowDemOverlayChange: (visible: boolean) => void;
  readonly activeDemLayerId: string | null;
  readonly onActiveDemLayerIdChange: (value: string | null) => void;
  readonly demOptions: SelectItem[];
  /** UX PDF R7: swipe-compare current raster with another. */
  readonly rasterCompareId?: string | null;
  readonly onRasterCompare?: (layerId: string | null) => void;
  /**
   * Pilar Azul — per-canal relevado items. When provided (along with the
   * propuestos array), the "Canales" accordion item renders. Leaving both
   * arrays unset keeps the panel identical to its pre-Pilar-Azul behavior for
   * tests/pages that don't care.
   */
  readonly canalesRelevadosItems?: readonly CanalToggleEntry[];
  readonly canalesPropuestosItems?: readonly CanalToggleEntry[];
  /**
   * Etapas filter, for the Canales badge (B4c/T3). The map stops drawing the
   * propuestos of an unchecked etapa, so counting them made the badge lie —
   * the same "60 vs 41" as the master gate, through the legend's filter.
   *
   * EVERY PRODUCTION CALLER MUST PASS IT. Build it with `selectEtapaGate`
   * (`useMapLayerSyncStore(selectEtapaGate)`) so its identity stays stable and
   * this memoised panel does not re-render on every store notification.
   *
   * The `null` default is deliberate but NARROW: it exists for fixtures and
   * tests that render the panel with no store behind it, where "no filter" is
   * the truth. It is NOT required (unlike the 4th argument of
   * `collectCanalChildIds`, which IS) because a required prop here would force
   * every existing test render — and the two unrelated render sites in
   * `MapUiPanels`/`MapaMapLibre` — to thread a value they may not have; the
   * REQUIRED gate lives one level down, at the derivation itself, which is the
   * one place a new call site cannot bypass.
   */
  readonly etapaGate?: EtapaGate | null;
  /**
   * Fine-grained per-layer opacity + render-order controls (Fase 3 — Tanda B).
   * Optional: when omitted, a no-op default keeps the panel identical to its
   * pre-Fase-3 behavior (sliders seed from the default, order falls back to
   * `DEFAULT_LAYER_ORDER`).
   */
  readonly layerFineControl?: LayerFineControl;
  /** Operator-only hazard toggle and the raster count it owns. */
  readonly hazardLayerControl?: HazardLayerControl;
  /**
   * Pilar Verde render-payload status (R4-001 / R4-002). The ~1.0 MB GeoJSON
   * group is lazy: it only downloads once a `pilar_verde_*` toggle is on, so
   * the family needs its own feedback — a spinner while it lands and a warning
   * row when it failed. Without them the toggle looks like it did nothing.
   * Optional: omitted → no extra rows, panel unchanged.
   */
  readonly pilarVerdeLayersLoading?: boolean;
  readonly pilarVerdeLayersError?: string | null;
  /**
   * Derived per-family load status (Batch 1 — "datos honestos"). Drives the
   * aggregate banner above the search box and one inline error row per family.
   * Optional: omitted → the panel renders exactly as it did before.
   */
  readonly layerHealth?: LayerHealth;
  /**
   * "Datos al DD/MM/AAAA" per family, from `buildLayerProvenance`. Only the
   * families with a REAL `generated_at` appear — see `layerProvenance.ts`.
   */
  readonly layerProvenance?: Partial<Record<LayerCategory, string>>;
  /** When set, each active row gets that layer's legend (UX PDF R2b). */
  readonly legendPanelProps?: Omit<
    LeyendaPanelProps,
    'onlyForLayerId' | 'floating' | 'embedded' | 'insideScrollContainer'
  >;
  /**
   * AUD-005 (T5) — set when an ANCESTOR already owns a scroll area (the
   * `MapWorkspace` sidebar body on desktop, the layers Drawer on mobile).
   *
   * The panel then renders UNBOUNDED: no viewport-derived `maxHeight`, no
   * `overflow`. Keeping its own bounded scroll inside a scrolling container
   * produced three nested scroll areas (sidebar → controls → legend); with a few
   * toggles on, the legend was pushed below the fold of a viewport-height box
   * that itself lived inside another scroller, and the wheel/touch gesture got
   * trapped in whichever one happened to be under the pointer.
   *
   * Default `false` — the FLOATING variant (`MapUiPanels`) has no scrolling
   * ancestor, so there the panel's own bound is what keeps it on screen.
   */
  readonly insideScrollContainer?: boolean;
  /** UX-02: published satellite overlay listed in En el mapa. */
  readonly satelliteLayer?: { label: string } | null;
  readonly onHideSatellite?: () => void;
  /** UX-11 */
  readonly rasterLoading?: boolean;
  /** UX-12 */
  readonly demLoadError?: string | null;
  readonly onRetryDem?: () => void;
  /** UX PDF T1: 3D omits Base/raster/ajustes; gray unsupported ids. */
  readonly variant?: '2d' | '3d';
  readonly unsupportedLayerIds?: readonly string[];
  /** UX-05: fly the 2D map to a canal explorer row. */
  readonly onFocusCanal?: (id: string) => void;
  /** CART-06: current map zoom; defaults to opening camera. */
  readonly mapZoom?: number;
}

const GLASS_BG = 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))';

/**
 * React Compiler is active → no manual `useMemo`/`useCallback`/`memo`.
 */
export function LayerControlsPanel({
  baseLayer,
  onBaseLayerChange,
  viewModePanel,
  layerItems,
  vectorVisibility,
  onLayerVisibilityChange,
  showIGNOverlay,
  onShowIGNOverlayChange,
  showHillshade = false,
  onShowHillshadeChange,
  hillshadeAvailable = false,
  demEnabled,
  showDemOverlay,
  onShowDemOverlayChange,
  activeDemLayerId,
  onActiveDemLayerIdChange,
  demOptions,
  rasterCompareId = null,
  onRasterCompare,
  canalesRelevadosItems,
  canalesPropuestosItems,
  etapaGate = null,
  layerFineControl = NOOP_FINE_CONTROL,
  hazardLayerControl,
  pilarVerdeLayersLoading = false,
  pilarVerdeLayersError = null,
  layerHealth,
  layerProvenance,
  insideScrollContainer = false,
  satelliteLayer = null,
  onHideSatellite,
  rasterLoading = false,
  demLoadError = null,
  onRetryDem,
  variant = '2d',
  unsupportedLayerIds = [],
  legendPanelProps,
  onFocusCanal,
  mapZoom = MAP_DEFAULT_ZOOM,
}: LayerControlsPanelProps) {
  const liveZoom = useMapCameraStore((state) => state.camera?.zoom);
  const effectiveZoom = liveZoom ?? mapZoom;
  const [query, setQuery] = useState('');
  const [accordionStored, setAccordionStored] = useState<string[] | null>(null);
  // Accent-folded, not just lowercased (R3-003): the labels mix accented
  // ("% Forestacion obligatoria" carries a tilde) and unaccented data-driven
  // names ("Riesgo de Inundacion"), so BOTH sides go through the same fold.
  const normalizedQuery = normalizeSearchText(query.trim());
  const isSearching = normalizedQuery.length > 0;
  const is3d = variant === '3d';
  const unsupportedSet = new Set(unsupportedLayerIds);

  const showCanalesSection =
    (canalesRelevadosItems?.length ?? 0) > 0 || (canalesPropuestosItems?.length ?? 0) > 0;
  const relevadosMaster = !!vectorVisibility.canales_relevados;
  const propuestosMaster = !!vectorVisibility.canales_propuestos;

  // FF1 + B2-2.6: el badge de Canales cuenta los HIJOS visibles (hojas + hijos de
  // grupo), no los masters — un master puede quedar en `true` despues de apagar
  // su ultimo hijo, y el badge quedaba viejo. Pero los masters SI entran como
  // filtro: `collectCanalChildIds` exige `vectorVisibility` (3er argumento, NO
  // es opcional) porque un lado con el master apagado no se dibuja, y contar sus
  // hijos hacia que el badge dijera 60 sobre un mapa con 41 canales.
  const canalesChildIds = collectCanalChildIds(
    canalesRelevadosItems,
    canalesPropuestosItems,
    vectorVisibility,
    etapaGate
  );
  // Fix 3 (T3c): per-family badges and the workspace "N capas activas" badge now
  // share ONE derivation, so they cannot disagree.
  const familyActiveCounts = buildFamilyActiveCounts({
    layerItems,
    vectorVisibility,
    canalChildIds: canalesChildIds,
    showIGNOverlay,
    showHillshade,
    showDemOverlay,
    showSatellite: Boolean(satelliteLayer),
  });
  const canalesActiveCount = familyActiveCounts[LAYER_CATEGORY.CANALES];

  // FF2: canal entries are searchable. When the query is the "canal(es)"
  // keyword we surface the whole section; otherwise we pass label-filtered
  // entries so individual canals are findable.
  const canalKeyword = normalizedQuery.length >= 3 && 'canales'.startsWith(normalizedQuery);
  const filteredRelevados = filterCanalEntries(canalesRelevadosItems, normalizedQuery);
  const filteredPropuestos = filterCanalEntries(canalesPropuestosItems, normalizedQuery);
  const relevadosToRender = !isSearching
    ? canalesRelevadosItems
    : canalKeyword
      ? canalesRelevadosItems
      : filteredRelevados;
  const propuestosToRender = !isSearching
    ? canalesPropuestosItems
    : canalKeyword
      ? canalesPropuestosItems
      : filteredPropuestos;
  const showCanalesDuringSearch =
    canalKeyword || filteredRelevados.length > 0 || filteredPropuestos.length > 0;

  const visibleSet = new Set<string>();
  for (const [id, visible] of Object.entries(vectorVisibility)) {
    if (visible) visibleSet.add(id);
  }
  const activeAttributions = getActiveAttributions(visibleSet);

  // Aggregate health: the banner counts FAILED families only (a family still
  // `cargando` has not failed yet — see `layerHealth.ts`).
  const failed = layerHealth?.failed ?? [];
  const bannerText = buildHealthBannerText(failed);
  // A degraded raster source has no `reload` (tiles retry themselves on the next
  // pan/zoom). Offering a button that calls nothing would be worse than showing
  // none, so the banner only grows one when SOMETHING can actually be retried.
  const canRetryAll = failed.some((entry) => entry.reload !== null);
  // Canales is rendered by its own accordion branch below, so it reads the
  // registry here instead of inside the shared vector-family loop.
  const canalesHealth = layerHealth?.byCategory[LAYER_CATEGORY.CANALES] ?? null;
  const canalesProvenance = layerProvenance?.[LAYER_CATEGORY.CANALES] ?? null;

  const hideAllCatalogLayers = useMapLayerSyncStore((state) => state.hideAllCatalogLayers);
  const restoreCatalogDefaults = useMapLayerSyncStore((state) => state.restoreCatalogDefaults);
  const ignActiveId = '__ign';
  const demActiveId = '__dem';
  const legendFor = (layerId: string) =>
    legendPanelProps ? (
      <LeyendaPanel {...legendPanelProps} onlyForLayerId={layerId} embedded />
    ) : undefined;

  const activeLayerRows = [
    ...layerItems
      .filter((item) => vectorVisibility[item.id])
      .map((item) => ({ id: item.id, label: item.label, legend: legendFor(item.id) })),
    ...(showIGNOverlay ? [{ id: ignActiveId, label: 'IGN Altimetría' }] : []),
    ...(showHillshade ? [{ id: '__hillshade', label: 'Relieve sombreado' }] : []),
    ...(showDemOverlay
      ? [
          {
            id: demActiveId,
            label: `${demOptions.find((option) => option.value === activeDemLayerId)?.label ?? 'Capa DEM'}${rasterLoading ? ' · cargando' : ''}`,
            legend: (() => {
              const tipo = demOptions.find((option) => option.value === activeDemLayerId)?.tipo;
              if (tipo) {
                return <RasterLegend layers={[{ tipo }]} floating={false} />;
              }
              return legendFor(demActiveId);
            })(),
          },
        ]
      : []),
    ...(hazardLayerControl?.active
      ? [{ id: '__hazard', label: 'Visor de riesgos', legend: legendFor('__hazard') }]
      : []),
    ...(satelliteLayer ? [{ id: '__satellite', label: satelliteLayer.label }] : []),
  ];

  const firstDemLayerId = demOptions[0]?.value ?? null;

  useEffect(() => {
    if (is3d) return;
    if (!showDemOverlay || !firstDemLayerId) return;
    const activeLayerExists = demOptions.some((option) => option.value === activeDemLayerId);
    if (!activeLayerExists) {
      onActiveDemLayerIdChange(firstDemLayerId);
    }
  }, [activeDemLayerId, demOptions, firstDemLayerId, is3d, onActiveDemLayerIdChange, showDemOverlay]);

  const handleDemOverlayChange = (visible: boolean) => {
    if (visible && !activeDemLayerId && firstDemLayerId) {
      onActiveDemLayerIdChange(firstDemLayerId);
    }
    onShowDemOverlayChange(visible);
  };

  // Vector items after applying the search filter (React Compiler memoizes this
  // — no manual `useMemo`).
  const filteredLayerItems = isSearching
    ? layerItems.filter((item) => normalizeSearchText(item.label).includes(normalizedQuery))
    : layerItems;

  // FF-T3c: raster/DEM options (riesgo hídrico, drenaje, terreno…) live in
  // Análisis raster. Search still has to find them — they were invisible when
  // scanned `layerItems` — typing "riesgo" answered "Sin resultados" about a
  // layer the map can absolutely paint. They now get their own results section.
  const rasterSearchMatches = isSearching
    ? mergeRasterSearchOptions(demOptions, query).filter((option) =>
        normalizeSearchText(option.label).includes(normalizedQuery)
      )
    : [];

  /** Activate one raster option from the search results: select it AND turn the DEM overlay on. */
  const handleRasterSearchSelect = (value: string) => {
    onActiveDemLayerIdChange(value);
    onShowDemOverlayChange(true);
  };

  const accordionItems = buildLayerAccordionItems({
    is3d,
    isSearching,
    normalizedQuery,
    familyActiveCounts,
    demEnabled,
    showDemOverlay,
    onShowDemOverlayChange,
    baseLayer,
    onBaseLayerChange,
    showIGNOverlay,
    onShowIGNOverlayChange,
    hillshadeAvailable,
    onShowHillshadeChange,
    showHillshade,
    hazardLayerControl,
    layerHealth,
    showCanalesSection,
    canalesHealth,
    showCanalesDuringSearch,
    canalesActiveCount,
    relevadosToRender,
    relevadosMaster,
    vectorVisibility,
    onLayerVisibilityChange,
    propuestosToRender,
    propuestosMaster,
    onFocusCanal,
    canalesProvenance,
    filteredLayerItems,
    activeAttributions,
    pilarVerdeLayersLoading,
    pilarVerdeLayersError,
    layerProvenance,
    layerFineControl,
    effectiveZoom,
    unsupportedSet,
    demOptions,
    demLoadError,
    rasterSearchMatches,
    query,
    rasterLoading,
    activeDemLayerId,
    handleDemOverlayChange,
    handleRasterSearchSelect,
    onRetryDem,
    rasterCompareId,
    onRasterCompare,
  });

  return (
    // Bounded outer scroll container: when many layer toggles, DEM options
    // and attributions are active, the stack used to grow past the viewport
    // and collide with the bottom-left `LeyendaPanel`. We cap the whole
    // top-left stack at `calc(100vh - 180px)` and let it scroll internally.
    // Inside the sidebar/Drawer that bound is HARMFUL instead (T5) — the
    // container is already the scroller, so the panel grows freely there.
    <Box
      data-testid="layer-controls-panel-scroll"
      className={styles.layerTogglesRoot}
      role="region"
      aria-label="Controles de capas del mapa"
      data-inside-scroll-container={insideScrollContainer ? 'true' : 'false'}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        ...(insideScrollContainer
          ? { overflow: 'visible' }
          : {
              maxHeight: 'calc(100vh - 180px)',
              overflowY: 'auto',
              overflowX: 'hidden',
            }),
      }}
    >
      {viewModePanel}

      <MapPresetChips
        onApplyRaster={(presetId) => {
          const rasterId = pickPresetRasterId(presetId, demOptions);
          if (!rasterId) return;
          onActiveDemLayerIdChange(rasterId);
          onShowDemOverlayChange(true);
        }}
      />

      <ActiveLayersSection
        rows={activeLayerRows}
        onRemove={(id) => {
          if (id === ignActiveId) {
            onShowIGNOverlayChange(false);
            return;
          }
          if (id === demActiveId) {
            onShowDemOverlayChange(false);
            return;
          }
          if (id === '__hazard') {
            hazardLayerControl?.onActiveChange(false);
            return;
          }
          if (id === '__satellite') {
            onHideSatellite?.();
            return;
          }
          if (id === '__hillshade') {
            onShowHillshadeChange?.(false);
            return;
          }
          onLayerVisibilityChange(id, false);
        }}
        onClearAll={() => {
          hideAllCatalogLayers('map2d');
          onShowIGNOverlayChange(false);
          onShowDemOverlayChange(false);
          onShowHillshadeChange?.(false);
          hazardLayerControl?.onActiveChange(false);
          onHideSatellite?.();
        }}
        onRestore={() => {
          restoreCatalogDefaults('map2d');
          onShowIGNOverlayChange(false);
          onShowDemOverlayChange(false);
        }}
        opacityByLayer={layerFineControl.opacityByLayer}
        onLayerOpacityChange={layerFineControl.onLayerOpacityChange}
      />

      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{ background: GLASS_BG, backdropFilter: 'blur(6px)' }}
      >
        <Stack gap={6}>
          {bannerText && (
            <Group gap={6} wrap="nowrap" align="center" data-testid="layer-health-banner">
              <Text size="xs" c="red" style={{ flex: 1 }}>
                ⚠ {bannerText}
              </Text>
              {canRetryAll && (
                <Button
                  size="xs"
                  variant="subtle"
                  color="red"
                  leftSection={<IconRefresh size={12} />}
                  data-testid="layer-health-retry-all"
                  onClick={() => layerHealth?.retryAll()}
                >
                  Reintentar
                </Button>
              )}
            </Group>
          )}
          <TextInput
            size="xs"
            aria-label="Buscar capa"
            placeholder="Buscar capa…"
            leftSection={<IconSearch size={14} />}
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            rightSection={
              isSearching ? (
                <CloseButton size="sm" aria-label="Limpiar búsqueda" onClick={() => setQuery('')} />
              ) : null
            }
          />
          {accordionItems.length > 0 ? (
            <Accordion
              multiple
              chevronPosition="right"
              keepMounted
              keepMountedMode="display-none"
              value={displayedAccordionValue(
                isSearching,
                accordionStored,
                idleAccordionValue(
                  LAYER_FAMILIES.filter((family) => familyActiveCounts[family.value] > 0).map(
                    (family) => family.value
                  ),
                  Boolean(showDemOverlay)
                ),
                accordionItems.flatMap((node) =>
                  isValidElement(node) && node.key != null ? [String(node.key)] : []
                )
              )}
              onChange={(next) => {
                const list = Array.isArray(next) ? next : next ? [next] : [];
                setAccordionStored(rememberAccordionChange(isSearching, list, accordionStored));
              }}
              styles={{ content: { padding: '8px' } }}
            >
              {accordionItems}
            </Accordion>
          ) : (
            // FF3: a search that matches nothing shows a hint instead of a
            // blank panel (recoverable via the clear button).
            <Text size="xs" c="dimmed" data-testid="layer-controls-no-results">
              Sin resultados para «{query}»
            </Text>
          )}
          {/*
            Orden de capas (task 3.5). Hidden while searching to keep the
            filtered view focused. Renders the FULL reorderable set (active +
            dimmed inactive) so every write is a complete bottom→top order —
            the contract `applyLayerOrder` requires.
          */}
          {!isSearching && (
            <>
              <Divider my={4} />
              <CollapsibleSection
                title="Orden de capas"
                titleSize="xs"
                defaultOpen={false}
                testId="layer-order-collapsible"
              >
                <LayerOrderSection
                  orderByLayer={layerFineControl.orderByLayer}
                  onLayerOrderChange={layerFineControl.onLayerOrderChange}
                  vectorVisibility={vectorVisibility}
                  labelById={Object.fromEntries(layerItems.map((item) => [item.id, item.label]))}
                  /* SUG-1 — coherence with the OFFER gate: `road_flow` is the
                     one reorderable layer whose selector entry is role-gated
                     (staff only, `buildVectorLayerItems`), so a session that is
                     not offered the layer is not offered a row for it either.
                     The check is "did the selector offer it", not a second copy
                     of the role rule. It is deliberately NOT generalised to
                     "everything missing from layerItems": several reorderable
                     ids (canales masters, escuelas) never appear there and must
                     keep their rows. */
                  hiddenIds={
                    layerItems.some((item) => item.id === 'road_flow')
                      ? undefined
                      : [
                          'road_flow',
                          'sentido_camino',
                          'puntos_interes',
                          'red_vial_oficial',
                          'caminos_huecos',
                        ]
                  }
                />
              </CollapsibleSection>
            </>
          )}
        </Stack>
      </Paper>
    </Box>
  );
}
