import { useEffect, useState } from 'react';

interface RasterLoadMap {
  on: (event: string, handler: (event: { sourceId?: string }) => void) => void;
  off: (event: string, handler: (event: { sourceId?: string }) => void) => void;
}

const RASTER_SOURCE_HINT = /dem|raster|overlay|terrain-texture|gee/i;

export function isRasterSourceId(sourceId: string | undefined): boolean {
  if (!sourceId) return false;
  return RASTER_SOURCE_HINT.test(sourceId);
}

/** UX-11: true while MapLibre is fetching the active raster overlay. */
export function useRasterTileLoading(
  map: RasterLoadMap | null,
  enabled: boolean,
): boolean {
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!map || !enabled) {
      setLoading(false);
      return;
    }
    const onLoading = (event: { sourceId?: string }) => {
      if (isRasterSourceId(event.sourceId)) setLoading(true);
    };
    const onIdle = () => setLoading(false);
    map.on('sourcedataloading', onLoading);
    map.on('idle', onIdle);
    return () => {
      map.off('sourcedataloading', onLoading);
      map.off('idle', onIdle);
    };
  }, [enabled, map]);

  return loading;
}
