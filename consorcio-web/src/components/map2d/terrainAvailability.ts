export type TerrainAvailability = 'loading' | 'ready' | 'error' | 'empty';

export function resolveTerrainAvailability(input: {
  loading: boolean;
  error: string | null;
  hasDemRaw: boolean;
}): TerrainAvailability {
  if (input.loading) return 'loading';
  if (input.error) return 'error';
  if (input.hasDemRaw) return 'ready';
  return 'empty';
}

export function terrainAvailabilityHint(status: TerrainAvailability): string {
  switch (status) {
    case 'loading':
      return 'Cargando relieve…';
    case 'error':
      return 'No pudimos cargar el relieve.';
    case 'empty':
      return 'Sin capa DEM — ejecutá el pipeline de terreno primero.';
    default:
      return 'Vista 3D del terreno (MapLibre)';
  }
}
