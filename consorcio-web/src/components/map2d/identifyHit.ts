export const IDENTIFY_HIT_RADIUS_FINE_PX = 6;
export const IDENTIFY_HIT_RADIUS_COARSE_PX = 10;

export function identifyHitRadiusPx(pointerCoarse: boolean): number {
  return pointerCoarse ? IDENTIFY_HIT_RADIUS_COARSE_PX : IDENTIFY_HIT_RADIUS_FINE_PX;
}

export function identifyHitBbox(
  x: number,
  y: number,
  radius: number,
): [[number, number], [number, number]] {
  return [
    [x - radius, y - radius],
    [x + radius, y + radius],
  ];
}

export function pointerIsCoarse(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia('(pointer: coarse)').matches;
}
