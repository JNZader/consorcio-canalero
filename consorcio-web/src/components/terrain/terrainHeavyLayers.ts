/** UX PDF T6 — catastro and soils are the expensive 3D vector fills. */
export const HEAVY_3D_LAYER_IDS = ['catastro', 'soil'] as const;

export const HEAVY_3D_WARNING = 'Esto puede ir lento en 3D';

export function heavy3dWarning(visibility: Record<string, boolean>): string | null {
  const on = HEAVY_3D_LAYER_IDS.some((id) => visibility[id]);
  return on ? HEAVY_3D_WARNING : null;
}

export function heavy3dLoadLines(params: {
  catastroOn: boolean;
  catastroLoading: boolean;
  catastroError: string | null;
  soilOn: boolean;
  soilLoading: boolean;
  soilError: string | null;
}): { loading: string[]; errors: string[] } {
  const loading: string[] = [];
  const errors: string[] = [];
  if (params.catastroOn && params.catastroLoading) loading.push('Cargando catastro…');
  if (params.soilOn && params.soilLoading) loading.push('Cargando suelos…');
  if (params.catastroOn && params.catastroError) errors.push('Catastro: no se pudo cargar');
  if (params.soilOn && params.soilError) errors.push('Suelos: no se pudo cargar');
  return { loading, errors };
}
