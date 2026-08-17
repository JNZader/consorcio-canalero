import { useMemo } from 'react';
import { useCanAccess } from '../stores/authStore';

/**
 * Reusable gate for the Multi-Hazard mode toggle.
 *
 * Returns `true` only when:
 * - the `VITE_FEATURE_MULTI_HAZARD_VIEWER` env var is truthy; AND
 * - the authenticated user has role `admin` or `operador`.
 *
 * The same predicate is used by the route validator, the toggle render, and the
 * URL-state hook so the gate cannot drift between code paths.
 */
export function useMultiHazardGate(): boolean {
  const canAccess = useCanAccess(['admin', 'operador']);

  return useMemo(() => {
    const raw = import.meta.env.VITE_FEATURE_MULTI_HAZARD_VIEWER;
    const flagEnabled = raw === 'true' || raw === true || raw === '1' || raw === 1;
    return flagEnabled && canAccess;
  }, [canAccess]);
}

/**
 * Predicate form for non-hook call sites (route validators, helpers).
 */
export function isMultiHazardGateOpen(role: string | null | undefined): boolean {
  if (role !== 'admin' && role !== 'operador') return false;
  const raw = import.meta.env.VITE_FEATURE_MULTI_HAZARD_VIEWER;
  return raw === 'true' || raw === true || raw === '1' || raw === 1;
}
