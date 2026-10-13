import * as maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';

/** One MapLibre `pmtiles://` protocol for the app. Register before any source. */
export const pmtilesProtocol = new Protocol();
maplibregl.addProtocol('pmtiles', pmtilesProtocol.tile.bind(pmtilesProtocol));
