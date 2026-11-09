/**
 * One-shot hint so /admin/images → /mapa can open the right imagery mode.
 * MapaMapLibre consumes and clears this on mount/focus.
 */

export const MAP_PREFERRED_VIEW_KEY = 'consorcio_map_preferred_view';

export type MapPreferredView = 'single' | 'comparison';

export function setMapPreferredView(view: MapPreferredView): void {
  try {
    sessionStorage.setItem(MAP_PREFERRED_VIEW_KEY, view);
  } catch {
    // Private mode / quota — navigation still works; operator picks mode manually.
  }
}

export function consumeMapPreferredView(): MapPreferredView | null {
  try {
    const raw = sessionStorage.getItem(MAP_PREFERRED_VIEW_KEY);
    sessionStorage.removeItem(MAP_PREFERRED_VIEW_KEY);
    if (raw === 'single' || raw === 'comparison') return raw;
    return null;
  } catch {
    return null;
  }
}
