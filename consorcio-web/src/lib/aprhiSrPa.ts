import type { Feature, FeatureCollection, LineString, MultiLineString } from 'geojson';

export const APRHI_SR_PA_URL = '/capas/aprhi_sr_pa.geojson';
export const SR_PA_KIND = 'sr_pa' as const;
export const SR_PA_ID_PREFIX = 'srpa:';

export interface SrPaListRow {
  readonly kind: typeof SR_PA_KIND;
  readonly id: string;
  readonly identificador: string;
  readonly nombre: string;
  readonly estado: string;
  readonly tipo: string;
  readonly publicado: boolean;
}

function readText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

export function srPaFeatureId(properties: Record<string, unknown> | null | undefined): string {
  const identificador = readText(properties?.Identificador);
  if (identificador) return `${SR_PA_ID_PREFIX}${identificador}`;
  const objectId = readText(properties?.OBJECTID) || readText(properties?.id);
  return `${SR_PA_ID_PREFIX}${objectId || 'sin-id'}`;
}

export function isSrPaListId(id: string | null | undefined): boolean {
  return typeof id === 'string' && id.startsWith(SR_PA_ID_PREFIX);
}

function isLineGeometry(geometry: Feature['geometry']): geometry is LineString | MultiLineString {
  return geometry?.type === 'LineString' || geometry?.type === 'MultiLineString';
}

export function parseSrPaRows(collection: FeatureCollection): SrPaListRow[] {
  const rows: SrPaListRow[] = [];
  for (const feature of collection.features) {
    if (!isLineGeometry(feature.geometry)) continue;
    const properties = (feature.properties ?? {}) as Record<string, unknown>;
    const identificador = readText(properties.Identificador);
    const nombre =
      readText(properties.Nombre_Obra) ||
      readText(properties.nombre_publico) ||
      identificador ||
      'Obra sin nombre';
    rows.push({
      kind: SR_PA_KIND,
      id: srPaFeatureId(properties),
      identificador,
      nombre,
      estado: readText(properties.Estado_Registro) || 's/estado',
      tipo: readText(properties.Tipo_Obra_Lineal) || 's/tipo',
      publicado: properties.publicado === true,
    });
  }
  return rows.sort((left, right) => {
    const estado = left.estado.localeCompare(right.estado, 'es');
    if (estado !== 0) {
      if (left.estado === 'Vigente') return -1;
      if (right.estado === 'Vigente') return 1;
      return estado;
    }
    return (left.identificador || left.nombre).localeCompare(
      right.identificador || right.nombre,
      'es'
    );
  });
}

export function tagSrPaListIds(collection: FeatureCollection): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: collection.features.map((feature) => {
      const listId = srPaFeatureId((feature.properties ?? {}) as Record<string, unknown>);
      return {
        ...feature,
        id: listId,
        properties: {
          ...(feature.properties ?? {}),
          id: listId,
          list_id: listId,
        },
      };
    }),
  };
}

export function srPaFeatureById(
  collection: FeatureCollection,
  id: string
): Feature<LineString | MultiLineString> | undefined {
  return collection.features.find((feature) => {
    if (!isLineGeometry(feature.geometry)) return false;
    return srPaFeatureId((feature.properties ?? {}) as Record<string, unknown>) === id;
  }) as Feature<LineString | MultiLineString> | undefined;
}
