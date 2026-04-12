import { Box, Loader, Stack, Text } from '@mantine/core';
import { type MouseEventHandler, memo } from 'react';
import { IconGitCompare } from '../ui/icons';

interface MapViewportOverlayProps {
  readonly viewMode: string;
  readonly sliderPosition: number;
  readonly mapReady: boolean;
  readonly onSliderMouseDown: MouseEventHandler<HTMLDivElement>;
}

export const MapViewportOverlay = memo(function MapViewportOverlay({
  viewMode,
  sliderPosition,
  mapReady,
  onSliderMouseDown,
}: MapViewportOverlayProps) {
  return (
    <>
      {viewMode === 'comparison' && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: `${sliderPosition}%`,
            width: 3,
            height: '100%',
            background: 'rgba(255,255,255,0.9)',
            cursor: 'col-resize',
            zIndex: 15,
            transform: 'translateX(-50%)',
          }}
          onMouseDown={onSliderMouseDown}
          aria-label="Divisor de comparación"
          role="separator"
          aria-orientation="vertical"
          tabIndex={0}
        >
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
            background:
              'light-dark(var(--mantine-color-gray-1), var(--mantine-color-dark-7))',
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
