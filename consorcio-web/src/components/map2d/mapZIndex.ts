/**
 * Stacking order for the 2D map chrome.
 *
 * The stylesheet mirrors every value as `--z-map-*` on `:root`
 * (`map/classNames`). Inline styles must read this object so a panel cannot
 * invent a new layer. `tests/unit/mapZIndex.test.ts` pins the two copies
 * together.
 */
export const MAP_Z = {
  hazard: 3,
  hazardMobile: 4,
  comparison: 10,
  overlay: 12,
  dateBadge: 14,
  divider: 15,
  controls: 16,
  measurementLabel: 17,
  profile: 18,
  blocking: 20,
  pageChrome: 25,
  panel: 1000,
  drawerOverlay: 1150,
  drawer: 1200,
  burger: 1250,
  gesture: 1300,
} as const;

export type MapZIndexToken = keyof typeof MAP_Z;
