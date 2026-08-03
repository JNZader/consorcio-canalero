import {
  Accordion,
  ActionIcon,
  Badge,
  Box,
  Button,
  Checkbox,
  CloseButton,
  Divider,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  Select,
  Slider,
  Stack,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import type { ComponentType, ReactNode } from 'react';
import { useEffect, useState } from 'react';

import { CanalesLayerSection } from '../shared/CanalesLayerSection';
import styles from '../../styles/components/map.module.css';
import { type CanalToggleEntry, collectCanalChildIds } from '../shared/canalesGrouping';
import { CollapsibleSection } from '../ui/CollapsibleSection';
import {
  IconChartBar,
  IconDroplet,
  IconMap,
  IconMapPin,
  IconPlant,
  IconRefresh,
  IconRoute,
  IconSearch,
} from '../ui/icons';
import { LayerOrderSection } from './LayerOrderSection';
import { getActiveAttributions } from './layerAttributions';
import { buildHealthBannerText, type LayerHealth } from './layerHealth';
import { RENDERABLE_UI_LAYER_IDS } from './layerRenderRegistry';
import {
  buildFamilyActiveCounts,
  LAYER_CATEGORY,
  type LayerCategory,
  normalizeSearchText,
} from './map2dDerived';

const RENDERABLE_UI_LAYER_ID_SET = new Set<string>(RENDERABLE_UI_LAYER_IDS);

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
  readonly demEnabled: boolean;
  readonly showDemOverlay: boolean;
  readonly onShowDemOverlayChange: (visible: boolean) => void;
  readonly activeDemLayerId: string | null;
  readonly onActiveDemLayerIdChange: (value: string | null) => void;
  readonly demOptions: SelectItem[];
  /**
   * Pilar Azul — per-canal relevado items. When provided (along with the
   * propuestos array), the "Canales" accordion item renders. Leaving both
   * arrays unset keeps the panel identical to its pre-Pilar-Azul behavior for
   * tests/pages that don't care.
   */
  readonly canalesRelevadosItems?: readonly CanalToggleEntry[];
  readonly canalesPropuestosItems?: readonly CanalToggleEntry[];
  /**
   * Fine-grained per-layer opacity + render-order controls (Fase 3 — Tanda B).
   * Optional: when omitted, a no-op default keeps the panel identical to its
   * pre-Fase-3 behavior (sliders seed from the default, order falls back to
   * `DEFAULT_LAYER_ORDER`).
   */
  readonly layerFineControl?: LayerFineControl;
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
}

type LayerFamilyIcon = ComponentType<{ size?: number }>;

/**
 * Family metadata for the layer accordion (change `rediseno-ux-mapa`). Order
 * is LOCKED: Base → Hidrografía → Territorio → Pilar Verde → Canales →
 * Análisis. Icons come from the app's Tabler wrapper (`ui/icons`) — no new
 * dependency added.
 */
const LAYER_FAMILIES: ReadonlyArray<{
  value: LayerCategory;
  label: string;
  Icon: LayerFamilyIcon;
}> = [
  { value: LAYER_CATEGORY.BASE, label: 'Base', Icon: IconMap },
  {
    value: LAYER_CATEGORY.HIDROGRAFIA,
    label: 'Hidrografía',
    Icon: IconDroplet,
  },
  { value: LAYER_CATEGORY.TERRITORIO, label: 'Territorio', Icon: IconMapPin },
  { value: LAYER_CATEGORY.PILAR_VERDE, label: 'Pilar Verde', Icon: IconPlant },
  { value: LAYER_CATEGORY.CANALES, label: 'Canales', Icon: IconRoute },
  { value: LAYER_CATEGORY.ANALISIS, label: 'Análisis', Icon: IconChartBar },
];

const GLASS_BG = 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))';

/**
 * User-facing labels of the structural Base controls, so the Base accordion
 * item stays discoverable via the search box (change rediseno-ux-mapa FF2).
 * Folded through `normalizeSearchText` (lowercase + accent-stripped) so they
 * match the query the same way every other label does (R3-003).
 */
const BASE_SEARCH_LABELS = [
  'base',
  'capa base',
  'osm',
  'satélite',
  'ign altimetría',
  'capa dem',
].map(normalizeSearchText);

/**
 * Filter canal entries by label for the search box (FF2). A `leaf` matches on
 * its own label; a `group` is kept WHOLE when the group label OR any child
 * label matches (we never partially filter a group's children).
 *
 * `query` MUST already be normalized by `normalizeSearchText` — labels are
 * folded here so an accented canal name is reachable without typing accents.
 */
function filterCanalEntries(
  entries: readonly CanalToggleEntry[] | undefined,
  query: string
): CanalToggleEntry[] {
  if (!entries) return [];
  return entries.filter((entry) => {
    if (entry.kind === 'leaf') return normalizeSearchText(entry.label).includes(query);
    return (
      normalizeSearchText(entry.label).includes(query) ||
      entry.children.some((child) => normalizeSearchText(child.label).includes(query))
    );
  });
}

/**
 * Compact per-layer opacity slider (task 3.3). Rendered only for an ACTIVE
 * layer that is in the render registry. Value is the 0..100 % view of the
 * store's 0..1 multiplier; the ↺ button resets the multiplier to 1 (Tanda A
 * made multiplier===1 restore the true hardcoded default).
 */
function LayerOpacityControl({
  layerId,
  label,
  multiplier,
  onChange,
}: {
  layerId: string;
  label: string;
  multiplier: number;
  onChange: (layerId: string, multiplier: number) => void;
}) {
  const percent = Math.round(multiplier * 100);
  return (
    <Group gap={6} wrap="nowrap" pl={26} pr={4} data-testid={`layer-opacity-${layerId}`}>
      <Slider
        style={{ flex: 1 }}
        min={0}
        max={100}
        step={1}
        value={percent}
        onChange={(value) => onChange(layerId, value / 100)}
        label={(value) => `${value}%`}
        thumbLabel={`Opacidad de ${label}`}
      />
      <Text size="9px" c="dimmed" w={28} ta="right">
        {percent}%
      </Text>
      <Tooltip label="Restablecer opacidad" withArrow>
        <ActionIcon
          variant="subtle"
          size="sm"
          color="gray"
          aria-label={`Restablecer opacidad de ${label}`}
          data-testid={`layer-opacity-reset-${layerId}`}
          onClick={() => onChange(layerId, 1)}
        >
          <IconRefresh size={12} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

/**
 * Inline failure row for ONE layer family. Generalized from the old
 * pilar-verde-only markup; `testId` stays a parameter because the Pilar Verde
 * row keeps its historical `pilar-verde-layers-error` id (two tests pin it).
 */
function LayerHealthErrorRow({
  testId,
  message,
  onRetry,
}: {
  testId: string;
  message: string;
  onRetry?: (() => void) | null;
}) {
  return (
    <Group gap={6} wrap="nowrap" align="center">
      <Text size="xs" c="red" data-testid={testId} style={{ flex: 1 }}>
        {message}
      </Text>
      {onRetry && (
        <Button
          size="compact-xs"
          variant="subtle"
          color="red"
          leftSection={<IconRefresh size={12} />}
          onClick={onRetry}
        >
          Reintentar
        </Button>
      )}
    </Group>
  );
}

/**
 * Resolve the inline failure row for one family, or `null` when it is healthy.
 *
 * Pilar Verde keeps its legacy contract: while the `pilarVerdeLayersError` prop
 * is set it wins over the registry, so its historical copy AND its
 * `pilar-verde-layers-error` testid survive untouched (two tests pin them).
 * Extracted from the render loop to keep that precedence in ONE readable place.
 */
function resolveFamilyHealthRow(
  category: LayerCategory,
  isPilarVerde: boolean,
  pilarVerdeLayersError: string | null,
  layerHealth: LayerHealth | undefined
): { testId: string; message: string; onRetry: (() => void) | null } | null {
  const entry = layerHealth?.byCategory[category] ?? null;
  if (isPilarVerde && pilarVerdeLayersError) {
    return {
      testId: 'pilar-verde-layers-error',
      message: 'No se pudieron cargar las capas — reintentá',
      onRetry: entry?.reload ?? null,
    };
  }
  if (!entry?.message) return null;
  return {
    testId: isPilarVerde ? 'pilar-verde-layers-error' : `layer-health-error-${category}`,
    message: entry.message,
    onRetry: entry.reload,
  };
}

/** Dimmed "Datos al …" footer line, sibling of the attribution lines. */
function LayerProvenanceLine({ category, text }: { category: LayerCategory; text: string }) {
  return (
    <Text size="xs" c="dimmed" data-testid={`layer-provenance-${category}`}>
      {text}
    </Text>
  );
}

function FamilyControlLabel({ label, count }: { label: string; count: number }) {
  return (
    <Group gap="xs" justify="space-between" wrap="nowrap" style={{ flex: 1 }}>
      <Text size="xs" fw={600}>
        {label}
      </Text>
      {count > 0 && (
        <Badge size="xs" variant="light" color="blue">
          {count}
        </Badge>
      )}
    </Group>
  );
}

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
  demEnabled,
  showDemOverlay,
  onShowDemOverlayChange,
  activeDemLayerId,
  onActiveDemLayerIdChange,
  demOptions,
  canalesRelevadosItems,
  canalesPropuestosItems,
  layerFineControl = NOOP_FINE_CONTROL,
  pilarVerdeLayersLoading = false,
  pilarVerdeLayersError = null,
  layerHealth,
  layerProvenance,
}: LayerControlsPanelProps) {
  const [query, setQuery] = useState('');
  // Accent-folded, not just lowercased (R3-003): the labels mix accented
  // ("% Forestacion obligatoria" carries a tilde) and unaccented data-driven
  // names ("Riesgo de Inundacion"), so BOTH sides go through the same fold.
  const normalizedQuery = normalizeSearchText(query.trim());
  const isSearching = normalizedQuery.length > 0;

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
    vectorVisibility
  );
  // Fix 3 (T3c): per-family badges and the workspace "N capas activas" badge now
  // share ONE derivation, so they cannot disagree.
  const familyActiveCounts = buildFamilyActiveCounts({
    layerItems,
    vectorVisibility,
    canalChildIds: canalesChildIds,
    showIGNOverlay,
    showDemOverlay,
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

  const firstDemLayerId = demOptions[0]?.value ?? null;

  useEffect(() => {
    if (!showDemOverlay || !firstDemLayerId) return;
    const activeLayerExists = demOptions.some((option) => option.value === activeDemLayerId);
    if (!activeLayerExists) {
      onActiveDemLayerIdChange(firstDemLayerId);
    }
  }, [activeDemLayerId, demOptions, firstDemLayerId, onActiveDemLayerIdChange, showDemOverlay]);

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

  // FF-T3c: the raster/DEM options (riesgo hídrico, drenaje, terreno…) live in
  // the Base > "Capa DEM" Select, so they were invisible to a search that only
  // scanned `layerItems` — typing "riesgo" answered "Sin resultados" about a
  // layer the map can absolutely paint. They now get their own results section.
  const rasterSearchMatches =
    isSearching && demEnabled
      ? demOptions.filter((option) => normalizeSearchText(option.label).includes(normalizedQuery))
      : [];

  /** Activate one raster option from the search results: select it AND turn the DEM overlay on. */
  const handleRasterSearchSelect = (value: string) => {
    onActiveDemLayerIdChange(value);
    onShowDemOverlayChange(true);
  };

  const accordionItems: ReactNode[] = [];

  for (const family of LAYER_FAMILIES) {
    const Icon = family.Icon;

    // ── Base: structural controls (capa base / IGN / DEM), NOT in layerItems.
    if (family.value === LAYER_CATEGORY.BASE) {
      // FF2: Base stays searchable by its control labels (Capa base / IGN /
      // Capa DEM / OSM / Satélite).
      if (isSearching && !BASE_SEARCH_LABELS.some((label) => label.includes(normalizedQuery))) {
        continue;
      }
      const baseActiveCount = familyActiveCounts[LAYER_CATEGORY.BASE];
      // The DEM catalog (`geo_layers`) lives in BASE, and this branch `continue`s
      // before the shared vector-family loop — without this row the banner would
      // count a failure the panel never explains.
      const baseHealthRow = resolveFamilyHealthRow(family.value, false, null, layerHealth);
      accordionItems.push(
        <Accordion.Item key={family.value} value={family.value} data-testid="layer-controls-capas">
          <Accordion.Control icon={<Icon size={16} />}>
            <FamilyControlLabel label={family.label} count={baseActiveCount} />
          </Accordion.Control>
          <Accordion.Panel>
            <Stack gap={4}>
              {baseHealthRow && (
                <LayerHealthErrorRow
                  testId={baseHealthRow.testId}
                  message={baseHealthRow.message}
                  onRetry={baseHealthRow.onRetry}
                />
              )}
              {baseLayer !== undefined && onBaseLayerChange && (
                <>
                  <Text size="xs" fw={600} c="dimmed">
                    Capa base
                  </Text>
                  <SegmentedControl
                    size="xs"
                    aria-label="Seleccionar capa base"
                    value={baseLayer}
                    onChange={(value) => onBaseLayerChange(value as 'osm' | 'satellite')}
                    data={[
                      { value: 'osm', label: 'OSM' },
                      { value: 'satellite', label: 'Satélite' },
                    ]}
                  />
                  <Divider my={4} />
                </>
              )}
              <Checkbox
                label="IGN Altimetría"
                checked={showIGNOverlay}
                onChange={(event) => onShowIGNOverlayChange(event.currentTarget.checked)}
              />
              {demEnabled && (
                <>
                  <Checkbox
                    label="Capa DEM"
                    checked={showDemOverlay}
                    onChange={(event) => handleDemOverlayChange(event.currentTarget.checked)}
                  />
                  {showDemOverlay && (
                    <Select
                      size="xs"
                      aria-label="Tipo de capa DEM"
                      placeholder="Tipo de capa"
                      value={activeDemLayerId}
                      onChange={onActiveDemLayerIdChange}
                      data={demOptions}
                    />
                  )}
                </>
              )}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      );
      continue;
    }

    // ── Canales: shared master + per-canal section (Pilar Azul).
    if (family.value === LAYER_CATEGORY.CANALES) {
      // `showCanalesSection` is data-driven: when index.json fails outright there
      // are no entries, so the whole item used to disappear — the one case where
      // the user MOST needs to be told something broke.
      if (!showCanalesSection && !canalesHealth) continue;
      // FF2: keep the section reachable while searching (keyword or a matching
      // canal label); otherwise it hides like any non-matching family.
      if (isSearching && !showCanalesDuringSearch) continue;
      accordionItems.push(
        <Accordion.Item
          key={family.value}
          value={family.value}
          data-testid="layer-controls-canales"
        >
          <Accordion.Control icon={<Icon size={16} />}>
            <FamilyControlLabel label={family.label} count={canalesActiveCount} />
          </Accordion.Control>
          <Accordion.Panel>
            <Stack gap={6}>
              {canalesHealth?.message && (
                <LayerHealthErrorRow
                  testId={`layer-health-error-${family.value}`}
                  message={canalesHealth.message}
                  onRetry={canalesHealth.reload}
                />
              )}
              <CanalesLayerSection
                side="relevados"
                entries={relevadosToRender}
                masterFlag="canales_relevados"
                masterOn={relevadosMaster}
                vectorVisibility={vectorVisibility}
                onLayerVisibilityChange={onLayerVisibilityChange}
              />
              <CanalesLayerSection
                side="propuestos"
                entries={propuestosToRender}
                masterFlag="canales_propuestos"
                masterOn={propuestosMaster}
                vectorVisibility={vectorVisibility}
                onLayerVisibilityChange={onLayerVisibilityChange}
              />
              {/*
                Etapas filter (Alta → Largo plazo) for propuestos lives in
                ``LeyendaPanel`` as interactive checkboxes — single source of
                truth for both swatch colors AND toggle controls.
              */}
              {canalesProvenance && (
                <LayerProvenanceLine category={family.value} text={canalesProvenance} />
              )}
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      );
      continue;
    }

    // ── Vector families: Hidrografía / Territorio / Pilar Verde / Análisis.
    const familyVisible = filteredLayerItems.filter((item) => item.category === family.value);
    const isAnalisis = family.value === LAYER_CATEGORY.ANALISIS;
    // Análisis carries the IDECor attribution footer. Show it when not
    // searching so the credit stays visible even if the only Análisis layer
    // (puntos_conflicto) is absent.
    const showAttributions = isAnalisis && !isSearching && activeAttributions.length > 0;

    if (familyVisible.length === 0 && !showAttributions) continue;

    const familyActiveCount = familyActiveCounts[family.value];
    // Pilar Verde is the only family whose render payload is lazy (~1.0 MB,
    // fetched on first toggle), so it is the only one that needs in-panel
    // status: a spinner while the group lands (R4-002) and a warning row when
    // the group failed (R4-001) — otherwise the toggle just looks broken.
    const isPilarVerde = family.value === LAYER_CATEGORY.PILAR_VERDE;
    const showPilarVerdeSpinner = isPilarVerde && pilarVerdeLayersLoading && familyActiveCount > 0;
    const familyHealthRow = resolveFamilyHealthRow(
      family.value,
      isPilarVerde,
      pilarVerdeLayersError,
      layerHealth
    );
    const familyProvenance = layerProvenance?.[family.value] ?? null;

    accordionItems.push(
      <Accordion.Item key={family.value} value={family.value}>
        <Accordion.Control icon={<Icon size={16} />}>
          <Group gap={6} wrap="nowrap" style={{ flex: 1 }}>
            <FamilyControlLabel label={family.label} count={familyActiveCount} />
            {showPilarVerdeSpinner && <Loader size={12} data-testid="pilar-verde-layers-loading" />}
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap={4}>
            {familyHealthRow && (
              <LayerHealthErrorRow
                testId={familyHealthRow.testId}
                message={familyHealthRow.message}
                onRetry={familyHealthRow.onRetry}
              />
            )}
            {familyVisible.map((item) => {
              const isOn = !!vectorVisibility[item.id];
              const showOpacity = isOn && RENDERABLE_UI_LAYER_ID_SET.has(item.id);
              return (
                <Box key={item.id}>
                  <Checkbox
                    label={item.label}
                    checked={isOn}
                    onChange={(event) =>
                      onLayerVisibilityChange(item.id, event.currentTarget.checked)
                    }
                  />
                  {/*
                    FF-B3: the slider is gated on `isOn`, but a persisted
                    non-1 opacity is INTENTIONALLY preserved while the layer is
                    off (`toggleLayer` never clears `opacityByLayer[id]`) and is
                    re-applied on re-enable — do NOT "fix" this into a clear.
                  */}
                  {showOpacity && (
                    <LayerOpacityControl
                      layerId={item.id}
                      label={item.label}
                      multiplier={layerFineControl.opacityByLayer[item.id] ?? 1}
                      onChange={layerFineControl.onLayerOpacityChange}
                    />
                  )}
                </Box>
              );
            })}
            {showAttributions && (
              <>
                {familyVisible.length > 0 && <Divider my={4} />}
                {activeAttributions.map((text) => (
                  <Text key={text} size="xs" c="dimmed">
                    {text}
                  </Text>
                ))}
              </>
            )}
            {familyProvenance && (
              <LayerProvenanceLine category={family.value} text={familyProvenance} />
            )}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    );
  }

  if (rasterSearchMatches.length > 0) {
    accordionItems.push(
      <Accordion.Item key="raster-search" value="raster-search" data-testid="layer-controls-raster">
        <Accordion.Control icon={<IconChartBar size={16} />}>
          <FamilyControlLabel label="Capas raster" count={showDemOverlay ? 1 : 0} />
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap={4}>
            {rasterSearchMatches.map((option) => (
              <Checkbox
                key={option.value}
                label={option.label}
                data-testid={`raster-search-option-${option.value}`}
                checked={showDemOverlay && activeDemLayerId === option.value}
                onChange={(event) => {
                  if (event.currentTarget.checked) {
                    handleRasterSearchSelect(option.value);
                  } else {
                    onShowDemOverlayChange(false);
                  }
                }}
              />
            ))}
            <Text size="9px" c="dimmed">
              Se muestra una capa raster por vez (Base › Capa DEM).
            </Text>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    );
  }

  return (
    // Bounded outer scroll container: when many layer toggles, DEM options
    // and attributions are active, the stack used to grow past the viewport
    // and collide with the bottom-left `LeyendaPanel`. We cap the whole
    // top-left stack at `calc(100vh - 180px)` and let it scroll internally.
    <Box
      data-testid="layer-controls-panel-scroll"
      className={styles.layerTogglesRoot}
      role="region"
      aria-label="Controles de capas del mapa"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        maxHeight: 'calc(100vh - 180px)',
        overflowY: 'auto',
        overflowX: 'hidden',
      }}
    >
      {viewModePanel}

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
                  size="compact-xs"
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
              defaultValue={[...LAYER_FAMILIES.map((family) => family.value), 'raster-search']}
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
                />
              </CollapsibleSection>
            </>
          )}
        </Stack>
      </Paper>
    </Box>
  );
}
