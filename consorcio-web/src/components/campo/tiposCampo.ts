/**
 * Campo (PR 6, S5/S6) — types of the offline field package + neutral copy.
 *
 * The package is the JSON the backend serves at
 * `GET /api/v2/public/campo/{token}` (mirrors
 * `gee-backend/.../informe_area/service.py::construir_paquete_campo`).
 *
 * Copy rule (PR 5's S11): the panel NEVER renders per-class producer
 * phrases ("sector bajo…", agronomic advice). Classes are shown neutral —
 * "clase Alto" — because those phrases are gated behind validation work
 * this PR does not include.
 */

export interface GeometriaGeoJSON {
  type: 'Polygon' | 'MultiPolygon' | string;
  coordinates: unknown;
}

export interface ClaseCampo {
  clase: string;
  color: string;
  geometrias: GeometriaGeoJSON[];
}

export interface TemaCampo {
  titulo: string;
  clases: ClaseCampo[];
}

export interface SubcuencaCampo {
  nombre: string;
  geometry: GeometriaGeoJSON;
}

export interface BasemapCampo {
  imagen: string; // data:image/png;base64,...
  bounds: [number, number, number, number]; // [w, s, e, n]
  fecha?: string | null;
  sensor?: string | null;
  descripcion?: string;
}

export interface PaqueteCampo {
  version: number;
  nombre: string;
  generado_el: string;
  vence_at?: string;
  area_ha: number;
  limites: { seleccion: GeometriaGeoJSON; subcuencas: SubcuencaCampo[] };
  temas: Record<string, TemaCampo>;
  basemap: BasemapCampo | null;
  notas: string[];
}

/** Short neutral labels for the theme chips (S6). */
export const TITULOS_TEMAS: Record<string, string> = {
  riesgo: 'Riesgo',
  drenaje: 'Drenaje',
  suelos: 'Suelos',
};

export function tituloTema(clave: string, paquete: PaqueteCampo): string {
  return TITULOS_TEMAS[clave] ?? paquete.temas[clave]?.titulo ?? clave;
}

/** The bottom panel's GPS line — neutral class copy only (no S11 phrases). */
export function frasePosicion(clase: string | null): string {
  return clase ? `Tu posición: clase ${clase}` : 'Fuera del área del informe';
}

/** The boundary warning (S6): "Estás en el límite entre Medio y Alto". */
export function fraseLimite(actual: string, vecino: string): string {
  return `Estás en el límite entre ${actual} y ${vecino}`;
}

/** Offline chip (S6): "Sin señal · funciona igual". */
export const FRASE_SIN_SENAL = 'Sin señal · funciona igual';
