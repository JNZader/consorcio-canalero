import type { StyleSpecification } from 'maplibre-gl';
import { TILE_LAYERS } from '../../constants/mapStyles';
import { getMartinTileUrl, MARTIN_SOURCES } from '../../hooks/useMartinLayers';
import { MAP_GLYPHS_URL } from '../map2d/roadLabelLayer';
import { TERRAIN_DEFAULT_EXAGGERATION } from './terrainExaggeration';

/**
 * Estilo inicial del visor 3D. La base es siempre el satélite Esri:
 * el mesh de Zona Consorcio es el terreno, no una capa perimetral extra.
 */
export function buildTerrainMapStyle(params: {
  terrainRgbUrl: string;
  textureUrl: string;
  overlayOpacity: number;
}): StyleSpecification {
  const { terrainRgbUrl, textureUrl, overlayOpacity } = params;
  return {
    version: 8,
    glyphs: MAP_GLYPHS_URL,
    sources: {
      'terrain-rgb': {
        type: 'raster-dem',
        tiles: [terrainRgbUrl],
        tileSize: 256,
        maxzoom: 14,
        encoding: 'mapbox',
      },
      'terrain-texture': {
        type: 'raster',
        tiles: [textureUrl],
        tileSize: 256,
      },
      satellite: {
        type: 'raster',
        tiles: [TILE_LAYERS.satellite.url],
        tileSize: 256,
        attribution: TILE_LAYERS.satellite.attribution,
      },
      puntos_conflicto_src: {
        type: 'vector',
        tiles: [getMartinTileUrl('puntos_conflicto')],
        minzoom: 0,
        maxzoom: 22,
      },
    },
    layers: [
      {
        id: 'satellite-base',
        type: 'raster',
        source: 'satellite',
        layout: { visibility: 'visible' },
        paint: { 'raster-opacity': 1 },
      },
      {
        id: 'dem-overlay',
        type: 'raster',
        source: 'terrain-texture',
        paint: { 'raster-opacity': overlayOpacity },
      },
      {
        id: 'puntos_conflicto-circle',
        type: 'circle',
        source: 'puntos_conflicto_src',
        'source-layer': MARTIN_SOURCES.puntos_conflicto.table,
        layout: { visibility: 'none' },
        paint: {
          'circle-color': MARTIN_SOURCES.puntos_conflicto.style.fillColor,
          'circle-opacity': MARTIN_SOURCES.puntos_conflicto.style.fillOpacity,
          'circle-radius': MARTIN_SOURCES.puntos_conflicto.style.radius,
          'circle-stroke-color': MARTIN_SOURCES.puntos_conflicto.style.color,
          'circle-stroke-width': MARTIN_SOURCES.puntos_conflicto.style.weight,
        },
      },
    ],
    terrain: {
      source: 'terrain-rgb',
      exaggeration: TERRAIN_DEFAULT_EXAGGERATION,
    },
  };
}
