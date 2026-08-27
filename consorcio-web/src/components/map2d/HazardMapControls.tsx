import type { HazardControlsProps } from './hazardControls.types';
import { HazardControls } from './HazardControls';
import { HazardControlsMobile } from './HazardControlsMobile';

interface HazardMapControlsProps {
  readonly active: boolean;
  readonly desktop: boolean;
  readonly desktopCollapsed: boolean;
  readonly mobileCollapsed: boolean;
  readonly onDesktopCollapsedChange: (collapsed: boolean) => void;
  readonly onMobileCollapsedChange: (collapsed: boolean) => void;
  readonly controls: Omit<HazardControlsProps, 'collapsed' | 'onCollapsedChange'>;
}

/** Keeps responsive hazard controls mounted only while the lifecycle is active. */
export function HazardMapControls({
  active,
  desktop,
  desktopCollapsed,
  mobileCollapsed,
  onDesktopCollapsedChange,
  onMobileCollapsedChange,
  controls,
}: HazardMapControlsProps) {
  if (!active) return null;

  if (desktop) {
    return (
      <HazardControls
        {...controls}
        collapsed={desktopCollapsed}
        onCollapsedChange={onDesktopCollapsedChange}
      />
    );
  }

  return (
    <HazardControlsMobile
      {...controls}
      collapsed={mobileCollapsed}
      onCollapsedChange={onMobileCollapsedChange}
    />
  );
}
