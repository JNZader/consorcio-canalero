import { getRouteApi, useNavigate, useRouter } from '@tanstack/react-router';
import { useCallback, useEffect, useMemo } from 'react';
import { useCanAccess } from '../stores/authStore';

export const RISK_CLASS_LABELS = ['Bajo', 'Medio', 'Alto', 'Crítico'] as const;
export type RiskClass = (typeof RISK_CLASS_LABELS)[number];

export type PrecipMonth = 'anual' | '01' | '02' | '03' | '04' | '05' | '06' | '07' | '08' | '09' | '10' | '11' | '12';

const VALID_RISK_CLASSES = new Set<string>(RISK_CLASS_LABELS);
const VALID_PRECIP_MONTHS = new Set<PrecipMonth>([
  'anual',
  '01',
  '02',
  '03',
  '04',
  '05',
  '06',
  '07',
  '08',
  '09',
  '10',
  '11',
  '12',
]);

const routeApi = getRouteApi('/mapa');

export interface HazardUrlState {
  /** Whether hazard mode is requested in the URL. */
  hazard: boolean;
  /** Resolved active state after gating. */
  isHazardActive: boolean;
  /** Selected basin id or null when showing all basins. */
  basin: string | null;
  /** Active risk-class labels. */
  riskClasses: RiskClass[];
  /** Selected CHIRPS normals month. */
  precipMonth: PrecipMonth;
  /** Turn hazard mode on/off. */
  setHazard: (on: boolean) => void;
  /** Select a basin id or clear it with null. */
  setBasin: (id: string | null) => void;
  /** Replace the active risk-class set. */
  setRiskClasses: (classes: RiskClass[]) => void;
  /** Select a precipitation month. */
  setPrecipMonth: (month: PrecipMonth) => void;
  /** Reset to canonical defaults: hazard on, all risk classes, no basin, anual. */
  resetToDefaults: () => void;
}

/** Canonical hazard default layer stack. */
export const HAZARD_DEFAULT_LAYERS = [
  'flood_risk',
  'drainage_need',
  'soil',
  'canales_relevados',
  'basins',
  'precip_normal',
] as const;

/** Default risk classes shown when hazard mode is active. */
export const HAZARD_DEFAULT_RISK_CLASSES: RiskClass[] = [...RISK_CLASS_LABELS];

/** Default precipitation normal month. */
export const HAZARD_DEFAULT_PRECIP_MONTH: PrecipMonth = 'anual';

/**
 * Read/write Multi-Hazard mode URL state on `/mapa`.
 *
 * Responsibilities:
 * - Parses and validates hazard, basin, riskClasses and precipMonth.
 * - Filters unknown basin/risk-class values (callers must still validate basin
 *   ids against the live basin catalog).
 * - Treats `hazard=1` as `false` when the user lacks the role/flag gate.
 */
export function useHazardUrlState(): HazardUrlState {
  const router = useRouter({ warn: false });
  const canAccessHazard = useCanAccess(['admin', 'operador']);

  const featureFlagEnabled = useMemo(() => {
    const raw = import.meta.env.VITE_FEATURE_MULTI_HAZARD_VIEWER;
    return raw === 'true' || raw === true || raw === '1' || raw === 1;
  }, []);

  const gateOpen = featureFlagEnabled && canAccessHazard;

  // Tests and storybook may render components that consume this hook without a
  // TanStack Router provider. Fall back to sensible defaults and no-op setters
  // instead of crashing.
  if (!router) {
    return {
      hazard: false,
      isHazardActive: false,
      basin: null,
      riskClasses: [],
      precipMonth: HAZARD_DEFAULT_PRECIP_MONTH,
      setHazard: () => {},
      setBasin: () => {},
      setRiskClasses: () => {},
      setPrecipMonth: () => {},
      resetToDefaults: () => {},
    };
  }

  const search = routeApi.useSearch();
  const navigate = useNavigate({ from: '/mapa' });

  const rawHazard = search.hazard === true;
  const isHazardActive = gateOpen && rawHazard;

  const basin =
    typeof search.basin === 'string' && search.basin.trim() !== ''
      ? search.basin.trim()
      : null;

  const riskClasses = useMemo<RiskClass[]>(() => {
    if (!isHazardActive) return [];
    const input = search.riskClasses ?? HAZARD_DEFAULT_RISK_CLASSES;
    const raw = Array.isArray(input) ? input : String(input).split(/[,;]/);
    return raw
      .map((c) => String(c).trim())
      .filter((c): c is RiskClass => VALID_RISK_CLASSES.has(c));
  }, [isHazardActive, search.riskClasses]);

  const precipMonth =
    search.precipMonth && VALID_PRECIP_MONTHS.has(search.precipMonth as PrecipMonth)
      ? (search.precipMonth as PrecipMonth)
      : HAZARD_DEFAULT_PRECIP_MONTH;

  const writeSearch = useCallback(
    (next: Partial<ReturnType<typeof routeApi.useSearch>>) => {
      navigate({
        search: (prev) => ({
          ...prev,
          ...next,
        }),
        replace: true,
      });
    },
    [navigate]
  );

  // Role/flag gate: if hazard mode is requested in the URL but the gate is
  // closed (citizen, feature flag off, etc.), drop the param so the URL stays
  // clean and shared links never advertise a gated mode.
  useEffect(() => {
    if (rawHazard && !gateOpen) {
      writeSearch({ hazard: false });
    }
  }, [rawHazard, gateOpen, writeSearch]);

  const setHazard = useCallback(
    (on: boolean) => {
      if (!gateOpen) {
        // Gate failed: drop the hazard param so the URL stays clean.
        writeSearch({ hazard: false });
        return;
      }
      writeSearch({ hazard: on });
    },
    [gateOpen, writeSearch]
  );

  const setBasin = useCallback(
    (id: string | null) => {
      writeSearch({ basin: id ?? undefined });
    },
    [writeSearch]
  );

  const setRiskClasses = useCallback(
    (classes: RiskClass[]) => {
      writeSearch({ riskClasses: classes.length > 0 ? classes : undefined });
    },
    [writeSearch]
  );

  const setPrecipMonth = useCallback(
    (month: PrecipMonth) => {
      writeSearch({ precipMonth: month });
    },
    [writeSearch]
  );

  const resetToDefaults = useCallback(() => {
    writeSearch({
      hazard: !!gateOpen,
      basin: undefined,
      riskClasses: HAZARD_DEFAULT_RISK_CLASSES,
      precipMonth: HAZARD_DEFAULT_PRECIP_MONTH,
      layers: undefined,
    });
  }, [gateOpen, writeSearch]);

  return {
    hazard: rawHazard,
    isHazardActive,
    basin,
    riskClasses,
    precipMonth,
    setHazard,
    setBasin,
    setRiskClasses,
    setPrecipMonth,
    resetToDefaults,
  };
}
