export const TERRAIN_HILLSHADE_SOURCE_ID = 'terrain-hillshade-dem';

interface RasterDemLike {
  type?: string;
  tiles?: string[];
  url?: string;
  tileSize?: number;
  maxzoom?: number;
  minzoom?: number;
}

/**
 * 3D-07: hillshade must not share the `terrain-rgb` source used by setTerrain.
 * Clone the DEM tiles into a sibling raster-dem source.
 */
export function buildHillshadeDemSource(
  terrainRgb: RasterDemLike | null | undefined,
): {
  type: 'raster-dem';
  tiles: string[];
  tileSize: number;
  maxzoom?: number;
  minzoom?: number;
} | null {
  if (!terrainRgb) return null;
  const tiles = terrainRgb.tiles?.filter((tile) => typeof tile === 'string' && tile.length > 0) ?? [];
  if (tiles.length === 0 && typeof terrainRgb.url === 'string' && terrainRgb.url.length > 0) {
    return {
      type: 'raster-dem',
      tiles: [terrainRgb.url],
      tileSize: terrainRgb.tileSize ?? 256,
      maxzoom: terrainRgb.maxzoom,
      minzoom: terrainRgb.minzoom,
    };
  }
  if (tiles.length === 0) return null;
  return {
    type: 'raster-dem',
    tiles: [...tiles],
    tileSize: terrainRgb.tileSize ?? 256,
    maxzoom: terrainRgb.maxzoom,
    minzoom: terrainRgb.minzoom,
  };
}
