/**
 * Campo (PR 6, S6) — point-in-class and distance-to-edge maths, pure.
 *
 * The GPS panel answers two questions per fix, client-side, offline:
 *
 *  1. **¿En qué clase estoy?** — ray-casting point-in-polygon over the
 *     package's dissolved class polygons (GeoJSON Polygon/MultiPolygon,
 *     holes honored). No turf dependency: the dep list stays closed and a
 *     hand-rolled 30-line PIP is easier to trust than a polyfill chain.
 *  2. **¿Estoy al límite?** — geodesic-enough distance from the fix to the
 *     nearest edge of its own class, compared against the GPS accuracy
 *     radius. Inside that radius the neighbouring class is a real
 *     possibility, so the panel warns and NAMES the neighbour (S6:
 *     "Estás en el límite entre Medio y Alto"). Distances use a local
 *     equirectangular projection around the fix — at GPS accuracies
 *     (5–100 m) the error versus a true geodesic is sub-centimetric.
 */

import type { ClaseCampo, GeometriaGeoJSON, TemaCampo } from './tiposCampo';

export type LngLat = [number, number];

type Anillo = number[][];

function anillosDe(geometria: GeometriaGeoJSON): Anillo[] {
  const anillos: Anillo[] = [];
  const coords = geometria.coordinates as unknown;
  if (geometria.type === 'Polygon' && Array.isArray(coords)) {
    for (const anillo of coords as Anillo[]) anillos.push(anillo);
  } else if (geometria.type === 'MultiPolygon' && Array.isArray(coords)) {
    for (const poligono of coords as Anillo[][]) {
      for (const anillo of poligono) anillos.push(anillo);
    }
  }
  return anillos;
}

/** Ray casting on one ring. True when the point is inside the ring. */
function puntoEnAnillo(x: number, y: number, anillo: Anillo): boolean {
  let dentro = false;
  for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
    const xi = anillo[i][0];
    const yi = anillo[i][1];
    const xj = anillo[j][0];
    const yj = anillo[j][1];
    const cruza = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (cruza) dentro = !dentro;
  }
  return dentro;
}

/** PIP for a Polygon/MultiPolygon with holes (first ring outer, rest holes). */
export function puntoEnGeometria(pt: LngLat, geometria: GeometriaGeoJSON): boolean {
  if (geometria.type === 'Polygon') {
    const anillos = anillosDe(geometria);
    if (!anillos.length || !puntoEnAnillo(pt[0], pt[1], anillos[0])) return false;
    return !anillos.some((anillo, i) => i > 0 && puntoEnAnillo(pt[0], pt[1], anillo));
  }
  if (geometria.type === 'MultiPolygon') {
    const coords = geometria.coordinates as Anillo[][];
    return coords.some(
      (poligono) =>
        poligono.length > 0 &&
        puntoEnAnillo(pt[0], pt[1], poligono[0]) &&
        !poligono.some((anillo, i) => i > 0 && puntoEnAnillo(pt[0], pt[1], anillo))
    );
  }
  return false;
}

export function puntoEnClase(pt: LngLat, clase: ClaseCampo): boolean {
  return clase.geometrias.some((g) => puntoEnGeometria(pt, g));
}

/** The class containing the point, or null when the fix falls outside. */
export function claseEnPunto(tema: TemaCampo, pt: LngLat): ClaseCampo | null {
  for (const clase of tema.clases) {
    if (puntoEnClase(pt, clase)) return clase;
  }
  return null;
}

const METROS_POR_GRADO_LAT = 110_540;

/** Metres-per-degree-lon at a latitude (local scale for the projection). */
function escalaLon(lat: number): number {
  return Math.max(METROS_POR_GRADO_LAT * Math.cos((lat * Math.PI) / 180), 1e-6);
}

/** Segment→point distance in METRES, equirectangular around the fix. */
function distanciaSegmentoM(pt: LngLat, a: number[], b: number[], escalaLonLocal: number): number {
  const px = pt[0] * escalaLonLocal;
  const py = pt[1] * METROS_POR_GRADO_LAT;
  const ax = a[0] * escalaLonLocal;
  const ay = a[1] * METROS_POR_GRADO_LAT;
  const bx = b[0] * escalaLonLocal;
  const by = b[1] * METROS_POR_GRADO_LAT;
  const dx = bx - ax;
  const dy = by - ay;
  const largo2 = dx * dx + dy * dy;
  let t = largo2 > 0 ? ((px - ax) * dx + (py - ay) * dy) / largo2 : 0;
  t = Math.min(1, Math.max(0, t));
  const cx = ax + t * dx;
  const cy = ay + t * dy;
  return Math.hypot(px - cx, py - cy);
}

/** Min distance (m) from the point to the edges of one geometry's rings. */
function distanciaABordeM(pt: LngLat, geometrias: GeometriaGeoJSON[]): number {
  const escala = escalaLon(pt[1]);
  let minimo = Number.POSITIVE_INFINITY;
  for (const geometria of geometrias) {
    for (const anillo of anillosDe(geometria)) {
      for (let i = 0; i + 1 < anillo.length; i++) {
        minimo = Math.min(minimo, distanciaSegmentoM(pt, anillo[i], anillo[i + 1], escala));
      }
    }
  }
  return minimo;
}

export interface AnalisisPosicion {
  clase: ClaseCampo | null;
  /** True when the fix is within `precisionM` of its class edge (S6). */
  enLimite: boolean;
  /** The class on the other side of that edge, when known. */
  vecino: ClaseCampo | null;
  /** Metres to the own-class edge (Infinity outside every class). */
  distanciaBordeM: number;
}

/**
 * Full GPS-fix analysis over one theme: class + boundary proximity.
 *
 * The neighbour is found by probing ~3 m beyond the nearest edge point —
 * the dissolved classes tile the selection, so just across the boundary
 * there IS another class (or the outside, when the edge is the selection
 * itself → `vecino: null`, the warning still fires).
 */
export function analizarPosicion(
  tema: TemaCampo | null,
  pt: LngLat | null,
  precisionM: number
): AnalisisPosicion {
  if (!tema || !pt) {
    return {
      clase: null,
      enLimite: false,
      vecino: null,
      distanciaBordeM: Number.POSITIVE_INFINITY,
    };
  }
  const clase = claseEnPunto(tema, pt);
  if (!clase) {
    return {
      clase: null,
      enLimite: false,
      vecino: null,
      distanciaBordeM: Number.POSITIVE_INFINITY,
    };
  }
  const distancia = distanciaABordeM(pt, clase.geometrias);
  if (!Number.isFinite(distancia) || distancia >= Math.max(precisionM, 1)) {
    return { clase, enLimite: false, vecino: null, distanciaBordeM: distancia };
  }
  return {
    clase,
    enLimite: true,
    vecino: vecinoDelLado(tema, pt, distancia),
    distanciaBordeM: distancia,
  };
}

/** Probe 3 m past the nearest edge, on the away-from-fix side. */
function vecinoDelLado(tema: TemaCampo, pt: LngLat, distanciaM: number): ClaseCampo | null {
  // Walk outward in small steps; the first class that is NOT the current
  // one and contains a probe wins. 3–8 m clears the boundary jitter of
  // simplified vectors without jumping over a sliver class.
  const pasos = [distanciaM + 3, distanciaM + 8, distanciaM + 20];
  const claseActual = claseEnPunto(tema, pt);
  if (!claseActual) return null;
  for (const paso of pasos) {
    for (let angulo = 0; angulo < 360; angulo += 45) {
      const rad = (angulo * Math.PI) / 180;
      const dLon = (paso * Math.sin(rad)) / escalaLon(pt[1]);
      const dLat = (paso * Math.cos(rad)) / METROS_POR_GRADO_LAT;
      const sonda: LngLat = [pt[0] + dLon, pt[1] + dLat];
      const encontrada = claseEnPunto(tema, sonda);
      if (encontrada && encontrada.clase !== claseActual.clase) return encontrada;
    }
  }
  return null;
}

/** Maximum rendered accuracy circle radius (m) so coarse cell-tower fixes stay legible. */
export const RADIO_PRECISION_MAX_M = 500;

/** 64-gon of radius `radioM` (clamped at 500 m) around the fix — the accuracy circle (S6). */
export function circuloPrecision(pt: LngLat, radioM: number): GeometriaGeoJSON {
  const radioAcotado = Math.min(
    Math.max(Number.isFinite(radioM) ? radioM : 0, 0),
    RADIO_PRECISION_MAX_M
  );
  const puntos: number[][] = [];
  const escala = escalaLon(pt[1]);
  for (let i = 0; i <= 64; i++) {
    const angulo = (i / 64) * 2 * Math.PI;
    puntos.push([
      pt[0] + (radioAcotado * Math.sin(angulo)) / escala,
      pt[1] + (radioAcotado * Math.cos(angulo)) / METROS_POR_GRADO_LAT,
    ]);
  }
  return { type: 'Polygon', coordinates: [puntos] };
}
