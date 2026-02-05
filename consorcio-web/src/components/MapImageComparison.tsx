/**
 * Component for side-by-side satellite image comparison on the map.
 * Uses a slider to compare two satellite images.
 *
 * Split into two components:
 * - ComparisonLayers: Renders TileLayers inside MapContainer
 * - ComparisonSliderUI: Renders slider UI outside MapContainer
 *
 * Uses per-tile clipping inspired by leaflet-side-by-side plugin
 * to handle map panning correctly.
 */

import { Badge, CloseButton, Group, Paper, Stack, Text } from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { TileLayer, useMap } from 'react-leaflet';
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
  comparison: ImageComparison;
  sliderPosition: number;
}

/**
 * Clips individual tile elements based on their screen position.
 * This handles map panning correctly because we recalculate on every move.
 */
function clipTilesInPane(
  pane: HTMLElement,
  containerRect: DOMRect,
  dividerX: number,
  side: 'left' | 'right'
) {
  const tiles = pane.querySelectorAll('.leaflet-tile');
  tiles.forEach((tile) => {
    const tileEl = tile as HTMLElement;
    const tileRect = tileEl.getBoundingClientRect();

    // Calculate tile position relative to container
    const tileLeft = tileRect.left - containerRect.left;
    const tileRight = tileRect.right - containerRect.left;
    const tileWidth = tileRect.width;

    if (side === 'left') {
      // For left pane: show only the portion to the left of divider
      if (tileRight <= dividerX) {
        // Tile is completely to the left of divider - show all
        tileEl.style.clip = '';
      } else if (tileLeft >= dividerX) {
        // Tile is completely to the right of divider - hide all
        tileEl.style.clip = 'rect(0, 0, 0, 0)';
      } else {
        // Tile crosses the divider - clip it
        const clipRight = dividerX - tileLeft;
        tileEl.style.clip = `rect(0, ${clipRight}px, ${tileRect.height}px, 0)`;
      }
    } else {
      // For right pane: show only the portion to the right of divider
      if (tileLeft >= dividerX) {
        // Tile is completely to the right of divider - show all
        tileEl.style.clip = '';
      } else if (tileRight <= dividerX) {
        // Tile is completely to the left of divider - hide all
        tileEl.style.clip = 'rect(0, 0, 0, 0)';
      } else {
        // Tile crosses the divider - clip it
        const clipLeft = dividerX - tileLeft;
        tileEl.style.clip = `rect(0, ${tileWidth}px, ${tileRect.height}px, ${clipLeft}px)`;
      }
    }
  });
}

/**
 * Renders the two TileLayers for comparison.
 * Must be rendered inside MapContainer.
 * Uses per-tile clipping for correct behavior during map pan/zoom.
 */
export function ComparisonLayers({ comparison, sliderPosition }: ComparisonLayersProps) {
  const map = useMap();
  const [panesReady, setPanesReady] = useState(false);

  // Create custom panes for BOTH layers
  // z-index between tilePane (200) and overlayPane (400) so they don't cover vector layers
  useEffect(() => {
    // Create pane for RIGHT image (full, bottom of comparison) - z-index 250
    let rightPane = map.getPane('comparisonRight');
    if (!rightPane) {
      rightPane = map.createPane('comparisonRight');
      rightPane.style.zIndex = '250';
    }

    // Create pane for LEFT image (clipped, top of comparison) - z-index 251
    let leftPane = map.getPane('comparisonLeft');
    if (!leftPane) {
      leftPane = map.createPane('comparisonLeft');
      leftPane.style.zIndex = '251';
    }

    setPanesReady(true);

    return () => {
      // Clean up clips on unmount
      const lp = map.getPane('comparisonLeft');
      const rp = map.getPane('comparisonRight');
      if (lp) {
        lp.querySelectorAll('.leaflet-tile').forEach((t) => {
          (t as HTMLElement).style.clip = '';
        });
      }
      if (rp) {
        rp.querySelectorAll('.leaflet-tile').forEach((t) => {
          (t as HTMLElement).style.clip = '';
        });
      }
    };
  }, [map]);

  // Update tile clips on slider position change and map move
  useEffect(() => {
    if (!panesReady) return;

    const updateClips = () => {
      const leftPane = map.getPane('comparisonLeft');
      const rightPane = map.getPane('comparisonRight');
      if (!leftPane || !rightPane) return;

      const container = map.getContainer();
      const containerRect = container.getBoundingClientRect();
      const dividerX = (sliderPosition / 100) * containerRect.width;

      // Clip tiles in both panes
      clipTilesInPane(leftPane, containerRect, dividerX, 'left');
      clipTilesInPane(rightPane, containerRect, dividerX, 'right');
    };

    // Initial update
    updateClips();

    // Update on map events
    map.on('move', updateClips);
    map.on('moveend', updateClips);
    map.on('zoomend', updateClips);
    map.on('resize', updateClips);

    // Also update when new tiles are loaded
    const observer = new MutationObserver(updateClips);
    const leftPane = map.getPane('comparisonLeft');
    const rightPane = map.getPane('comparisonRight');
    if (leftPane) {
      observer.observe(leftPane, { childList: true, subtree: true });
    }
    if (rightPane) {
      observer.observe(rightPane, { childList: true, subtree: true });
    }

    return () => {
      map.off('move', updateClips);
      map.off('moveend', updateClips);
      map.off('zoomend', updateClips);
      map.off('resize', updateClips);
      observer.disconnect();
    };
  }, [map, sliderPosition, panesReady]);

  // Don't render TileLayers until panes are ready
  if (!panesReady) {
    return null;
  }

  return (
    <>
      {/* Right image (bottom layer) - in comparisonRight pane */}
      <TileLayer
        key={`right-${comparison.right.tile_url}`}
        url={comparison.right.tile_url}
        attribution="&copy; Google Earth Engine"
        opacity={1}
        maxZoom={18}
        pane="comparisonRight"
      />
      {/* Left image (top layer) - in comparisonLeft pane */}
      <TileLayer
        key={`left-${comparison.left.tile_url}`}
        url={comparison.left.tile_url}
        attribution="&copy; Google Earth Engine"
        opacity={1}
        maxZoom={18}
        pane="comparisonLeft"
      />
    </>
  );
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
 * Must be rendered OUTSIDE MapContainer, but inside a positioned container.
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
