/**
 * Whitelist de `sort` para las bandejas de administración (issue #698).
 *
 * El backend (`order_clause` en `gee-backend/app/shared/list_sort.py`)
 * rechaza con 400 cualquier `sort` fuera del mapa de columnas de cada
 * dominio. Una URL compartida con un `sort` viejo o inexistente dejaba
 * la bandeja en error permanente y "Reintentar" re-enviaba el mismo
 * valor. Igual que `order`, un `sort` desconocido ahora cae en el
 * default del panel y nunca llega a la API.
 *
 * Los sets NO son intercambiables entre bandejas: denuncias ordena por
 * `tipo` y sugerencias por `categoria`. Cada lista debe reflejar lo que
 * el panel ofrece en UI (Select "Ordenar" + headers sorteables) y lo que
 * acepta el backend: ver `ReportsFilters`/`ReportsTableContent` y
 * `SugerenciasFilters`/`SugerenciasTableContent`.
 */
export const REPORTS_SORT_KEYS = ['created_at', 'estado', 'tipo'] as const;

export const SUGERENCIAS_SORT_KEYS = ['created_at', 'estado', 'categoria'] as const;

/** Default compartido por ambas bandejas: las más recientes primero. */
export const DEFAULT_BANDEJA_SORT = 'created_at';

/**
 * Devuelve el `sort` de la URL solo si está en la whitelist de la
 * bandeja; si no (ausente, vacío o inválido), el default del panel.
 */
export function resolveBandejaSort(
  value: string | null,
  allowed: readonly string[],
  fallback: string = DEFAULT_BANDEJA_SORT
): string {
  return value && allowed.includes(value) ? value : fallback;
}
