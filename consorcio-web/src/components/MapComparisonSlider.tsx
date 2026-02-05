/**
 * Side-by-side image comparison slider for the map.
 * Allows dragging a vertical line to compare two satellite images.
 */

import { Badge, CloseButton, Group, Paper, Stack, Text } from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ImageComparison } from '../hooks/useImageComparison';
import { IconArrowsHorizontal } from './ui/icons';

interface MapComparisonSliderProps {
  comparison: ImageComparison;
  onClear: () => void;
  /** Ref to the left image tile layer container */
  leftLayerRef: React.RefObject<HTMLElement | null>;
}

/**
 * Calculates days between two dates
 */
function daysBetween(date1: string, date2: string): number {
  const d1 = new Date(date1);
  const d2 = new Date(date2);
  const diffTime = Math.abs(d2.getTime() - d1.getTime());
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

export function MapComparisonSlider({ comparison, onClear, leftLayerRef }: MapComparisonSliderProps) {
  const [sliderPosition, setSliderPosition] = useState(50); // percentage
  const isDragging = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Apply clip-path to left layer based on slider position
  useEffect(() => {
    const leftLayer = leftLayerRef.current;
    if (!leftLayer) return;

    // Clip the left layer to only show the left portion
    leftLayer.style.clipPath = `inset(0 ${100 - sliderPosition}% 0 0)`;

    return () => {
      leftLayer.style.clipPath = '';
    };
  }, [sliderPosition, leftLayerRef]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
  }, []);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    isDragging.current = true;
  }, []);

  const updatePosition = useCallback((clientX: number) => {
    const container = containerRef.current?.parentElement;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = clientX - rect.left;
    const percentage = Math.max(5, Math.min(95, (x / rect.width) * 100));
    setSliderPosition(percentage);
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
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
    window.addEventListener('touchmove', handleTouchMove);
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
        ref={containerRef}
        style={{
          position: 'absolute',
          top: 0,
          left: `${sliderPosition}%`,
          bottom: 0,
          width: 4,
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

      {/* Labels for left and right images */}
      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{
          position: 'absolute',
          top: 10,
          left: 10,
          zIndex: 1000,
          maxWidth: 180,
        }}
      >
        <Text size="xs" fw={600} c="blue.7">
          {comparison.left.target_date}
        </Text>
        <Text size="xs" c="dimmed" truncate>
          {comparison.left.visualization_description}
        </Text>
      </Paper>

      <Paper
        shadow="md"
        p="xs"
        radius="md"
        style={{
          position: 'absolute',
          top: 10,
          right: 60,
          zIndex: 1000,
          maxWidth: 180,
        }}
      >
        <Text size="xs" fw={600} c="green.7">
          {comparison.right.target_date}
        </Text>
        <Text size="xs" c="dimmed" truncate>
          {comparison.right.visualization_description}
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
              <Text size="xs" c="dimmed">vs</Text>
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

export default MapComparisonSlider;
