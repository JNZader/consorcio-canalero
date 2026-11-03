import { Button, Checkbox, SegmentedControl, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';

import { useMapWorkspaceStore } from '../../stores/mapWorkspaceStore';
import { MapBaseSelectorPanel } from './MapBaseSelectorPanel';
import { useMapPageView } from './mapPageViewContext';

interface MapVistaSectionProps {
  readonly baseLayer?: 'osm' | 'satellite';
  readonly onBaseLayerChange?: (value: 'osm' | 'satellite') => void;
  readonly viewModePanel?: ReactNode;
  /** The cursor readout is a 2D canvas overlay. The 3D shell omits the toggle. */
  readonly showCursorToggle?: boolean;
}

/**
 * Vista controls that used to sit in rows above the canvas: 2D/3D, capa base
 * and the satellite view mode. They live at the top of the layers panel so the
 * map can use that height.
 */
export function MapVistaSection({
  baseLayer,
  onBaseLayerChange,
  viewModePanel,
  showCursorToggle = true,
}: MapVistaSectionProps) {
  const pageView = useMapPageView();
  const showCursorReadout = useMapWorkspaceStore((state) => state.showCursorReadout);
  const setShowCursorReadout = useMapWorkspaceStore((state) => state.setShowCursorReadout);
  const showBase = baseLayer !== undefined && onBaseLayerChange !== undefined;

  return (
    <Stack gap={6} data-testid="map-vista-section">
      <Text size="xs" fw={600}>
        Vista
      </Text>
      {pageView ? (
        <>
          <SegmentedControl
            size="xs"
            fullWidth
            aria-label="Vista del mapa"
            value={pageView.mode}
            onChange={(value) => pageView.setMode(value as '2d' | '3d')}
            data={[
              { value: '2d', label: '2D' },
              { value: '3d', label: '3D', disabled: !pageView.terrainReady },
            ]}
          />
          {pageView.terrainHint ? (
            <Text size="xs" c="dimmed" data-testid="map-3d-status">
              {pageView.terrainHint}
            </Text>
          ) : null}
          {pageView.terrainStatus === 'error' && pageView.onRetryTerrain ? (
            <Button size="xs" variant="light" onClick={pageView.onRetryTerrain}>
              Reintentar
            </Button>
          ) : null}
        </>
      ) : null}
      {showBase ? (
        <MapBaseSelectorPanel
          plain
          baseLayer={baseLayer}
          onBaseLayerChange={onBaseLayerChange}
          viewModePanel={viewModePanel}
        />
      ) : null}
      {showCursorToggle ? (
        <Checkbox
          size="xs"
          label="Coordenadas del cursor"
          checked={showCursorReadout}
          onChange={(event) => setShowCursorReadout(event.currentTarget.checked)}
          data-testid="map-cursor-toggle"
        />
      ) : null}
    </Stack>
  );
}
