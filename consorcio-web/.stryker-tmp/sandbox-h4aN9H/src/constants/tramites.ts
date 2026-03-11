// @ts-nocheck
export const TRAMITE_ESTADOS_CANONICOS = [
  'pendiente',
  'en_revision',
  'aprobado',
  'rechazado',
  'completado',
] as const;

export type TramiteEstadoCanonico = (typeof TRAMITE_ESTADOS_CANONICOS)[number];

export const TRAMITE_ESTADOS_SET = new Set<string>(TRAMITE_ESTADOS_CANONICOS);

export function isCanonicalTramiteEstado(value: string): value is TramiteEstadoCanonico {
  return TRAMITE_ESTADOS_SET.has(value);
}

export function formatTramiteEstado(estado: TramiteEstadoCanonico): string {
  return estado.replace('_', ' ').toUpperCase();
}
