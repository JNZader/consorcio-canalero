import { createContext, type ReactNode, useContext } from 'react';

import type { TerrainAvailability } from './terrainAvailability';

export type MapPageViewMode = '2d' | '3d';

export interface MapPageViewValue {
  readonly mode: MapPageViewMode;
  readonly setMode: (mode: MapPageViewMode) => void;
  /** DEM list resolved and a `dem_raw` layer exists. */
  readonly terrainReady: boolean;
  readonly terrainHint: string | null;
  readonly terrainStatus: TerrainAvailability;
  readonly onRetryTerrain?: () => void;
}

const MapPageViewContext = createContext<MapPageViewValue | null>(null);

export function MapPageViewProvider({
  value,
  children,
}: {
  readonly value: MapPageViewValue;
  readonly children: ReactNode;
}) {
  return <MapPageViewContext.Provider value={value}>{children}</MapPageViewContext.Provider>;
}

/** `null` when the map shell is rendered outside `MapaPage` (unit fixtures). */
export function useMapPageView(): MapPageViewValue | null {
  return useContext(MapPageViewContext);
}
