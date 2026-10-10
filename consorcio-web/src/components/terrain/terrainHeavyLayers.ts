/** UX PDF T6 — catastro and soils are the expensive 3D vector fills. */
export const HEAVY_3D_LAYER_IDS = ['catastro', 'soil'] as const;

export const HEAVY_3D_WARNING = 'Esto puede ir lento en 3D';

export function heavy3dWarning(visibility: Record<string, boolean>): string | null {
  const on = HEAVY_3D_LAYER_IDS.some((id) => visibility[id]);
  return on ? HEAVY_3D_WARNING : null;
}
