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
  | 'entidades_no_permitidas'
  | 'lectura_fallida';

export class ErrorKml extends Error {
  readonly codigo: CodigoErrorKml;
  constructor(codigo: CodigoErrorKml, mensaje: string) {
    super(mensaje);
    this.name = 'ErrorKml';
    this.codigo = codigo;
  }
}

/** S4 caps: 10 MB per file, 20 000 vértices across every kept polygon. */
export const LIMITE_BYTES_KML = 10 * 1024 * 1024;
export const LIMITE_VERTICES_KML = 20_000;

// ── geometry normalization (strip Z, close rings) ────────────────────────────

type Posicion2D = [number, number];

/** One position → [lon, lat]; Z (and anything past 2D) is dropped. */
function aPosicion2D(posicion: readonly number[]): Posicion2D | null {
  if (typeof posicion[0] !== 'number' || typeof posicion[1] !== 'number') return null;
  return [posicion[0], posicion[1]];
}

/**
 * One ring → closed 2D ring. Returns null when the ring has no usable
 * interior (fewer than 3 DISTINCT positions after stripping — a degenerate
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
  if (primera[0] !== ultima[0] || primera[1] !== ultima[1])
    posiciones.push([primera[0], primera[1]]);
  return posiciones;
}

/** Normalize one Polygon's rings; null when nothing polygonal survives. */
function normalizarPoligono(anillos: readonly (readonly (readonly number[])[])[]): Polygon | null {
  const coordenadas: Posicion2D[][] = [];
  for (const anillo of anillos) {
    const normalizado = normalizarAnillo(anillo);
    if (normalizado) coordenadas.push(normalizado);
  }
  if (coordenadas.length === 0) return null;
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
 * KML text → the polygonal selection candidates (S4).
 *
 * Pure on purpose: the worker, the vitest suite and the inline fallback all
 * call this same function, so the parse contract cannot drift between the
 * three.
 */
export function kmlAPoligonos(texto: string): PoligonoKml[] {
  // Guard anti billion-laughs/XXE (CodeQL: entity expansion): KML legítimo
  // (Google Earth, QGIS) NO usa DTDs ni entidades — cualquier declaración
  // de ENTITY/DOCTYPE en un archivo subido es ataque, no contenido.
  // (Literal .includes() — CodeQL's xml-bomb query recognizes this guard
  // shape; a regex .test() with the same semantics was not recognized.)
  if (texto.includes('<!DOCTYPE') || texto.includes('<!ENTITY')) {
    throw new ErrorKml(
      'entidades_no_permitidas',
      'El KML incluye declaraciones de entidad no permitidas.'
    );
  }
  // Reviewed false positives (CodeQL HIGH), reasons kept next to each rule:
  //   xml-bomb — browser DOMParser hard-caps entity expansion (a
  //     server-parser threat), and the DOCTYPE/ENTITY guard above rejects
  //     the input outright anyway.
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
      nombreBruto !== null
        ? nombreBruto.replace(/[<>&"']/g, '').slice(0, 120) || null
        : null;
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

/**
 * KMZ bytes → the text of its FIRST `.kml` entry (S4). jszip lazily reads
 * only that entry's stream, so a bloated archive costs memory once, not
 * twice.
 */
export async function kmzATexto(buffer: ArrayBuffer): Promise<string> {
  const archivo = await JSZip.loadAsync(buffer);
  const entrada =
    Object.keys(archivo.files)
      .filter((nombre) => nombre.toLowerCase().endsWith('.kml'))
      .sort((a, b) => a.length - b.length)[0] ?? null;
  if (!entrada) {
    throw new ErrorKml('archivo_invalido', 'El KMZ no contiene ningún KML.');
  }
  return archivo.files[entrada].async('string');
}

/**
 * One picked file → the polygonal candidates, enforcing the S4 caps.
 *
 * The size cap fires BEFORE any parse (the cheapest possible rejection);
 * the vertex cap fires DURING the geometry walk. Everything else about the
 * file (points, lines, weird styles) is handled by the parse itself.
 */
export async function procesarArchivoKml(archivo: File): Promise<PoligonoKml[]> {
  if (archivo.size > LIMITE_BYTES_KML) {
    throw new ErrorKml(
      'archivo_grande',
      `El archivo pesa más de ${(LIMITE_BYTES_KML / 1024 / 1024).toFixed(0)} MB.`
    );
  }
  const esKmz = archivo.name.toLowerCase().endsWith('.kmz');
  let texto: string;
  try {
    texto = esKmz ? await kmzATexto(await archivo.arrayBuffer()) : await archivo.text();
  } catch (error) {
    if (error instanceof ErrorKml) throw error;
    throw new ErrorKml('lectura_fallida', 'No se pudo leer el archivo.');
  }
  return kmlAPoligonos(texto);
}

// ── the worker bridge ────────────────────────────────────────────────────────

/** What the worker posts back: either the polygons or a coded failure. */
export type MensajeKmlWorker =
  | { ok: true; poligonos: PoligonoKml[] }
  | { ok: false; codigo: CodigoErrorKml | 'worker_incapaz'; mensaje: string };

/**
 * Read one file OFF the main thread (S7: "sin congelar la página").
 *
 * The worker path is the production route; two failure modes degrade to the
 * SAME pure function inline, so behavior never depends on where the parse
 * ran:
 *
 *  - the Worker constructor throws (unhappy embedders, odd test DOMs);
 *  - the worker reports `worker_incapaz` (no DOMParser in that worker
 *    context) or fails to load at all.
 *
 * The inline fallback blocks the page, yes — but only where the environment
 * already denied the worker, which in practice is the test DOM.
 */
export function leerArchivoKml(archivo: File): Promise<PoligonoKml[]> {
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
      if (mensaje.ok) resolve(mensaje.poligonos);
      else if (mensaje.codigo === 'worker_incapaz') fallarAlInline();
      else reject(new ErrorKml(mensaje.codigo as CodigoErrorKml, mensaje.mensaje));
    };
    activo.onerror = fallarAlInline;
    activo.postMessage(archivo);
  });
}
