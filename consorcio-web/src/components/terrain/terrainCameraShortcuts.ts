export type TerrainCameraShortcut = 'n' | 'u' | 'r';

export function isShortcutTextTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

/** A11Y-01: bare n/u/r only when the map has focus and no modifiers. */
export function terrainCameraShortcutFromEvent(event: KeyboardEvent): TerrainCameraShortcut | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (isShortcutTextTarget(event.target)) return null;
  const key = event.key.toLowerCase();
  if (key === 'n' || key === 'u' || key === 'r') return key;
  return null;
}
