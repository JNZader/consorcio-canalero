export const CATEGORIAS = [
  { value: 'infraestructura', label: 'Infraestructura (canales, caminos, alcantarillas)' },
  { value: 'servicios', label: 'Servicios del consorcio' },
  { value: 'administrativo', label: 'Temas administrativos' },
  { value: 'ambiental', label: 'Medio ambiente' },
  { value: 'otro', label: 'Otro' },
];

export const NON_SPATIAL_CATEGORIES = ['administrativo', 'servicios'] as const;

export function isNonSpatialCategory(categoria: string | null | undefined): boolean {
  if (!categoria) return false;
  return (NON_SPATIAL_CATEGORIES as readonly string[]).includes(categoria);
}
