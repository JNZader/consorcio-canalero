/** UX-28: finishing dblclick must not zoom or open identify. */

export const MEASUREMENT_IDENTIFY_GUARD_MS = 300;

let blockedUntil = 0;

export function armMeasurementIdentifyGuard(now = Date.now()): void {
  blockedUntil = now + MEASUREMENT_IDENTIFY_GUARD_MS;
}

export function isMeasurementIdentifyBlocked(now = Date.now()): boolean {
  return now < blockedUntil;
}

export function resetMeasurementIdentifyGuard(): void {
  blockedUntil = 0;
}
