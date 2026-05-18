import {
  Box,
  Checkbox,
  Divider,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Text,
} from '@mantine/core';
import type { ReactNode } from 'react';
import { memo, useCallback, useEffect, useMemo } from 'react';
import { CollapsibleSection } from '../ui/CollapsibleSection';
import { getActiveAttributions } from './layerAttributions';

interface LayerItem {
  id: string;
  label: string;
}

/**
 * Canal entry — either a single canal (`leaf`) or a group of tramos that
 * share a `tramo_folder` (`group`). Groups render as a CollapsibleSection
 * with a master checkbox that toggles every child at once.
 */
export type CanalToggleEntry =
  | { kind: 'leaf'; id: string; label: string }
  | { kind: 'group'; folder: string; label: string; children: LayerItem[] };

interface SelectItem {
  value: string;
  label: string;
}

interface LayerControlsPanelProps {
  /**
   * Selector "Capa base" + slot `viewModePanel`. When BOTH are omitted
   * (typical when the parent renders a separate `MapBaseSelectorPanel`
   * above the map), the first Paper is suppressed.
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
   * propuestos array), the "Canales" CollapsibleSection renders AFTER the
   * "Capas" section. Leaving both arrays unset keeps the panel identical to
   * its pre-Pilar-Azul behavior for tests/pages that don't care.
   */
  readonly canalesRelevadosItems?: readonly CanalToggleEntry[];
  readonly canalesPropuestosItems?: readonly CanalToggleEntry[];
}

function collectChildIds(entries: readonly CanalToggleEntry[] | undefined): string[] {
  const ids: string[] = [];
  if (!entries) return ids;
  for (const e of entries) {
    if (e.kind === 'leaf') ids.push(e.id);
    else for (const c of e.children) ids.push(c.id);
  }
  return ids;
}

function computeBulkState(
  entries: readonly CanalToggleEntry[] | undefined,
  vectorVisibility: Record<string, boolean>
): { childIds: string[]; allOn: boolean; indeterminate: boolean } {
  const childIds = collectChildIds(entries);
  if (childIds.length === 0) return { childIds, allOn: false, indeterminate: false };
  const on = childIds.reduce((n, id) => n + (vectorVisibility[id] ? 1 : 0), 0);
  const allOn = on === childIds.length;
  const allOff = on === 0;
  return { childIds, allOn, indeterminate: !allOn && !allOff };
}

function CanalLeafRow({
  id,
  label,
  vectorVisibility,
  onLayerVisibilityChange,
  onChildActivated,
}: {
  id: string;
  label: string;
  vectorVisibility: Record<string, boolean>;
  onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  /** Called when user activates this child — used to auto-flip the master ON. */
  onChildActivated?: () => void;
}) {
  return (
    <div data-testid={`canal-toggle-${id}`}>
      <Checkbox
        size="xs"
        label={label}
        checked={!!vectorVisibility[id]}
        onChange={(event) => {
          const next = event.currentTarget.checked;
          onLayerVisibilityChange(id, next);
          if (next) onChildActivated?.();
        }}
      />
    </div>
  );
}

function CanalGroupRow({
  folder,
  label,
  tramos,
  vectorVisibility,
  onLayerVisibilityChange,
  onChildActivated,
}: {
  folder: string;
  label: string;
  tramos: { id: string; label: string }[];
  vectorVisibility: Record<string, boolean>;
  onLayerVisibilityChange: (layerId: string, visible: boolean) => void;
  onChildActivated?: () => void;
}) {
  const visibleCount = tramos.reduce(
    (n, c) => n + (vectorVisibility[c.id] ? 1 : 0),
    0
  );
  const allOn = visibleCount === tramos.length;
  const allOff = visibleCount === 0;
  const indeterminate = !allOn && !allOff;
  const title = `${label} (${tramos.length} tramos)`;
  return (
    <div data-testid={`canal-group-${folder}`}>
      <CollapsibleSection
        title={title}
        defaultOpen={false}
        titleSize="xs"
        titleWeight={500}
        rightAccessory={
          <Checkbox
            size="xs"
            aria-label={`Toggle ${label}`}
            checked={allOn}
            indeterminate={indeterminate}
            onClick={(event) => event.stopPropagation()}
            onChange={(event) => {
              const next = event.currentTarget.checked;
              for (const c of tramos) onLayerVisibilityChange(c.id, next);
              if (next) onChildActivated?.();
            }}
          />
        }
      >
        <Stack gap={2} pl="md">
          {tramos.map((c) => (
            <CanalLeafRow
              key={c.id}
              id={c.id}
              label={c.label}
              vectorVisibility={vectorVisibility}
              onLayerVisibilityChange={onLayerVisibilityChange}
              onChildActivated={onChildActivated}
            />
          ))}
        </Stack>
      </CollapsibleSection>
    </div>
  );
}

function renderCanalEntry(
  entry: CanalToggleEntry,
  vectorVisibility: Record<string, boolean>,
  onLayerVisibilityChange: (layerId: string, visible: boolean) => void,
  onChildActivated: () => void
) {
  if (entry.kind === 'leaf') {
    return (
      <CanalLeafRow
        key={entry.id}
        id={entry.id}
        label={entry.label}
        vectorVisibility={vectorVisibility}
        onLayerVisibilityChange={onLayerVisibilityChange}
        onChildActivated={onChildActivated}
      />
    );
  }
  return (
    <CanalGroupRow
      key={entry.folder}
      folder={entry.folder}
      label={entry.label}
      tramos={entry.children}
      vectorVisibility={vectorVisibility}
      onLayerVisibilityChange={onLayerVisibilityChange}
      onChildActivated={onChildActivated}
    />
  );
}

export const LayerControlsPanel = memo(function LayerControlsPanel({
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
  const showCanalesSection =
    (canalesRelevadosItems?.length ?? 0) > 0 || (canalesPropuestosItems?.length ?? 0) > 0;
  const relevadosMaster = !!vectorVisibility.canales_relevados;
  const propuestosMaster = !!vectorVisibility.canales_propuestos;
  const relevadosBulk = useMemo(
    () => computeBulkState(canalesRelevadosItems, vectorVisibility),
    [canalesRelevadosItems, vectorVisibility]
  );
  const propuestosBulk = useMemo(
    () => computeBulkState(canalesPropuestosItems, vectorVisibility),
    [canalesPropuestosItems, vectorVisibility]
  );
  const activeAttributions = useMemo(() => {
    const visibleSet = new Set<string>();
    for (const [id, visible] of Object.entries(vectorVisibility)) {
      if (visible) visibleSet.add(id);
    }
    return getActiveAttributions(visibleSet);
  }, [vectorVisibility]);
  const firstDemLayerId = demOptions[0]?.value ?? null;

  useEffect(() => {
    if (!showDemOverlay || !firstDemLayerId) return;
    const activeLayerExists = demOptions.some((option) => option.value === activeDemLayerId);
    if (!activeLayerExists) {
      onActiveDemLayerIdChange(firstDemLayerId);
    }
  }, [activeDemLayerId, demOptions, firstDemLayerId, onActiveDemLayerIdChange, showDemOverlay]);

  const handleDemOverlayChange = useCallback(
    (visible: boolean) => {
      if (visible && !activeDemLayerId && firstDemLayerId) {
        onActiveDemLayerIdChange(firstDemLayerId);
      }
      onShowDemOverlayChange(visible);
    },
    [activeDemLayerId, firstDemLayerId, onActiveDemLayerIdChange, onShowDemOverlayChange]
  );

  return (
    // Bounded outer scroll container: when many layer toggles, DEM options
    // and attributions are active, the stack used to grow past the viewport
    // and collide with the bottom-left `LeyendaPanel`. We cap the whole
    // top-left stack at `calc(100vh - 180px)` (≈ leaves room for bottom-left
    // legend + padding) and let it scroll internally instead.
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
      {baseLayer !== undefined && onBaseLayerChange && (
        <Paper
          shadow="md"
          p="xs"
          radius="md"
          style={{
            background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
            backdropFilter: 'blur(6px)',
          }}
        >
          <Stack gap={4}>
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
          </Stack>
        </Paper>
      )}

      {viewModePanel}

      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{
          background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
          backdropFilter: 'blur(6px)',
        }}
      >
        <CollapsibleSection
          title="Capas"
          testId="layer-controls-capas"
          titleSize="xs"
          titleWeight={600}
        >
          <Stack gap={4}>
            {layerItems.map(({ id, label }) => (
              <Checkbox
                key={id}
                size="xs"
                label={label}
                checked={!!vectorVisibility[id]}
                onChange={(event) => onLayerVisibilityChange(id, event.currentTarget.checked)}
              />
            ))}
            <Divider my={4} />
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
            {activeAttributions.length > 0 && (
              <>
                <Divider my={4} />
                {activeAttributions.map((text) => (
                  <Text key={text} size="xs" c="dimmed">
                    {text}
                  </Text>
                ))}
              </>
            )}
          </Stack>
        </CollapsibleSection>
      </Paper>

      {showCanalesSection && (
        <Paper
          shadow="md"
          p="xs"
          radius="md"
          style={{
            background: 'light-dark(rgba(255,255,255,0.94), rgba(36,36,36,0.94))',
            backdropFilter: 'blur(6px)',
          }}
        >
          <CollapsibleSection
            title="Canales"
            testId="layer-controls-canales"
            titleSize="xs"
            titleWeight={600}
          >
            <Stack gap={6}>
              {(canalesRelevadosItems?.length ?? 0) > 0 && (
                <Stack gap={4}>
                  <Checkbox
                    size="xs"
                    label={relevadosBulk.allOn ? 'Apagar todos los relevados' : 'Encender todos los relevados'}
                    checked={relevadosBulk.allOn}
                    indeterminate={relevadosBulk.indeterminate}
                    onChange={(event) => {
                      const next = event.currentTarget.checked;
                      // Bulk: set every child + keep the master gate ON so they render.
                      onLayerVisibilityChange('canales_relevados', next);
                      for (const childId of relevadosBulk.childIds) {
                        onLayerVisibilityChange(childId, next);
                      }
                    }}
                  />
                  <Stack gap={2} pl="md">
                    {canalesRelevadosItems?.map((entry) =>
                      renderCanalEntry(
                        entry,
                        vectorVisibility,
                        onLayerVisibilityChange,
                        () => {
                          if (!relevadosMaster)
                            onLayerVisibilityChange('canales_relevados', true);
                        }
                      )
                    )}
                  </Stack>
                </Stack>
              )}

              {(canalesPropuestosItems?.length ?? 0) > 0 && (
                <Stack gap={4}>
                  <Checkbox
                    size="xs"
                    label={propuestosBulk.allOn ? 'Apagar todos los propuestos' : 'Encender todos los propuestos'}
                    checked={propuestosBulk.allOn}
                    indeterminate={propuestosBulk.indeterminate}
                    onChange={(event) => {
                      const next = event.currentTarget.checked;
                      onLayerVisibilityChange('canales_propuestos', next);
                      for (const childId of propuestosBulk.childIds) {
                        onLayerVisibilityChange(childId, next);
                      }
                    }}
                  />
                  <Stack gap={2} pl="md">
                    {canalesPropuestosItems?.map((entry) =>
                      renderCanalEntry(
                        entry,
                        vectorVisibility,
                        onLayerVisibilityChange,
                        () => {
                          if (!propuestosMaster)
                            onLayerVisibilityChange('canales_propuestos', true);
                        }
                      )
                    )}
                  </Stack>
                  {/*
                    The propuestos etapas filter (Alta → Largo plazo) lives in
                    `LeyendaPanel` as interactive checkboxes — single source of
                    truth for both swatch colors AND toggle controls.
                  */}
                </Stack>
              )}
            </Stack>
          </CollapsibleSection>
        </Paper>
      )}
    </Box>
  );
});
