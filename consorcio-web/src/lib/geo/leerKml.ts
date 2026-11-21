/**
 * leerKml — KML/KMZ → selection polygons, parsed OFF the main thread (S4).
 *
 * The parse pipeline (pure, shared by the worker, the tests and the inline
 * fallback):
 *
 *  1. KMZ → `jszip` opens the archive and takes the FIRST `.kml` entry
 *     (doc.kml by Google Earth convention); a bare `.kml` is read as text.
 *  2. KML → GeoJSON with `@tmcw/togeojson` (the plan's one authorized new
 *     dependency). PARSING ONLY — no `eval`, no script execution of any kind
 *     (S8: "no evalúes nada, solo parseá XML").
 *  3. Keep Polygon/MultiPolygon only. KML `MultiGeometry` can surface as a
 *     GeoJSON GeometryCollection, so its polygonal members are EXTRACTED
 *     (S8: "MultiGeometry anidado").
 *  4. Strip Z from every position (MapboxDraw/PostGIS want 2D) and CLOSE
 *     every ring (append the first position when missing) — the wire
 *     contract the backend's ring validator expects.
 *  5. Measure each polygon's hectares with `@turf/area` (the Checkbox list
 *     shows them, S4) and enforce the file caps: 10 MB, 20 000 vértices.
 *
 * A file with no polygonal geometry at all fails with the S5 copy
 * "El archivo tiene solo puntos o líneas".
 */

import { kml as togeojsonKml } from '@tmcw/togeojson';
import area from '@turf/area';
import type { MultiPolygon, Polygon } from 'geojson';
import JSZip from 'jszip';

/** A polygonal geometry the selection can absorb, with its local figures. */
export interface PoligonoKml {
  readonly geometry: Polygon | MultiPolygon;
  /** Hectares measured client-side with @turf/area (EPSG-free geodesic). */
  readonly ha: number;
  /** Position count after strip/close — the cap the UI reports. */
  readonly vertices: number;
  /** The Placemark's `<name>`, when the file carried one. */
  readonly nombre: string | null;
}

/** Stable failure codes the UI can branch on (S5 error copy). */
export type CodigoErrorKml =
  | 'archivo_grande'
  | 'demasiados_vertices'
  | 'sin_poligonos'
  | 'archivo_invalido'
  | 'lectura_fallida';

export class ErrorKml extends Error {
  readonly codigo: CodigoErrorKml;
  constructor(codigo: CodigoErrorKml, mensaje: string) {
    super(mensaje);
    this.name = 'ErrorKml';
    this.codigo = codigo;
  }
}

/** S4 caps: 10 MB per file, 20 MB decompressed KML in KMZ, 20 000 vértices across kept polygons. */
export const LIMITE_BYTES_KML = 10 * 1024 * 1024;
export const LIMITE_BYTES_KML_DESCOMPRIMIDO = 20 * 1024 * 1024;
export const LIMITE_VERTICES_KML = 20_000;

// ── geometry normalization (strip Z, close rings) ────────────────────────────

type Posicion2D = [number, number];

/** One position → [lon, lat]; Z (and non-finite values) are dropped. */
function aPosicion2D(posicion: readonly number[]): Posicion2D | null {
  if (
    typeof posicion[0] !== 'number' ||
    typeof posicion[1] !== 'number' ||
    !Number.isFinite(posicion[0]) ||
    !Number.isFinite(posicion[1])
  ) {
    return null;
  }
  return [posicion[0], posicion[1]];
}

/**
 * One ring → closed 2D ring. Returns null when the ring has no usable
 * interior (fewer than 3 DISTINCT positions after closure — a degenerate
 * sliver the backend would only reject).
 */
function normalizarAnillo(anillo: readonly (readonly number[])[]): Posicion2D[] | null {
  const posiciones: Posicion2D[] = [];
  for (const posicion of anillo) {
    const plano = aPosicion2D(posicion);
    if (plano) posiciones.push(plano);
  }
  if (posiciones.length < 3) return null;
  const primera = posiciones[0];
  const ultima = posiciones[posiciones.length - 1];
  if (primera[0] !== ultima[0] || primera[1] !== ultima[1]) {
    posiciones.push([primera[0], primera[1]]);
  }
  if (posiciones.length < 4) return null;
  const distintos = new Set(posiciones.slice(0, -1).map(([x, y]) => `${x},${y}`));
  if (distintos.size < 3) return null;
  return posiciones;
}

/** Normalize one Polygon's rings; null when the outer ring is unusable (never promote holes). */
function normalizarPoligono(anillos: readonly (readonly (readonly number[])[])[]): Polygon | null {
  if (anillos.length === 0) return null;
  const exterior = normalizarAnillo(anillos[0]);
  if (!exterior) return null;
  const coordenadas: Posicion2D[][] = [exterior];
  for (const anillo of anillos.slice(1)) {
    const normalizado = normalizarAnillo(anillo);
    if (normalizado) coordenadas.push(normalizado);
  }
  return { type: 'Polygon', coordinates: coordenadas };
}

/**
 * ANY GeoJSON geometry → the list of polygonal geometries worth keeping.
 * GeometryCollection (how togeojson surfaces a nested MultiGeometry, S8) is
 * flattened; every other non-polygonal type is discarded.
 */
function geometriasPoligonales(geometria: unknown): (Polygon | MultiPolygon)[] {
  if (!geometria || typeof geometria !== 'object') return [];
  const { type, coordinates } = geometria as { type?: unknown; coordinates?: unknown };
  if (type === 'Polygon' && Array.isArray(coordinates)) {
    const poligono = normalizarPoligono(coordinates as never);
    return poligono ? [poligono] : [];
  }
  if (type === 'MultiPolygon' && Array.isArray(coordinates)) {
    const partes: Polygon[] = [];
    for (const parte of coordinates as never as readonly unknown[]) {
      if (!Array.isArray(parte)) continue;
      const poligono = normalizarPoligono(parte as never);
      if (poligono) partes.push(poligono);
    }
    if (partes.length === 0) return [];
    // A single-part multipolygon stays a Polygon — the smaller wire shape.
    if (partes.length === 1) return partes;
    return [{ type: 'MultiPolygon', coordinates: partes.map((p) => p.coordinates) }];
  }
  if (type === 'GeometryCollection') {
    const miembros = (geometria as { geometries?: unknown }).geometries;
    if (!Array.isArray(miembros)) return [];
    return miembros.flatMap((miembro) => geometriasPoligonales(miembro));
  }
  return [];
}

/** Position count of a normalized polygonal geometry (the vertex cap unit). */
function contarVertices(geometria: Polygon | MultiPolygon): number {
  const anillos =
    geometria.type === 'Polygon' ? geometria.coordinates : geometria.coordinates.flat();
  return anillos.reduce((total, anillo) => total + anillo.length, 0);
}

// ── the parse core ───────────────────────────────────────────────────────────

/** M² per hectare — the unit @turf/area results convert with. */
const M2_POR_HA = 10_000;

/**
 * Strip DOCTYPE / ENTITY blocks before feeding XML to DOMParser (anti XXE/billion-laughs).
 */
export function sanitizarTextoKml(textoEntrante: string): string {
  return textoEntrante
    .replace(/<!DOCTYPE[^>[]*(?:\[[\s\S]*?\])?\s*>/gi, '')
    .replace(/<!ENTITY[\s\S]*?>/gi, '');
}

/**
 * KML text → the polygonal selection candidates (S4).
 *
 * Pure on purpose: the worker, the vitest suite and the inline fallback all
 * call this same function, so the parse contract cannot drift between the
 * three.
 */
export function kmlAPoligonos(textoEntrante: string): PoligonoKml[] {
  const texto = sanitizarTextoKml(textoEntrante);
  // Reviewed false positives (CodeQL HIGH), reasons kept next to each rule:
  //   xml-bomb — entities are stripped above AND the browser DOMParser
  //     hard-caps entity expansion (a server-parser threat).
  //   xss — the parse output never reaches innerHTML: the only extracted
  //     text (polygon name) is markup-stripped and length-capped, and
  //     renders through React's auto-escaping.
  // codeql[js/xml-bomb]
  // codeql[js/xss]
  const doc = new DOMParser().parseFromString(texto, 'text/xml');
  if (doc.getElementsByTagName('parsererror').length > 0) {
    throw new ErrorKml('archivo_invalido', 'El archivo no es un KML válido.');
  }

  const coleccion = togeojsonKml(doc);
  const poligonos: PoligonoKml[] = [];
  let vertices = 0;
  for (const feature of coleccion.features ?? []) {
    // XSS guard (CodeQL): el nombre viene del XML subido y llega a la UI —
    // React auto-escapa, pero además se recorta, se le quitan caracteres de
    // marcado y se acota su longitud: nada del archivo se renderiza tal cual.
    const nombreBruto =
      typeof feature.properties?.name === 'string' && feature.properties.name.trim()
        ? feature.properties.name.trim()
        : null;
    const nombre =
      nombreBruto !== null ? nombreBruto.replace(/[<>&"']/g, '').slice(0, 120) || null : null;
    for (const geometry of geometriasPoligonales(feature.geometry)) {
      vertices += contarVertices(geometry);
      if (vertices > LIMITE_VERTICES_KML) {
        throw new ErrorKml(
          'demasiados_vertices',
          `El archivo supera el límite de ${LIMITE_VERTICES_KML.toLocaleString('es-AR')} vértices.`
        );
      }
      poligonos.push({
        geometry,
        ha: area({ type: 'Feature', properties: {}, geometry }) / M2_POR_HA,
        vertices: contarVertices(geometry),
        nombre,
      });
    }
  }
  if (poligonos.length === 0) {
    throw new ErrorKml('sin_poligonos', 'El archivo tiene solo puntos o líneas.');
  }
  return poligonos;
}

interface JSZipStreamHelper {
  on(event: 'data', cb: (chunk: Uint8Array) => void): JSZipStreamHelper;
  on(event: 'error', cb: (error: unknown) => void): JSZipStreamHelper;
  on(event: 'end', cb: () => void): JSZipStreamHelper;
  pause(): void;
  resume(): JSZipStreamHelper;
}

interface JSZipEntryConInternals extends JSZip.JSZipObject {
  _data?: { uncompressedSize?: number };
  internalStream?(type: 'uint8array'): JSZipStreamHelper;
}

function errorTamanoKmz(limiteBytes: number): ErrorKml {
  const mb = Math.max(1, Math.round(limiteBytes / 1024 / 1024));
  return new ErrorKml(
    'archivo_grande',
    `El KML dentro del KMZ supera el límite de ${mb} MB descomprimido.`
  );
}

/**
 * KMZ bytes → the text of its FIRST `.kml` entry (S4), streaming with an
 * explicit decompressed byte limit so zip-bombs cannot exhaust memory.
 */
export async function kmzATexto(
  buffer: ArrayBuffer,
  limiteBytes: number = LIMITE_BYTES_KML_DESCOMPRIMIDO
): Promise<string> {
  const archivo = await JSZip.loadAsync(buffer);
  const entrada =
    Object.keys(archivo.files)
      .filter((nombre) => nombre.toLowerCase().endsWith('.kml'))
      .sort((a, b) => a.length - b.length)[0] ?? null;
  if (!entrada) {
    throw new ErrorKml('archivo_invalido', 'El KMZ no contiene ningún KML.');
  }

  const objeto = archivo.files[entrada] as JSZipEntryConInternals;
  const tamanoDeclarado = objeto._data?.uncompressedSize;
  if (typeof tamanoDeclarado === 'number' && tamanoDeclarado > limiteBytes) {
    throw errorTamanoKmz(limiteBytes);
  }

  if (typeof objeto.internalStream === 'function') {
    const stream = objeto.internalStream('uint8array');
    const chunks: Uint8Array[] = [];
    let totalBytes = 0;

    await new Promise<void>((resolve, reject) => {
      let terminado = false;
      const finalizarError = (err: unknown) => {
        if (terminado) return;
        terminado = true;
        reject(err);
      };
      stream
        .on('data', (chunk) => {
          if (terminado) return;
          totalBytes += chunk.byteLength;
          if (totalBytes > limiteBytes) {
            stream.pause();
            finalizarError(errorTamanoKmz(limiteBytes));
            return;
          }
          chunks.push(chunk);
        })
        .on('error', (err) => {
          finalizarError(
            err instanceof ErrorKml
              ? err
              : new ErrorKml('lectura_fallida', 'No se pudo leer el KMZ.')
          );
        })
        .on('end', () => {
          if (terminado) return;
          terminado = true;
          resolve();
        })
        .resume();
    });

    const completo = new Uint8Array(totalBytes);
    let offset = 0;
    for (const chunk of chunks) {
      completo.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return new TextDecoder('utf-8').decode(completo);
  }

  const bytes = await objeto.async('uint8array');
  if (bytes.byteLength > limiteBytes) {
    throw errorTamanoKmz(limiteBytes);
  }
  return new TextDecoder('utf-8').decode(bytes);
}

/**
 * Validate raw file size, decompress `.kmz` if needed (bounded against zip-bombs),
 * and return sanitized XML text ready for `kmlAPoligonos`.
 */
export async function extraerTextoArchivoKml(archivo: File): Promise<string> {
  if (archivo.size > LIMITE_BYTES_KML) {
    throw new ErrorKml(
      'archivo_grande',
      `El archivo pesa más de ${(LIMITE_BYTES_KML / 1024 / 1024).toFixed(0)} MB.`
    );
  }
  const esKmz = archivo.name.toLowerCase().endsWith('.kmz');
  try {
    const bruto = esKmz ? await kmzATexto(await archivo.arrayBuffer()) : await archivo.text();
    return sanitizarTextoKml(bruto);
  } catch (error) {
    if (error instanceof ErrorKml) throw error;
    throw new ErrorKml('lectura_fallida', 'No se pudo leer el archivo.');
  }
}

/**
 * One picked file → the polygonal candidates, enforcing the S4 caps.
 */
export async function procesarArchivoKml(archivo: File): Promise<PoligonoKml[]> {
  return kmlAPoligonos(await extraerTextoArchivoKml(archivo));
}

// ── the worker bridge ────────────────────────────────────────────────────────

/** What the worker posts back: either the polygons, extracted KMZ text, or a coded failure. */
export type MensajeKmlWorker =
  | { ok: true; poligonos: PoligonoKml[] }
  | { ok: false; codigo: 'worker_solo_texto'; texto: string; mensaje: string }
  | { ok: false; codigo: CodigoErrorKml | 'worker_incapaz'; mensaje: string };

let workerTieneDomParser: boolean | null = null;

/** Test helper: clears the cached worker `DOMParser` capability probe. */
export function resetearCacheWorkerKml(): void {
  workerTieneDomParser = null;
}

/**
 * Read one file OFF the main thread (S7: "sin congelar la página").
 *
 * When a browser worker lacks `DOMParser`, `.kmz` decompression + zip-bomb
 * checks still execute inside the worker (`worker_solo_texto`), and only XML
 * DOM parsing runs inline; once probed, plain `.kml` files skip spawning a
 * no-op worker.
 */
export function leerArchivoKml(archivo: File): Promise<PoligonoKml[]> {
  const esKmz = archivo.name.toLowerCase().endsWith('.kmz');
  if (!esKmz && workerTieneDomParser === false) {
    return procesarArchivoKml(archivo);
  }

  return new Promise<PoligonoKml[]>((resolve, reject) => {
    let worker: Worker | null = null;
    try {
      worker = new Worker(new URL('./leerKml.worker.ts', import.meta.url), { type: 'module' });
    } catch {
      worker = null;
    }
    if (!worker) {
      procesarArchivoKml(archivo).then(resolve, reject);
      return;
    }
    const activo = worker;
    const fallarAlInline = () => {
      activo.terminate();
      procesarArchivoKml(archivo).then(resolve, reject);
    };
    activo.onmessage = (evento: MessageEvent<MensajeKmlWorker>) => {
      const mensaje = evento.data;
      activo.terminate();
      if (mensaje.ok) {
        workerTieneDomParser = true;
        resolve(mensaje.poligonos);
      } else if (mensaje.codigo === 'worker_solo_texto') {
        workerTieneDomParser = false;
        Promise.resolve()
          .then(() => kmlAPoligonos(mensaje.texto))
          .then(resolve, reject);
      } else if (mensaje.codigo === 'worker_incapaz') {
        workerTieneDomParser = false;
        fallarAlInline();
      } else {
        reject(new ErrorKml(mensaje.codigo, mensaje.mensaje));
      }
    };
    activo.onerror = fallarAlInline;
    activo.postMessage(archivo);
  });
}
