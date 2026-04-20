import { Box, Checkbox, Divider, Paper, SegmentedControl, Select, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { memo, useMemo } from 'react';
import { CollapsibleSection } from '../ui/CollapsibleSection';
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
}: LayerControlsPanelProps) {
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
    </Box>
  );
});
