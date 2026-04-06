/**
 * Component for side-by-side satellite image comparison on the map.
 * Uses a slider to compare two satellite images.
 *
 * Split into two components:
 * - ComparisonLayers: Wires two raster tile layers into a MapLibre GL map.
 * - ComparisonSliderUI: Renders slider UI outside the map container.
 *
 * Uses per-tile clipping via CSS to handle map panning correctly.
 */

import { Badge, CloseButton, Group, Paper, Stack, Text } from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import type { ImageComparison } from '../hooks/useImageComparison';
import { IconArrowsHorizontal } from './ui/icons';

/**
 * Calculates days between two dates
 */
function daysBetween(date1: string, date2: string): number {
  const d1 = new Date(date1);
  const d2 = new Date(date2);
  const diffTime = Math.abs(d2.getTime() - d1.getTime());
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

interface ComparisonLayersProps {
  map: maplibregl.Map;
  comparison: ImageComparison;
  sliderPosition: number;
}

/**
 * Wires two raster tile layers into a MapLibre GL map for comparison.
 * Must receive the map instance directly (not inside a MapContainer).
 * Uses clip-path on the left layer container to implement the slider.
 */
export function ComparisonLayers({ map, comparison, sliderPosition }: ComparisonLayersProps) {
  const [layersReady, setLayersReady] = useState(false);
  const LEFT_SOURCE = 'comparison-left';
  const RIGHT_SOURCE = 'comparison-right';
  const LEFT_LAYER = 'comparison-left-layer';
  const RIGHT_LAYER = 'comparison-right-layer';

  // Add sources and layers to the MapLibre map
  useEffect(() => {
    const addLayers = () => {
      // Right source/layer (bottom)
      if (!map.getSource(RIGHT_SOURCE)) {
        map.addSource(RIGHT_SOURCE, {
          type: 'raster',
          tiles: [comparison.right.tile_url],
          tileSize: 256,
        });
      }
      if (!map.getLayer(RIGHT_LAYER)) {
        map.addLayer({
          id: RIGHT_LAYER,
          type: 'raster',
          source: RIGHT_SOURCE,
          paint: { 'raster-opacity': 1 },
        });
      }

      // Left source/layer (top, will be clipped)
      if (!map.getSource(LEFT_SOURCE)) {
        map.addSource(LEFT_SOURCE, {
          type: 'raster',
          tiles: [comparison.left.tile_url],
          tileSize: 256,
        });
      }
      if (!map.getLayer(LEFT_LAYER)) {
        map.addLayer({
          id: LEFT_LAYER,
          type: 'raster',
          source: LEFT_SOURCE,
          paint: { 'raster-opacity': 1 },
        });
      }

      setLayersReady(true);
    };

    if (map.isStyleLoaded()) {
      addLayers();
    } else {
      map.once('load', addLayers);
    }

    return () => {
      if (map.getLayer(LEFT_LAYER)) map.removeLayer(LEFT_LAYER);
      if (map.getLayer(RIGHT_LAYER)) map.removeLayer(RIGHT_LAYER);
      if (map.getSource(LEFT_SOURCE)) map.removeSource(LEFT_SOURCE);
      if (map.getSource(RIGHT_SOURCE)) map.removeSource(RIGHT_SOURCE);
      setLayersReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, comparison.left.tile_url, comparison.right.tile_url]);

  // Update clip-path on slider position change
  useEffect(() => {
    if (!layersReady) return;
    const canvas = map.getCanvas();
    if (!canvas) return;

    // The left layer canvas pane needs to be clipped at sliderPosition%
    // MapLibre renders to a single canvas; we clip via the container div approach
    const pct = `${sliderPosition}%`;
    canvas.style.clipPath = '';

    // Use the map's container to apply clip to the left-side layer by
    // temporarily using a canvas filter approach is complex in MapLibre.
    // The MapComparisonSlider in MapaMapLibre.tsx handles this via CSS
    // on the layer container. Here we expose a data attribute for that.
    canvas.parentElement?.setAttribute('data-comparison-pos', pct);
  }, [map, sliderPosition, layersReady]);

  return null;
}

interface ComparisonSliderUIProps {
  comparison: ImageComparison;
  sliderPosition: number;
  onSliderChange: (position: number) => void;
  onClear: () => void;
  containerRef: React.RefObject<HTMLElement | null>;
}

/**
 * Renders the slider UI for comparison.
 * Must be rendered OUTSIDE the map container, but inside a positioned container.
 */
export function ComparisonSliderUI({
  comparison,
  sliderPosition,
  onSliderChange,
  onClear,
  containerRef,
}: ComparisonSliderUIProps) {
  const isDragging = useRef(false);
  const sliderRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    isDragging.current = true;
  }, []);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    e.stopPropagation();
    isDragging.current = true;
  }, []);

  const updatePosition = useCallback(
    (clientX: number) => {
      const container = containerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const x = clientX - rect.left;
      const percentage = Math.max(5, Math.min(95, (x / rect.width) * 100));
      onSliderChange(percentage);
    },
    [containerRef, onSliderChange]
  );

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      e.preventDefault();
      updatePosition(e.clientX);
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (!isDragging.current) return;
      if (e.touches.length > 0) {
        updatePosition(e.touches[0].clientX);
      }
    };

    const handleEnd = () => {
      isDragging.current = false;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleEnd);
    window.addEventListener('touchmove', handleTouchMove, { passive: true });
    window.addEventListener('touchend', handleEnd);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleEnd);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleEnd);
    };
  }, [updatePosition]);

  const daysDiff = daysBetween(comparison.left.target_date, comparison.right.target_date);

  return (
    <>
      {/* Slider line and handle */}
      <div
        ref={sliderRef}
        style={{
          position: 'absolute',
          top: 0,
          left: `${sliderPosition}%`,
          bottom: 0,
          width: 40,
          transform: 'translateX(-50%)',
          zIndex: 1000,
          cursor: 'ew-resize',
          touchAction: 'none',
        }}
        onMouseDown={handleMouseDown}
        onTouchStart={handleTouchStart}
      >
        {/* Vertical line */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: '50%',
            width: 3,
            transform: 'translateX(-50%)',
            backgroundColor: 'white',
            boxShadow: '0 0 8px rgba(0,0,0,0.5)',
            pointerEvents: 'none',
          }}
        />

        {/* Handle */}
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: 40,
            height: 40,
            borderRadius: '50%',
            backgroundColor: 'white',
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'ew-resize',
          }}
        >
          <IconArrowsHorizontal size={20} color="#333" />
        </div>
      </div>

      {/* Labels for left image */}
      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{
          position: 'absolute',
          top: 10,
          left: 10,
          zIndex: 1000,
          maxWidth: 160,
          pointerEvents: 'none',
        }}
      >
        <Text size="xs" fw={600} c="blue.7">
          {comparison.left.target_date}
        </Text>
        <Text size="xs" c="dimmed" truncate>
          {comparison.left.sensor}
        </Text>
      </Paper>

      {/* Labels for right image */}
      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{
          position: 'absolute',
          top: 10,
          right: 60,
          zIndex: 1000,
          maxWidth: 160,
          pointerEvents: 'none',
        }}
      >
        <Text size="xs" fw={600} c="green.7">
          {comparison.right.target_date}
        </Text>
        <Text size="xs" c="dimmed" truncate>
          {comparison.right.sensor}
        </Text>
      </Paper>

      {/* Info panel */}
      <Paper
        shadow="md"
        p="sm"
        radius="md"
        style={{
          position: 'absolute',
          bottom: 30,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 1000,
        }}
      >
        <Group gap="sm" wrap="nowrap">
          <Stack gap={2}>
            <Group gap="xs">
              <Badge size="sm" color="blue" variant="light">
                {comparison.left.sensor}
              </Badge>
              <Text size="xs" c="dimmed">
                vs
              </Text>
              <Badge size="sm" color="green" variant="light">
                {comparison.right.sensor}
              </Badge>
            </Group>
            <Text size="xs" c="dimmed" ta="center">
              {daysDiff} dias de diferencia
            </Text>
          </Stack>
          <CloseButton size="sm" onClick={onClear} aria-label="Cerrar comparacion" />
        </Group>
      </Paper>
    </>
  );
}

export default ComparisonLayers;
