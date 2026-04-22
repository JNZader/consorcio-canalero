import type { AgendaItem, EntityOption } from './reunionesTypes';

export function normalizeArrayResponse<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }

  if (payload && typeof payload === 'object') {
    const wrapped = payload as Record<string, unknown>;
    const arrayLike = wrapped.items ?? wrapped.data ?? wrapped.results;

    if (Array.isArray(arrayLike)) {
      return arrayLike as T[];
    }
  }

  return [];
}

export function buildReferrableOptions(
  reports: Array<{ id: string; tipo: string; ubicacion_texto?: string }>,
  tramites: Array<{ id: string; titulo: string; numero_expediente?: string }>,
  assets: Array<{ id: string; nombre: string; tipo: string }>
): EntityOption[] {
  return [
    ...reports.map((report) => ({
      value: report.id,
      label: `${report.tipo.replace('_', ' ')} - ${report.ubicacion_texto || report.id.slice(0, 5)}`,
      group: 'Reportes',
      type: 'reporte',
    })),
    ...tramites.map((tramite) => ({
      value: tramite.id,
      label: `${tramite.titulo} (${tramite.numero_expediente || 'S/N'})`,
      group: 'Tramites',
      type: 'tramite',
    })),
    ...assets.map((asset) => ({
      value: asset.id,
      label: `${asset.nombre} (${asset.tipo})`,
      group: 'Infraestructura',
      type: 'infraestructura',
    })),
  ];
}

export function buildAgendaReferences(referencias: string[], availableEntities: EntityOption[]) {
  return referencias.map((id) => {
    const entity = availableEntities.find((option) => option.value === id);
    return {
      entidad_id: id,
      entidad_tipo: entity?.type || 'otro',
      metadata: { label: entity?.label },
    };
  });
}

export function getAgendaReferenceColor(entidadTipo: string) {
  if (entidadTipo === 'reporte') return 'red';
  if (entidadTipo === 'tramite') return 'blue';
  if (entidadTipo === 'infraestructura') return 'green';
  return 'gray';
}

export function hasAgendaItems(items?: string[]) {
  return Boolean(items && items.length > 0);
}

export function buildAgendaTopicPayload(
  values: { titulo: string; descripcion: string; referencias: string[] },
  agenda: AgendaItem[],
  availableEntities: EntityOption[]
) {
  return {
    titulo: values.titulo,
    descripcion: values.descripcion,
    orden: agenda.length + 1,
    referencias: buildAgendaReferences(values.referencias, availableEntities),
  };
}
