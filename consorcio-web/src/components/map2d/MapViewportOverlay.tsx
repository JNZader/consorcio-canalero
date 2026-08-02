import { Box, Loader, Stack, Text } from '@mantine/core';
import { type PointerEventHandler, memo } from 'react';
import { IconGitCompare } from '../ui/icons';

/** Interactive width of the comparison divider (map-fluidity T2, fix 3). The
 * visible bar stays 3px; the extra width is transparent padding so the target
 * clears the 24px minimum instead of asking for a 3px-precise touch. */
const SLIDER_HIT_AREA_PX = 24;
const SLIDER_BAR_PX = 3;

interface MapViewportOverlayProps {
  readonly viewMode: string;
  readonly sliderPosition: number;
  readonly mapReady: boolean;
  /**
   * Pointer-down on the comparison divider. POINTER, not mouse: the same
   * handler has to serve mouse, touch and pen (see `useComparisonSlider`).
   */
  readonly onSliderPointerDown: PointerEventHandler<HTMLDivElement>;
}

export const MapViewportOverlay = memo(function MapViewportOverlay({
  viewMode,
  sliderPosition,
  mapReady,
  onSliderPointerDown,
}: MapViewportOverlayProps) {
  return (
    <>
      {viewMode === 'comparison' && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: `${sliderPosition}%`,
            width: SLIDER_HIT_AREA_PX,
            height: '100%',
            background: 'transparent',
            cursor: 'col-resize',
            zIndex: 15,
            transform: 'translateX(-50%)',
            // Without this the browser claims the gesture for panning and
            // never delivers `pointermove` to the divider.
            touchAction: 'none',
          }}
          onPointerDown={onSliderPointerDown}
          aria-label="Divisor de comparación"
          role="separator"
          aria-orientation="vertical"
          tabIndex={0}
          data-testid="map-comparison-divider"
        >
          {/* The visible bar — unchanged 3px, centred in the wider hit area. */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: '50%',
              transform: 'translateX(-50%)',
              width: SLIDER_BAR_PX,
              height: '100%',
              background: 'rgba(255,255,255,0.9)',
              pointerEvents: 'none',
            }}
          />
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              width: 28,
              height: 28,
              borderRadius: '50%',
              background: 'white',
              border: '2px solid rgba(0,0,0,0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
            }}
          >
            <IconGitCompare size={14} color="gray" />
          </div>
        </div>
      )}

      {!mapReady && (
        <Box
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-7))',
            zIndex: 20,
          }}
        >
          <Stack align="center" gap="md">
            <Loader size="lg" color="institucional" type="dots" />
            <Text size="sm" c="dimmed" fw={500}>
              Cargando mapa interactivo...
            </Text>
          </Stack>
        </Box>
      )}
    </>
  );
});
