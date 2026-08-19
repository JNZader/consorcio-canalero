import { useAuthStore } from '../stores/authStore';

export const MULTI_HAZARD_ALLOWED_ROLES = ['admin', 'operador'] as const;

export type MultiHazardAllowedRole = (typeof MULTI_HAZARD_ALLOWED_ROLES)[number];

function isFeatureEnabled(value: unknown): boolean {
  return value === true || value === 'true' || value === '1';
}

export function canUseMultiHazardViewer(featureFlag: unknown, role: unknown): boolean {
  return isFeatureEnabled(featureFlag) && MULTI_HAZARD_ALLOWED_ROLES.includes(role as MultiHazardAllowedRole);
}

/** Returns whether the current user may activate the operator-only hazard viewer. */
export function useMultiHazardGate(): boolean {
  const role = useAuthStore((state) => state.profile?.rol);
  return canUseMultiHazardViewer(import.meta.env.VITE_FEATURE_MULTI_HAZARD_VIEWER, role);
}
