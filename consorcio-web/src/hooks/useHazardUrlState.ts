import { useNavigate, useSearch } from '@tanstack/react-router';
import { useEffect } from 'react';

import { useAuthLoading } from '../stores/authStore';
import { useMultiHazardGate } from './useMultiHazardGate';

export const HAZARD_RISK_CLASSES = ['Bajo', 'Medio', 'Alto', 'Crítico'] as const;
export const HAZARD_PRECIP_MONTHS = [
  '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
] as const;
export const HAZARD_DEFAULT_PRECIP_MONTH = 'anual';

export type HazardRiskClass = (typeof HAZARD_RISK_CLASSES)[number];
export type HazardPrecipMonth = (typeof HAZARD_PRECIP_MONTHS)[number] | typeof HAZARD_DEFAULT_PRECIP_MONTH;

export interface HazardSearchInput {
  hazard?: unknown;
  basin?: unknown;
  riskClasses?: unknown;
  precipMonth?: unknown;
}

export interface HazardUrlState {
  hazard: boolean;
  basin: string | null;
  riskClasses: HazardRiskClass[];
  precipMonth: HazardPrecipMonth;
}

export const BASIN_CATALOG_STATUS = {
  LOADING: 'loading',
  READY: 'ready',
  ERROR: 'error',
} as const;

export type BasinCatalogStatus = (typeof BASIN_CATALOG_STATUS)[keyof typeof BASIN_CATALOG_STATUS];

export interface BasinCatalogStatusInput {
  loading: boolean;
  error: string | null;
  /** False while TanStack Query has no catalog payload yet (including paused pending). */
  hasData?: boolean;
}

export interface HazardUrlStateOptions {
  gateOpen: boolean;
  basinIds?: readonly string[];
  basinCatalogStatus?: BasinCatalogStatus;
}

export function resolveBasinCatalogStatus({
  loading,
  error,
  hasData = true,
}: BasinCatalogStatusInput): BasinCatalogStatus {
  if (loading) return BASIN_CATALOG_STATUS.LOADING;
  if (error) return BASIN_CATALOG_STATUS.ERROR;
  if (!hasData) return BASIN_CATALOG_STATUS.LOADING;
  return BASIN_CATALOG_STATUS.READY;
}

const DEFAULT_HAZARD_URL_STATE: HazardUrlState = {
  hazard: false,
  basin: null,
  riskClasses: [...HAZARD_RISK_CLASSES],
  precipMonth: HAZARD_DEFAULT_PRECIP_MONTH,
};

function normalizeRiskClass(value: unknown): HazardRiskClass | undefined {
  if (typeof value !== 'string') return undefined;
  const normalized = value.trim().normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  return HAZARD_RISK_CLASSES.find(
    (riskClass) => riskClass.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase() === normalized
  );
}

function riskClassValues(value: unknown): unknown[] {
  if (Array.isArray(value)) return value.flatMap((entry) => riskClassValues(entry));
  return typeof value === 'string' ? value.split(',') : [];
}

function normalizeRiskClasses(value: unknown): HazardRiskClass[] {
  const result = riskClassValues(value)
    .map(normalizeRiskClass)
    .filter((riskClass): riskClass is HazardRiskClass => riskClass !== undefined);
  const unique = new Set(result);
  return HAZARD_RISK_CLASSES.filter((riskClass) => unique.has(riskClass));
}

function isBasinCatalogResolved(
  catalogStatus: BasinCatalogStatus | undefined,
  basinIds: readonly string[] | undefined
): boolean {
  if (catalogStatus === BASIN_CATALOG_STATUS.LOADING) return false;
  if (catalogStatus === BASIN_CATALOG_STATUS.ERROR) return false;
  if (catalogStatus === BASIN_CATALOG_STATUS.READY) return true;
  return basinIds !== undefined;
}

function normalizeBasin(
  value: unknown,
  basinIds: readonly string[] | undefined,
  catalogStatus: BasinCatalogStatus | undefined
): string | null {
  if (typeof value !== 'string' || value.trim() === '') return null;
  const basin = value.trim();
  if (!isBasinCatalogResolved(catalogStatus, basinIds)) return basin;
  return basinIds?.includes(basin) ? basin : null;
}

function normalizePrecipMonth(value: unknown): HazardPrecipMonth {
  if (typeof value !== 'string') return HAZARD_DEFAULT_PRECIP_MONTH;
  const normalized = value.trim().toLowerCase();
  if (normalized === HAZARD_DEFAULT_PRECIP_MONTH) return HAZARD_DEFAULT_PRECIP_MONTH;
  return HAZARD_PRECIP_MONTHS.includes(normalized as (typeof HAZARD_PRECIP_MONTHS)[number])
    ? (normalized as HazardPrecipMonth)
    : HAZARD_DEFAULT_PRECIP_MONTH;
}

function isHazardRequested(value: unknown): boolean {
  return value === true || value === '1' || value === 'true';
}

export function parseHazardUrlState(
  search: HazardSearchInput,
  { gateOpen, basinIds, basinCatalogStatus }: HazardUrlStateOptions
): HazardUrlState {
  if (!gateOpen || !isHazardRequested(search.hazard)) return { ...DEFAULT_HAZARD_URL_STATE };

  const riskClasses = normalizeRiskClasses(search.riskClasses);
  return {
    hazard: true,
    basin: normalizeBasin(search.basin, basinIds, basinCatalogStatus),
    riskClasses: riskClasses.length > 0 ? riskClasses : [...HAZARD_RISK_CLASSES],
    precipMonth: normalizePrecipMonth(search.precipMonth),
  };
}

function hasAllRiskClasses(riskClasses: readonly HazardRiskClass[]): boolean {
  return riskClasses.length === HAZARD_RISK_CLASSES.length && HAZARD_RISK_CLASSES.every((item) => riskClasses.includes(item));
}

export function toHazardSearch(state: HazardUrlState, gateOpen: boolean): Record<string, string> {
  if (!gateOpen || !state.hazard) return {};
  return {
    hazard: '1',
    ...(state.basin ? { basin: state.basin } : {}),
    ...(!hasAllRiskClasses(state.riskClasses) ? { riskClasses: state.riskClasses.join(',') } : {}),
    ...(state.precipMonth !== HAZARD_DEFAULT_PRECIP_MONTH ? { precipMonth: state.precipMonth } : {}),
  };
}

function sameSearch(left: HazardSearchInput, right: Record<string, string>): boolean {
  const leftEntries = Object.entries(left)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => [key, Array.isArray(value) ? value.join(',') : String(value)] as const)
    .sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey));
  const rightEntries = Object.entries(right).sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey));
  return JSON.stringify(leftEntries) === JSON.stringify(rightEntries);
}

export interface UseHazardUrlStateOptions {
  basinIds?: readonly string[];
  basinCatalogStatus?: BasinCatalogStatus;
}

export function useHazardUrlState({ basinIds, basinCatalogStatus }: UseHazardUrlStateOptions = {}) {
  const gateOpen = useMultiHazardGate();
  const authPending = useAuthLoading();
  const navigate = useNavigate();
  const search = useSearch({ from: '/mapa' });
  const state = parseHazardUrlState(search, { gateOpen, basinIds, basinCatalogStatus });
  const canonicalSearch = toHazardSearch(state, gateOpen);

  useEffect(() => {
    if (authPending) return;
    if (!sameSearch(search, canonicalSearch)) {
      void navigate({ to: '/mapa', search: canonicalSearch, replace: true });
    }
  }, [authPending, canonicalSearch, navigate, search]);

  const update = (patch: HazardSearchInput) => {
    const nextState = parseHazardUrlState(
      { ...search, ...patch },
      { gateOpen, basinIds, basinCatalogStatus }
    );
    void navigate({ to: '/mapa', search: toHazardSearch(nextState, gateOpen) });
  };

  return {
    ...state,
    setHazard: (hazard: boolean) => update({ hazard: hazard ? '1' : undefined }),
    setBasin: (basin: string | null) => update({ basin }),
    setRiskClasses: (riskClasses: readonly HazardRiskClass[]) => update({ riskClasses: [...riskClasses] }),
    setPrecipMonth: (precipMonth: HazardPrecipMonth) => update({ precipMonth }),
    resetToDefaults: () => update({ basin: undefined, riskClasses: undefined, precipMonth: undefined }),
  };
}
