import type { CSSProperties, ReactNode } from 'react';

export type MapViewPaneMode = '2d' | '3d';

export interface MapViewPanesProps {
  readonly mode: MapViewPaneMode;
  /** First time the user opens 3D, the 3D tree is mounted and then kept. */
  readonly threeDArmed: boolean;
  readonly twoD: ReactNode;
  readonly threeD: ReactNode;
  readonly className?: string;
}

const HIDDEN: CSSProperties = { display: 'none' };
const SHOWN: CSSProperties = { display: 'block' };

/**
 * UX-17: do not unmount the 2D MapLibre instance when switching to 3D.
 * Hiding with `display:none` keeps WebGL; showing again relies on resize.
 */
export function MapViewPanes({ mode, threeDArmed, twoD, threeD, className }: MapViewPanesProps) {
  return (
    <div className={className} data-testid="map-view-panes" data-mode={mode}>
      <div
        data-testid="map-2d-keep-alive"
        hidden={mode !== '2d'}
        style={mode === '2d' ? SHOWN : HIDDEN}
      >
        {twoD}
      </div>
      {threeDArmed ? (
        <div
          data-testid="map-3d-keep-alive"
          hidden={mode !== '3d'}
          style={mode === '3d' ? SHOWN : HIDDEN}
        >
          {threeD}
        </div>
      ) : null}
    </div>
  );
}

export function shouldArmThreeD(previousArmed: boolean, mode: MapViewPaneMode): boolean {
  return previousArmed || mode === '3d';
}

/** Notify MapLibre after a pane is shown again (ResizeObserver + map.resize). */
export function notifyMapPaneShown(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event('resize'));
}
