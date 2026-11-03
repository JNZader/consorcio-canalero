/**
 * Annual Sentinel-2 composites and JRC Global Surface Water tiles.
 * Both come from the operator GEE routes; the map only stores the tile.
 */

import type { SelectedImage } from '../../hooks/useSelectedImage';
import { apiFetch, GEE_TIMEOUT } from './core';

export const S2_YEAR_MIN = 2017;
export const JRC_YEAR_MIN = 1984;
export const JRC_YEAR_MAX = 2021;

export type TimeProduct = 's2' | 'jrc';

interface GeeTileBody {
  tile_url?: string;
  target_date?: string;
  visualization?: string;
  visualization_description?: string;
  collection?: string;
  images_count?: number;
  days_buffer?: number;
  max_cloud?: number | null;
  sensor?: string;
  mode?: 'scene' | 'composite';
}

export function yearOptions(product: TimeProduct, today = new Date()): number[] {
  const max = product === 's2' ? today.getFullYear() : JRC_YEAR_MAX;
  const min = product === 's2' ? S2_YEAR_MIN : JRC_YEAR_MIN;
  const years: number[] = [];
  for (let year = max; year >= min; year -= 1) years.push(year);
  return years;
}

function asSelectedImage(
  body: GeeTileBody,
  fallback: Omit<SelectedImage, 'tile_url'>
): SelectedImage {
  if (!body.tile_url) {
    throw new Error('No se pudo armar la imagen para ese año.');
  }
  return {
    ...fallback,
    tile_url: body.tile_url,
    target_date: body.target_date || fallback.target_date,
    visualization: body.visualization || fallback.visualization,
    visualization_description: body.visualization_description || fallback.visualization_description,
    collection: body.collection || fallback.collection,
    images_count: typeof body.images_count === 'number' ? body.images_count : fallback.images_count,
    days_buffer: typeof body.days_buffer === 'number' ? body.days_buffer : fallback.days_buffer,
    max_cloud: body.max_cloud === undefined ? fallback.max_cloud : body.max_cloud,
    selected_at: new Date().toISOString(),
  };
}

export const MONTHS_ES = [
  'Ene',
  'Feb',
  'Mar',
  'Abr',
  'May',
  'Jun',
  'Jul',
  'Ago',
  'Sep',
  'Oct',
  'Nov',
  'Dic',
] as const;

export function monthOptions(year: number, today = new Date()): number[] {
  const last = year < today.getFullYear() ? 12 : today.getMonth() + 1;
  const months: number[] = [];
  for (let month = 1; month <= last; month += 1) months.push(month);
  return months;
}

/** One XYZ tile around the consorcio, used as a date-selector thumbnail. */
export function tileThumbnailUrl(
  template: string,
  lon = -64.18,
  lat = -32.41,
  zoom = 11
): string | null {
  if (!template.includes('{z}') || !template.includes('{x}') || !template.includes('{y}')) {
    return null;
  }
  const n = 2 ** zoom;
  const x = Math.floor(((lon + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  );
  return template.replace('{z}', String(zoom)).replace('{x}', String(x)).replace('{y}', String(y));
}

export async function fetchMonthlySentinel(year: number, month: number): Promise<SelectedImage> {
  const body = await apiFetch<GeeTileBody>(
    `/geo/gee/images/sentinel2/monthly?year=${year}&month=${month}`,
    { timeout: GEE_TIMEOUT }
  );
  const mm = String(month).padStart(2, '0');
  return asSelectedImage(body, {
    target_date: `${year}-${mm}-15`,
    sensor: 'Sentinel-2',
    visualization: 'rgb',
    visualization_description: `Sentinel-2 ${MONTHS_ES[month - 1]} ${year}`,
    collection: 'COPERNICUS/S2_SR_HARMONIZED',
    images_count: 0,
    days_buffer: 14,
    max_cloud: 40,
    mode: 'composite',
    selected_at: new Date().toISOString(),
  });
}

export async function fetchAnnualSentinel(year: number): Promise<SelectedImage> {
  const body = await apiFetch<GeeTileBody>(`/geo/gee/images/sentinel2/annual?year=${year}`, {
    timeout: GEE_TIMEOUT,
  });
  return asSelectedImage(body, {
    target_date: `${year}-07-02`,
    sensor: 'Sentinel-2',
    visualization: 'rgb',
    visualization_description: `Sentinel-2 anual ${year}`,
    collection: 'COPERNICUS/S2_SR_HARMONIZED',
    images_count: 0,
    days_buffer: 182,
    max_cloud: 60,
    mode: 'composite',
    selected_at: new Date().toISOString(),
  });
}

export async function fetchJrcOccurrence(): Promise<SelectedImage> {
  const body = await apiFetch<GeeTileBody>('/geo/gee/layers/jrc-surface-water', {
    timeout: GEE_TIMEOUT,
  });
  return asSelectedImage(body, {
    target_date: `${JRC_YEAR_MAX}-01-01`,
    sensor: 'JRC',
    visualization: 'occurrence',
    visualization_description: 'Recurrencia histórica de agua superficial (JRC)',
    collection: 'JRC/GSW1_4/GlobalSurfaceWater',
    images_count: 1,
    days_buffer: 1,
    max_cloud: null,
    mode: 'composite',
    selected_at: new Date().toISOString(),
  });
}

export async function fetchJrcYear(year: number): Promise<SelectedImage> {
  const body = await apiFetch<GeeTileBody>(`/geo/gee/layers/jrc-surface-water/year?year=${year}`, {
    timeout: GEE_TIMEOUT,
  });
  return asSelectedImage(body, {
    target_date: `${year}-01-01`,
    sensor: 'JRC',
    visualization: 'waterClass',
    visualization_description: `Agua superficial JRC ${year}`,
    collection: 'JRC/GSW1_4/YearlyHistory',
    images_count: 1,
    days_buffer: 1,
    max_cloud: null,
    mode: 'composite',
    selected_at: new Date().toISOString(),
  });
}
