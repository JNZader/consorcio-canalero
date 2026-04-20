import { Checkbox, Divider, Group, Paper, SegmentedControl, Select, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { memo, useMemo } from 'react';
import { getActiveAttributions } from './layerAttributions';
import { PILAR_VERDE_COLORS } from './pilarVerdeLayers';

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
    <>
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
          maxHeight: '60vh',
          overflowY: 'auto',
        }}
      >
        <Text size="xs" fw={600} c="dimmed" mb={6}>
          Capas
        </Text>
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
          {vectorVisibility.pilar_verde_bpa_historico && (
            <>
              <Divider my={4} />
              <Text size="xs" c="dimmed" fw={500}>
                Años en BPA:
              </Text>
              <Group gap="xs" wrap="nowrap" data-testid="bpa-historico-legend">
                {[
                  { label: '1', color: PILAR_VERDE_COLORS.bpaHistoricoStop1 },
                  { label: '3', color: PILAR_VERDE_COLORS.bpaHistoricoStop3 },
                  { label: '5', color: PILAR_VERDE_COLORS.bpaHistoricoStop5 },
                  { label: '7', color: PILAR_VERDE_COLORS.bpaHistoricoStop7 },
                ].map((chip) => (
                  <Group key={chip.label} gap={4} wrap="nowrap">
                    <span
                      data-color={chip.color}
                      aria-label={`${chip.label} años`}
                      style={{
                        display: 'inline-block',
                        width: 12,
                        height: 12,
                        backgroundColor: chip.color,
                        border: '1px solid #166534',
                        borderRadius: 2,
                      }}
                    />
                    <Text size="xs">{chip.label}</Text>
                  </Group>
                ))}
              </Group>
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
      </Paper>
    </>
  );
});
