import {
  Box,
  Checkbox,
  Divider,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import type { ReactNode } from 'react';
import { memo, useMemo } from 'react';
import type { Etapa } from '../../types/canales';
import { CollapsibleSection } from '../ui/CollapsibleSection';
import { PropuestasEtapasFilter } from './PropuestasEtapasFilter';
import { getActiveAttributions } from './layerAttributions';

interface LayerItem {
  id: string;
  label: string;
}

interface SelectItem {
  value: string;
  label: string;
}

interface LayerControlsPanelProps {
  readonly baseLayer: 'osm' | 'satellite';
  readonly onBaseLayerChange: (value: 'osm' | 'satellite') => void;
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
  readonly canalesRelevadosItems?: readonly LayerItem[];
  readonly canalesPropuestosItems?: readonly LayerItem[];
  /**
   * 5-key record sourced from `mapLayerSyncStore.propuestasEtapasVisibility`.
   * Required only when the Canales section is active AND the propuestos
   * master is ON — the filter subsection reads it directly.
   */
  readonly propuestasEtapasVisibility?: Readonly<Record<Etapa, boolean>>;
  /**
   * Parent-owned setter for a single etapa. Typically delegates to
   * `mapLayerSyncStore.setEtapaVisible`.
   */
  readonly onSetEtapaVisible?: (etapa: Etapa, visible: boolean) => void;
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
  propuestasEtapasVisibility,
  onSetEtapaVisible,
}: LayerControlsPanelProps) {
  const showCanalesSection =
    (canalesRelevadosItems?.length ?? 0) > 0 || (canalesPropuestosItems?.length ?? 0) > 0;
  const relevadosMaster = !!vectorVisibility.canales_relevados;
  const propuestosMaster = !!vectorVisibility.canales_propuestos;
  const activeAttributions = useMemo(() => {
    const visibleSet = new Set<string>();
    for (const [id, visible] of Object.entries(vectorVisibility)) {
      if (visible) visibleSet.add(id);
    }
    return getActiveAttributions(visibleSet);
  }, [vectorVisibility]);

  return (
    // Bounded outer scroll container: when many layer toggles, DEM options
    // and attributions are active, the stack used to grow past the viewport
    // and collide with the bottom-left `LeyendaPanel`. We cap the whole
    // top-left stack at `calc(100vh - 180px)` (≈ leaves room for bottom-left
    // legend + padding) and let it scroll internally instead.
    <Box
      data-testid="layer-controls-panel-scroll"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        maxHeight: 'calc(100vh - 180px)',
        overflowY: 'auto',
        overflowX: 'hidden',
      }}
    >
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
            value={baseLayer}
            onChange={(value) => onBaseLayerChange(value as 'osm' | 'satellite')}
            data={[
              { value: 'osm', label: 'OSM' },
              { value: 'satellite', label: 'Satélite' },
            ]}
          />
        </Stack>
      </Paper>

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
                  onChange={(event) => onShowDemOverlayChange(event.currentTarget.checked)}
                />
                {showDemOverlay && (
                  <Select
                    size="xs"
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
                    label="Canales relevados"
                    checked={relevadosMaster}
                    onChange={(event) =>
                      onLayerVisibilityChange('canales_relevados', event.currentTarget.checked)
                    }
                  />
                  <Stack gap={2} pl="md">
                    {canalesRelevadosItems?.map(({ id, label }) => {
                      const disabledRow = !relevadosMaster;
                      const tooltipLabel = "Activá 'Canales relevados' para usar esta opción";
                      return (
                        <Tooltip key={id} label={tooltipLabel} disabled={!disabledRow} withinPortal>
                          <div
                            data-testid={`canal-toggle-${id}`}
                            data-tooltip-label={disabledRow ? tooltipLabel : undefined}
                          >
                            <Checkbox
                              size="xs"
                              label={label}
                              checked={!!vectorVisibility[id]}
                              disabled={disabledRow}
                              onChange={(event) =>
                                onLayerVisibilityChange(id, event.currentTarget.checked)
                              }
                            />
                          </div>
                        </Tooltip>
                      );
                    })}
                  </Stack>
                </Stack>
              )}

              {(canalesPropuestosItems?.length ?? 0) > 0 && (
                <Stack gap={4}>
                  <Checkbox
                    size="xs"
                    label="Canales propuestos"
                    checked={propuestosMaster}
                    onChange={(event) =>
                      onLayerVisibilityChange('canales_propuestos', event.currentTarget.checked)
                    }
                  />
                  <Stack gap={2} pl="md">
                    {canalesPropuestosItems?.map(({ id, label }) => {
                      const disabledRow = !propuestosMaster;
                      const tooltipLabel = "Activá 'Canales propuestos' para usar esta opción";
                      return (
                        <Tooltip key={id} label={tooltipLabel} disabled={!disabledRow} withinPortal>
                          <div
                            data-testid={`canal-toggle-${id}`}
                            data-tooltip-label={disabledRow ? tooltipLabel : undefined}
                          >
                            <Checkbox
                              size="xs"
                              label={label}
                              checked={!!vectorVisibility[id]}
                              disabled={disabledRow}
                              onChange={(event) =>
                                onLayerVisibilityChange(id, event.currentTarget.checked)
                              }
                            />
                          </div>
                        </Tooltip>
                      );
                    })}
                  </Stack>
                  {/*
                    PropuestasEtapasFilter UNMOUNTS when the master is OFF — spec
                    requirement "Section unmounts when master toggled off". When
                    the caller did not supply etapas state (e.g. test fixtures
                    without canales), we also bail to keep the render hole clean.
                  */}
                  {propuestasEtapasVisibility && onSetEtapaVisible && (
                    <PropuestasEtapasFilter
                      masterOn={propuestosMaster}
                      propuestasEtapasVisibility={propuestasEtapasVisibility}
                      onSetEtapaVisible={onSetEtapaVisible}
                    />
                  )}
                </Stack>
              )}
            </Stack>
          </CollapsibleSection>
        </Paper>
      )}
    </Box>
  );
});
