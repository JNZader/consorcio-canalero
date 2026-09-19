/**
 * Staff map pins API client.
 *
 * Mirrors `gee-backend/app/domains/geo/puntos_interes/router.py`
 * (`/api/v2/geo/puntos-interes`), an operator-only route
 * (`require_admin_or_operator`). Not a denuncia, not a survey, not public.
 */

import type { Feature, FeatureCollection, Point } from 'geojson';

import { apiFetch } from './core';

export const PUNTO_INTERES_TIPOS = {
  ALCANTARILLA: 'alcantarilla',
  ALTEO: 'alteo',
  TAPONAMIENTO: 'taponamiento',
  OTRO: 'otro',
} as const;

export type PuntoInteresTipo = (typeof PUNTO_INTERES_TIPOS)[keyof typeof PUNTO_INTERES_TIPOS];

export const PUNTO_INTERES_TIPO_LABELS = {
  [PUNTO_INTERES_TIPOS.ALCANTARILLA]: 'Alcantarilla',
  [PUNTO_INTERES_TIPOS.ALTEO]: 'Alteo',
  [PUNTO_INTERES_TIPOS.TAPONAMIENTO]: 'Taponamiento',
  [PUNTO_INTERES_TIPOS.OTRO]: 'Otro',
} as const;

export interface PuntoInteresProperties {
  readonly id: string;
  readonly titulo: string;
  readonly nota: string | null;
  readonly tipo: PuntoInteresTipo;
}

export type PuntoInteresFeature = Feature<Point, PuntoInteresProperties>;
export type PuntoInteresCollection = FeatureCollection<Point, PuntoInteresProperties>;

export interface PuntoInteresCreateBody {
  readonly lng: number;
  readonly lat: number;
  readonly titulo: string;
  readonly nota?: string | null;
  readonly tipo: PuntoInteresTipo;
}

const ENDPOINT = '/geo/puntos-interes';

export async function fetchPuntosInteres(signal?: AbortSignal): Promise<PuntoInteresCollection> {
  return apiFetch<PuntoInteresCollection>(ENDPOINT, { signal });
}

export async function createPuntoInteres(
  body: PuntoInteresCreateBody,
  signal?: AbortSignal
): Promise<PuntoInteresFeature> {
  return apiFetch<PuntoInteresFeature>(ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
}

export async function deletePuntoInteres(id: string, signal?: AbortSignal): Promise<void> {
  await apiFetch<void>(`${ENDPOINT}/${id}`, { method: 'DELETE', signal });
}
