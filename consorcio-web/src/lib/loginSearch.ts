export interface LoginSearch {
  modo?: 'registro';
}

/** Conserva `?modo=registro` y descarta el resto del search de /login. */
export function parseLoginSearch(search: Record<string, unknown>): LoginSearch {
  return search.modo === 'registro' ? { modo: 'registro' } : {};
}
