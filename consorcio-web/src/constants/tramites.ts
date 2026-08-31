export const TRAMITE_ESTADOS_CANONICOS = [
  'ingresado',
  'en_tramite',
  'aprobado',
  'rechazado',
  'archivado',
] as const;

export type TramiteEstadoCanonico = (typeof TRAMITE_ESTADOS_CANONICOS)[number];

export const TRAMITE_ESTADOS_SET = new Set<string>(TRAMITE_ESTADOS_CANONICOS);

export const TRAMITE_ESTADO_LABELS = {
  ingresado: 'Ingresado',
  en_tramite: 'En trámite',
  aprobado: 'Aprobado',
  rechazado: 'Rechazado',
  archivado: 'Archivado',
} as const satisfies Record<TramiteEstadoCanonico, string>;

const UNKNOWN_TRAMITE_ESTADO_LABEL = 'Estado desconocido';

export function isCanonicalTramiteEstado(value: string): value is TramiteEstadoCanonico {
  return TRAMITE_ESTADOS_SET.has(value);
}

export function formatTramiteEstado(estado: string): string {
  if (isCanonicalTramiteEstado(estado)) {
    return TRAMITE_ESTADO_LABELS[estado];
  }

  const trimmed = estado.trim();
  return trimmed.length > 0 ? trimmed : UNKNOWN_TRAMITE_ESTADO_LABEL;
}
