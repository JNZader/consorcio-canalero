import type { Feature, GeoJsonProperties, Geometry } from 'geojson';
import type { IndexFile } from '../../types/canales';

export interface CanalSearchHit {
  id: string;
  nombre: string;
  codigo: string | null;
  estado: 'relevado' | 'propuesto';
}

export interface ParcelSearchHit {
  key: string;
  label: string;
  detail: string;
  feature: Feature<Geometry, GeoJsonProperties>;
}

const CANAL_MIN = 2;
const PARCEL_MIN = 3;
const RESULT_LIMIT = 8;

function fold(value: string): string {
  return value.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim();
}

function textProp(props: GeoJsonProperties, keys: readonly string[]): string {
  if (!props) return '';
  const record = props as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  }
  return '';
}

export function searchCanales(
  index: IndexFile | null | undefined,
  query: string
): CanalSearchHit[] {
  const needle = fold(query);
  if (needle.length < CANAL_MIN || !index) return [];
  const rows: CanalSearchHit[] = [
    ...index.relevados.map((row) => ({
      id: row.id,
      nombre: row.nombre,
      codigo: row.codigo,
      estado: 'relevado' as const,
    })),
    ...index.propuestas.map((row) => ({
      id: row.id,
      nombre: row.nombre,
      codigo: row.codigo,
      estado: 'propuesto' as const,
    })),
  ];
  return rows
    .filter((row) => {
      const haystack = [row.nombre, row.codigo ?? '', row.id].map(fold);
      return haystack.some((value) => value.includes(needle));
    })
    .slice(0, RESULT_LIMIT);
}

export function searchParcelas(
  features: readonly Feature<Geometry, GeoJsonProperties>[] | null | undefined,
  query: string
): ParcelSearchHit[] {
  const needle = fold(query);
  if (needle.length < PARCEL_MIN || !features) return [];
  const hits: ParcelSearchHit[] = [];
  for (const feature of features) {
    const cuenta = textProp(feature.properties, ['Nro_Cuenta', 'nro_cuenta', 'cuenta']);
    const nomenclatura = textProp(feature.properties, ['Nomenclatura', 'nomenclatura']);
    const designacion = textProp(feature.properties, ['desig_oficial', 'Desig_Oficial']);
    const matched = [cuenta, nomenclatura, designacion].some((value) =>
      fold(value).includes(needle)
    );
    if (!matched) continue;
    const label = cuenta || nomenclatura || designacion;
    hits.push({
      key: `${label}:${hits.length}`,
      label,
      detail: designacion && designacion !== label ? designacion : nomenclatura,
      feature,
    });
    if (hits.length >= RESULT_LIMIT) break;
  }
  return hits;
}
