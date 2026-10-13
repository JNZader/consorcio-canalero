import {
  Accordion,
  ActionIcon,
  Box,
  Button,
  Checkbox,
  Divider,
  Group,
  Loader,
  Radio,
  SegmentedControl,
  Select,
  Slider,
  Stack,
  Switch,
  Text,
  Tooltip,
} from '@mantine/core';
import type { ComponentType } from 'react';
import { isValidElement, type ReactNode } from 'react';
import { CanalesLayerSection } from '../shared/CanalesLayerSection';
import type { CanalToggleEntry } from '../shared/canalesGrouping';
import {
  IconChartBar,
  IconDroplet,
  IconMap,
  IconMapPin,
  IconPlant,
  IconRefresh,
  IconRoute,
  IconSettings,
} from '../ui/icons';
import { mergeRasterSearchOptions } from './knownRasterCatalog';
import type { HazardLayerControl, LayerFineControl } from './LayerControlsPanel';
import {
  FamilyControlLabel,
  LayerHealthErrorRow,
  LayerOpacityControl,
  LayerProvenanceLine,
  resolveFamilyHealthRow,
} from './layerControlWidgets';
import type { LayerHealth, LayerHealthEntry } from './layerHealth';
import { LAYER_ZOOM_IN_HINT, layerBelowMinZoom } from './layerMinZoom';
import { RENDERABLE_UI_LAYER_IDS } from './layerRenderRegistry';
import { LAYER_CATEGORY, type LayerCategory, normalizeSearchText } from './map2dDerived';
import { MAP2D_HILLSHADE_Z_FACTOR } from './mapRasterOverlayHelpers';

const RENDERABLE_UI_LAYER_ID_SET = new Set<string>(RENDERABLE_UI_LAYER_IDS);

type LayerFamilyIcon = ComponentType<{ size?: number }>;

export const LAYER_FAMILIES: ReadonlyArray<{
  value: LayerCategory;
  label: string;
  Icon: LayerFamilyIcon;
}> = [
  { value: LAYER_CATEGORY.BASE, label: 'Base', Icon: IconMap },
  { value: LAYER_CATEGORY.HIDROGRAFIA, label: 'Hidrografía', Icon: IconDroplet },
  { value: LAYER_CATEGORY.CANALES, label: 'Canales', Icon: IconRoute },
  { value: LAYER_CATEGORY.TERRITORIO, label: 'Territorio', Icon: IconMapPin },
  { value: LAYER_CATEGORY.PILAR_VERDE, label: 'Pilar Verde', Icon: IconPlant },
  { value: LAYER_CATEGORY.ANALISIS, label: 'Análisis', Icon: IconChartBar },
];

const BASE_SEARCH_LABELS = [
  'base',
  'capa base',
  'osm',
  'satélite',
  'ign altimetría',
  'visor de riesgos',
  'zona consorcio',
  'ypf',
].map(normalizeSearchText);

const AJUSTES_SEARCH_LABELS = ['ajustes', 'etiquetas', 'grosor', 'líneas'].map(normalizeSearchText);

export interface LayerAccordionInput {
  readonly is3d: boolean;
  readonly isSearching: boolean;
  readonly normalizedQuery: string;
  readonly familyActiveCounts: Record<LayerCategory, number>;
  readonly demEnabled: boolean;
  readonly showDemOverlay: boolean;
  readonly onShowDemOverlayChange: (visible: boolean) => void;
  readonly baseLayer?: 'osm' | 'satellite';
  readonly onBaseLayerChange?: (value: 'osm' | 'satellite') => void;
  readonly showIGNOverlay: boolean;
  readonly onShowIGNOverlayChange: (visible: boolean) => void;
  readonly hillshadeAvailable: boolean;
  readonly onShowHillshadeChange?: (visible: boolean) => void;
  readonly showHillshade: boolean;
  readonly hazardLayerControl?: HazardLayerControl;
  readonly layerHealth?: LayerHealth;
  readonly showCanalesSection: boolean;
  readonly canalesHealth: LayerHealthEntry | null;
  readonly showCanalesDuringSearch: boolean;
  readonly canalesActiveCount: number;
  readonly relevadosToRender: readonly CanalToggleEntry[] | undefined;
  readonly relevadosMaster: boolean;
  readonly vectorVisibility: Record<string, boolean>;
  readonly onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  readonly propuestosToRender: readonly CanalToggleEntry[] | undefined;
  readonly propuestosMaster: boolean;
  readonly onFocusCanal?: (id: string) => void;
  readonly canalesProvenance: string | null;
  readonly filteredLayerItems: ReadonlyArray<{
    id: string;
    label: string;
    category: LayerCategory;
  }>;
  readonly activeAttributions: readonly string[];
  readonly pilarVerdeLayersLoading: boolean;
  readonly pilarVerdeLayersError: string | null;
  readonly layerProvenance?: Partial<Record<LayerCategory, string>>;
  readonly layerFineControl: LayerFineControl;
  readonly effectiveZoom: number;
  readonly unsupportedSet: ReadonlySet<string>;
  readonly demOptions: ReadonlyArray<{ value: string; label: string; tipo?: string }>;
  readonly demLoadError: string | null;
  readonly rasterSearchMatches: ReadonlyArray<{
    value: string;
    label: string;
    available?: boolean;
  }>;
  readonly query: string;
  readonly rasterLoading: boolean;
  readonly activeDemLayerId: string | null;
  readonly handleDemOverlayChange: (visible: boolean) => void;
  readonly handleRasterSearchSelect: (value: string) => void;
  readonly onRetryDem?: () => void;
  readonly rasterCompareId: string | null;
  readonly onRasterCompare?: (layerId: string | null) => void;
}

/** Arma los ítems del acordeón de capas. El panel solo los monta. */
export function buildLayerAccordionItems(input: LayerAccordionInput): ReactNode[] {
  const {
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
  } = input;

  const accordionItems: ReactNode[] = [];

  for (const family of LAYER_FAMILIES) {
    const Icon = family.Icon;

    // ── Base: structural controls (capa base / IGN / DEM), NOT in layerItems.
    if (family.value === LAYER_CATEGORY.BASE) {
      if (is3d) {
        if (isSearching && !BASE_SEARCH_LABELS.some((label) => label.includes(normalizedQuery))) {
          continue;
        }
        const baseActiveCount = familyActiveCounts[LAYER_CATEGORY.BASE];
        accordionItems.push(
          <Accordion.Item
            key={family.value}
            value={family.value}
            data-testid="layer-controls-capas"
          >
            <Accordion.Control icon={<Icon size={16} />}>
              <FamilyControlLabel label={family.label} count={baseActiveCount} />
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap={4}>
                <Text size="xs" c="dimmed">
                  Zona Consorcio es el terreno 3D; no hay perímetro extra.
                </Text>
                <Text size="xs" c="dimmed">
                  La base satelital es Esri World Imagery.
                </Text>
                <Checkbox label="Zona Consorcio" checked disabled />
                {demEnabled ? (
                  <Checkbox
                    label="Capa raster 3D"
                    checked={showDemOverlay}
                    onChange={(event) => onShowDemOverlayChange(event.currentTarget.checked)}
                  />
                ) : null}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        );
        continue;
      }
      // FF2: Base stays searchable by its control labels (Capa base / IGN /
      // Capa DEM / OSM / Satélite).
      if (isSearching && !BASE_SEARCH_LABELS.some((label) => label.includes(normalizedQuery))) {
        continue;
      }
      const baseActiveCount =
        familyActiveCounts[LAYER_CATEGORY.BASE] + (hazardLayerControl?.activeLayerCount ?? 0);
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
              {hillshadeAvailable && onShowHillshadeChange ? (
                <>
                  <Checkbox
                    label="Relieve sombreado"
                    checked={showHillshade}
                    onChange={(event) => onShowHillshadeChange(event.currentTarget.checked)}
                  />
                  {showHillshade ? (
                    <Text size="xs" c="dimmed">
                      Exagerado ×{MAP2D_HILLSHADE_Z_FACTOR} para que se note en terreno llano
                    </Text>
                  ) : null}
                </>
              ) : null}
              {hazardLayerControl?.visible && (
                <Checkbox
                  label="Visor de riesgos"
                  checked={hazardLayerControl.active}
                  onChange={(event) =>
                    hazardLayerControl.onActiveChange(event.currentTarget.checked)
                  }
                />
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
                variant="explorer"
                onFocusCanal={onFocusCanal}
              />
              <CanalesLayerSection
                side="propuestos"
                entries={propuestosToRender}
                masterFlag="canales_propuestos"
                masterOn={propuestosMaster}
                vectorVisibility={vectorVisibility}
                onLayerVisibilityChange={onLayerVisibilityChange}
                variant="explorer"
                onFocusCanal={onFocusCanal}
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
      <Accordion.Item
        key={family.value}
        value={family.value}
        data-testid={`layer-family-${family.value}`}
      >
        <Accordion.Control
          icon={<Icon size={16} />}
          data-testid={`layer-family-${family.value}-control`}
        >
          <Group gap={6} wrap="nowrap" style={{ flex: 1 }}>
            <FamilyControlLabel label={family.label} count={familyActiveCount} />
            {showPilarVerdeSpinner && <Loader size={12} data-testid="pilar-verde-layers-loading" />}
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap={4}>
            {familyVisible.length > 0 && (
              <Checkbox
                aria-label={`Todas las capas de ${family.label}`}
                label="Todas"
                checked={familyActiveCount > 0 && familyActiveCount === familyVisible.length}
                indeterminate={familyActiveCount > 0 && familyActiveCount < familyVisible.length}
                onChange={(event) => {
                  const next = event.currentTarget.checked;
                  for (const item of familyVisible) {
                    if (unsupportedSet.has(item.id)) continue;
                    onLayerVisibilityChange(item.id, next);
                  }
                }}
              />
            )}
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
              const unsupported = unsupportedSet.has(item.id);
              const checkbox = (
                <Checkbox
                  label={item.label}
                  checked={unsupported ? false : isOn}
                  disabled={unsupported}
                  onChange={(event) =>
                    onLayerVisibilityChange(item.id, event.currentTarget.checked)
                  }
                />
              );
              return (
                <Box key={item.id}>
                  {unsupported ? (
                    <Tooltip
                      label="No disponible en 3D"
                      withArrow
                      events={{ hover: true, focus: true, touch: true }}
                    >
                      <Box
                        tabIndex={0}
                        role="group"
                        aria-label={`${item.label}: no disponible en 3D`}
                      >
                        {checkbox}
                      </Box>
                    </Tooltip>
                  ) : (
                    checkbox
                  )}
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
                  {layerBelowMinZoom(item.id, effectiveZoom) && (
                    <Text size="xs" c="dimmed">
                      {LAYER_ZOOM_IN_HINT}
                    </Text>
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

  const rasterQueryHit =
    !isSearching ||
    rasterSearchMatches.length > 0 ||
    normalizeSearchText('análisis raster').includes(normalizedQuery) ||
    normalizedQuery.includes('dem');
  if (!is3d && rasterQueryHit && (demEnabled || demLoadError || rasterSearchMatches.length > 0)) {
    const rasterOptions =
      isSearching && rasterSearchMatches.length > 0
        ? rasterSearchMatches
        : demOptions.length > 0
          ? demOptions.map((option) => ({ ...option, available: true }))
          : mergeRasterSearchOptions(demOptions, query);
    accordionItems.push(
      <Accordion.Item key="raster" value="raster" data-testid="layer-controls-raster">
        <Accordion.Control icon={<IconChartBar size={16} />}>
          <FamilyControlLabel label="Análisis raster" count={showDemOverlay ? 1 : 0} />
        </Accordion.Control>
        <Accordion.Panel>
          <Switch
            size="sm"
            label={rasterLoading ? 'Mostrar raster (cargando…)' : 'Mostrar raster'}
            checked={showDemOverlay}
            onChange={(event) => handleDemOverlayChange(event.currentTarget.checked)}
            mb={8}
            disabled={!demEnabled}
          />
          {demLoadError ? (
            <Group gap={6} mb={8}>
              <Text size="xs" c="red">
                {demLoadError}
              </Text>
              {onRetryDem ? (
                <Button size="xs" variant="light" onClick={() => onRetryDem()}>
                  Reintentar
                </Button>
              ) : null}
            </Group>
          ) : null}
          <Radio.Group
            aria-label="Tipo de capa raster"
            value={showDemOverlay ? (activeDemLayerId ?? '') : ''}
            onChange={(value) => {
              if (!value) {
                onShowDemOverlayChange(false);
                return;
              }
              handleRasterSearchSelect(value);
            }}
          >
            <Stack gap={4}>
              {rasterOptions.map((option) => {
                const available = 'available' in option ? option.available !== false : true;
                return (
                  <Radio
                    key={option.value}
                    value={option.value}
                    disabled={!available}
                    label={available ? option.label : `${option.label} (no disponible)`}
                    data-testid={`raster-search-option-${option.value}`}
                  />
                );
              })}
              <Text size="xs" c="dimmed">
                Una capa raster por vez.
              </Text>
              {showDemOverlay && onRasterCompare && demOptions.length > 1 && (
                <Select
                  size="xs"
                  clearable
                  aria-label="Comparar con"
                  placeholder="Comparar con…"
                  data-testid="raster-compare-select"
                  value={rasterCompareId}
                  data={demOptions.filter((option) => option.value !== activeDemLayerId)}
                  onChange={onRasterCompare}
                />
              )}
            </Stack>
          </Radio.Group>
        </Accordion.Panel>
      </Accordion.Item>
    );
    const rasterIdx = accordionItems.findIndex(
      (node) => isValidElement(node) && node.key === 'raster'
    );
    const hidroIdx = accordionItems.findIndex(
      (node) => isValidElement(node) && node.key === LAYER_CATEGORY.HIDROGRAFIA
    );
    if (rasterIdx >= 0 && hidroIdx >= 0 && rasterIdx !== hidroIdx + 1) {
      const [rasterNode] = accordionItems.splice(rasterIdx, 1);
      const insertAt =
        accordionItems.findIndex(
          (node) => isValidElement(node) && node.key === LAYER_CATEGORY.HIDROGRAFIA
        ) + 1;
      accordionItems.splice(insertAt, 0, rasterNode);
    }
  }

  const showAjustes =
    !isSearching || AJUSTES_SEARCH_LABELS.some((label) => label.includes(normalizedQuery));
  if (!is3d && showAjustes) {
    accordionItems.push(
      <Accordion.Item key="ajustes" value="ajustes" data-testid="layer-controls-ajustes">
        <Accordion.Control icon={<IconSettings size={16} />}>
          <FamilyControlLabel label="Ajustes" count={0} />
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap={4}>
            <Text size="xs" fw={600} c="dimmed">
              Tamaño de etiquetas
            </Text>
            <Group gap={6} wrap="nowrap" data-testid="map-label-size">
              <Slider
                style={{ flex: 1 }}
                min={75}
                max={250}
                step={5}
                value={Math.round(layerFineControl.labelSizeScale * 100)}
                onChange={(value) => layerFineControl.onLabelSizeScaleChange(value / 100)}
                label={(value) => `${value}%`}
                thumbLabel="Tamaño de etiquetas del mapa"
              />
              <Text size="xs" c="dimmed" w={36} ta="right">
                {Math.round(layerFineControl.labelSizeScale * 100)}%
              </Text>
              <Tooltip label="Restablecer tamaño" withArrow>
                <ActionIcon
                  variant="subtle"
                  size="sm"
                  color="gray"
                  aria-label="Restablecer tamaño de etiquetas"
                  data-testid="map-label-size-reset"
                  onClick={() => layerFineControl.onLabelSizeScaleChange(1)}
                >
                  <IconRefresh size={12} />
                </ActionIcon>
              </Tooltip>
            </Group>
            <Text size="xs" fw={600} c="dimmed">
              Grosor de líneas
            </Text>
            <Group gap={6} wrap="nowrap" data-testid="map-line-width">
              <Slider
                style={{ flex: 1 }}
                min={75}
                max={250}
                step={5}
                value={Math.round(layerFineControl.lineWidthScale * 100)}
                onChange={(value) => layerFineControl.onLineWidthScaleChange(value / 100)}
                label={(value) => `${value}%`}
                thumbLabel="Grosor de líneas del mapa"
              />
              <Text size="xs" c="dimmed" w={36} ta="right">
                {Math.round(layerFineControl.lineWidthScale * 100)}%
              </Text>
              <Tooltip label="Restablecer grosor" withArrow>
                <ActionIcon
                  variant="subtle"
                  size="sm"
                  color="gray"
                  aria-label="Restablecer grosor de líneas"
                  data-testid="map-line-width-reset"
                  onClick={() => layerFineControl.onLineWidthScaleChange(1)}
                >
                  <IconRefresh size={12} />
                </ActionIcon>
              </Tooltip>
            </Group>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    );
  }

  return accordionItems;
}
