import {
  Accordion,
  Badge,
  Box,
  Checkbox,
  CloseButton,
  Divider,
  Group,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import type { ComponentType, ReactNode } from 'react';
import { useEffect, useState } from 'react';

import { CanalesLayerSection } from '../shared/CanalesLayerSection';
import { type CanalToggleEntry, collectChildIds } from '../shared/canalesGrouping';
import {
  IconChartBar,
  IconDroplet,
  IconMap,
  IconMapPin,
  IconPlant,
  IconRoute,
  IconSearch,
} from '../ui/icons';
import { getActiveAttributions } from './layerAttributions';
import { LAYER_CATEGORY, type LayerCategory } from './map2dDerived';

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
  { value: LAYER_CATEGORY.HIDROGRAFIA, label: 'Hidrografía', Icon: IconDroplet },
  { value: LAYER_CATEGORY.TERRITORIO, label: 'Territorio', Icon: IconMapPin },
  { value: LAYER_CATEGORY.PILAR_VERDE, label: 'Pilar Verde', Icon: IconPlant },
  { value: LAYER_CATEGORY.CANALES, label: 'Canales', Icon: IconRoute },
  { value: LAYER_CATEGORY.ANALISIS, label: 'Análisis', Icon: IconChartBar },
];

const GLASS_BG = 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))';

/**
 * User-facing labels of the structural Base controls, so the Base accordion
 * item stays discoverable via the search box (change rediseno-ux-mapa FF2).
 * Kept lowercased for case-insensitive `.includes` matching.
 */
const BASE_SEARCH_LABELS = [
  'base',
  'capa base',
  'osm',
  'satélite',
  'ign altimetría',
  'capa dem',
] as const;

/**
 * Filter canal entries by label for the search box (FF2). A `leaf` matches on
 * its own label; a `group` is kept WHOLE when the group label OR any child
 * label matches (we never partially filter a group's children).
 */
function filterCanalEntries(
  entries: readonly CanalToggleEntry[] | undefined,
  query: string
): CanalToggleEntry[] {
  if (!entries) return [];
  return entries.filter((entry) => {
    if (entry.kind === 'leaf') return entry.label.toLowerCase().includes(query);
    return (
      entry.label.toLowerCase().includes(query) ||
      entry.children.some((child) => child.label.toLowerCase().includes(query))
    );
  });
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
}: LayerControlsPanelProps) {
  const [query, setQuery] = useState('');
  const normalizedQuery = query.trim().toLowerCase();
  const isSearching = normalizedQuery.length > 0;

  const showCanalesSection =
    (canalesRelevadosItems?.length ?? 0) > 0 || (canalesPropuestosItems?.length ?? 0) > 0;
  const relevadosMaster = !!vectorVisibility.canales_relevados;
  const propuestosMaster = !!vectorVisibility.canales_propuestos;

  // FF1: the Canales badge counts the ACTUAL visible canal children (leaves +
  // group children), NOT the master flags — a master can stay `true` after its
  // last child is toggled off, which used to leave the badge stale.
  const canalesChildIds = [
    ...collectChildIds(canalesRelevadosItems),
    ...collectChildIds(canalesPropuestosItems),
  ];
  const canalesActiveCount = canalesChildIds.reduce(
    (count, id) => (vectorVisibility[id] ? count + 1 : count),
    0
  );

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
    ? layerItems.filter((item) => item.label.toLowerCase().includes(normalizedQuery))
    : layerItems;

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
      const baseActiveCount = (showIGNOverlay ? 1 : 0) + (showDemOverlay ? 1 : 0);
      accordionItems.push(
        <Accordion.Item key={family.value} value={family.value} data-testid="layer-controls-capas">
          <Accordion.Control icon={<Icon size={16} />}>
            <FamilyControlLabel label={family.label} count={baseActiveCount} />
          </Accordion.Control>
          <Accordion.Panel>
            <Stack gap={4}>
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
                size="xs"
                label="IGN Altimetría"
                checked={showIGNOverlay}
                onChange={(event) => onShowIGNOverlayChange(event.currentTarget.checked)}
              />
              {demEnabled && (
                <>
                  <Checkbox
                    size="xs"
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
      if (!showCanalesSection) continue;
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
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      );
      continue;
    }

    // ── Vector families: Hidrografía / Territorio / Pilar Verde / Análisis.
    const familyAll = layerItems.filter((item) => item.category === family.value);
    const familyVisible = filteredLayerItems.filter((item) => item.category === family.value);
    const isAnalisis = family.value === LAYER_CATEGORY.ANALISIS;
    // Análisis carries the IDECor attribution footer. Show it when not
    // searching so the credit stays visible even if the only Análisis layer
    // (puntos_conflicto) is absent.
    const showAttributions = isAnalisis && !isSearching && activeAttributions.length > 0;

    if (familyVisible.length === 0 && !showAttributions) continue;

    const familyActiveCount = familyAll.reduce(
      (count, item) => (vectorVisibility[item.id] ? count + 1 : count),
      0
    );

    accordionItems.push(
      <Accordion.Item key={family.value} value={family.value}>
        <Accordion.Control icon={<Icon size={16} />}>
          <FamilyControlLabel label={family.label} count={familyActiveCount} />
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap={4}>
            {familyVisible.map((item) => (
              <Checkbox
                key={item.id}
                size="xs"
                label={item.label}
                checked={!!vectorVisibility[item.id]}
                onChange={(event) => onLayerVisibilityChange(item.id, event.currentTarget.checked)}
              />
            ))}
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
          <TextInput
            size="xs"
            aria-label="Buscar capa"
            placeholder="Buscar capa…"
            leftSection={<IconSearch size={14} />}
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            rightSection={
              isSearching ? (
                <CloseButton
                  size="sm"
                  aria-label="Limpiar búsqueda"
                  onClick={() => setQuery('')}
                />
              ) : null
            }
          />
          {accordionItems.length > 0 ? (
            <Accordion
              multiple
              chevronPosition="right"
              defaultValue={LAYER_FAMILIES.map((family) => family.value)}
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
        </Stack>
      </Paper>
    </Box>
  );
}
