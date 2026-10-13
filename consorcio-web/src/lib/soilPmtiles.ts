import { FileSource, PMTiles } from 'pmtiles';

import { pmtilesProtocol } from './pmtilesProtocol';
import { erroresUi, textoError } from './userFacingError';

/** Bundled archive (`package.json` `gen:pmtiles`). Pages cannot Range this file. */
export const SOIL_PMTILES_PATH = '/data/suelos_cu.pmtiles';
export const SOIL_PMTILES_ARCHIVE_KEY = 'suelos_cu.pmtiles';

let archivePromise: Promise<string> | null = null;
let archiveKey: string | null = null;

export function getSoilPmtilesArchiveKey(): string | null {
  return archiveKey;
}

export function soilPmtilesMapUrl(key: string): string {
  return `pmtiles://${key}`;
}

export function resetSoilPmtilesArchiveForTests(): void {
  archivePromise = null;
  archiveKey = null;
}

export function setSoilPmtilesArchiveKeyForTests(key: string): void {
  archiveKey = key;
}

/**
 * Load the 350 KB archive in one GET (no Range). Cloudflare Pages returns the
 * whole file for Range requests; FetchSource then throws and 2D soils stay blank.
 */
export function ensureSoilPmtilesArchive(): Promise<string> {
  archivePromise ??= (async () => {
    const response = await fetch(SOIL_PMTILES_PATH);
    if (!response.ok) {
      throw new Error(textoError(erroresUi.cargarSuelos, `Respuesta ${response.status}.`));
    }
    const buffer = await response.arrayBuffer();
    const file = new File([buffer], SOIL_PMTILES_ARCHIVE_KEY, {
      type: 'application/octet-stream',
    });
    const tiles = new PMTiles(new FileSource(file));
    pmtilesProtocol.add(tiles);
    archiveKey = tiles.source.getKey();
    return archiveKey;
  })();
  return archivePromise;
}
