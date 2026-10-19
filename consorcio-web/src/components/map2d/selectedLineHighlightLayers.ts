/**
 * The selection highlight owns the top of the line stack.
 *
 * A selected line is painted orange over a dark casing by
 * `useSelectedLineHighlight`. That only reads as "selected" while nothing else
 * is raised above it — so every hoisting pass (canales, Pilar Verde) must insert
 * BELOW `SELECTED_LINE_CASING` instead of calling `moveLayer(id)` with no
 * `beforeId`. Raising canales to the very top is what made a selected canal look
 * unselected while a selected road (hoisted with a `beforeId`) still showed.
 */
export const SELECTED_LINE_SOURCE = 'map2d-selected-lines';
export const SELECTED_LINE_CASING = 'map2d-selected-lines-casing';
export const SELECTED_LINE_LAYER = 'map2d-selected-lines-line';

/**
 * Raise the highlight to the top: casing first, then the orange stroke, so the
 * stroke ends above its own casing. Idempotent and safe to call after every
 * sync pass.
 */
export function hoistSelectedLineHighlight(map: {
  getLayer: (id: string) => unknown;
  moveLayer: (id: string, beforeId?: string) => void;
}): void {
  for (const id of [SELECTED_LINE_CASING, SELECTED_LINE_LAYER]) {
    if (!map.getLayer(id)) {
      continue;
    }
    try {
      map.moveLayer(id);
    } catch {
      // moveLayer can race with concurrent style edits — safe to ignore, the
      // next pass retries.
    }
  }
}
