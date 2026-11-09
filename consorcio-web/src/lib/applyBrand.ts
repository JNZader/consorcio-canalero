/**
 * Apply a Theme Lab brand pack to the live document via CSS variables.
 *
 * Strategy: set `html[data-brand]` and override Mantine shade CSS vars on
 * `document.documentElement`. Components that read `--mantine-color-institucional-*`
 * or `--cc-color-primary` (alias to institucional-5) update without remounting
 * MantineProvider. Map scientific `--cc-map-*` hexes are never written here.
 */

import {
  BRAND_CHANGE_EVENT,
  BRAND_PRESETS,
  BRAND_STORAGE_KEY,
  DEFAULT_BRAND_ID,
  type BrandId,
  isBrandId,
} from './brandPresets';

const INSTITUCIONAL_VAR_PREFIX = '--mantine-color-institucional-';

/** CSS custom properties this module owns (cleared / rewritten on each apply). */
const MANAGED_VARS = [
  ...Array.from({ length: 10 }, (_, i) => `${INSTITUCIONAL_VAR_PREFIX}${i}`),
  '--mantine-color-gray-0',
  '--mantine-color-dimmed',
  '--mantine-color-placeholder',
  '--mantine-color-dark-7',
  '--mantine-color-dark-8',
  '--mantine-color-dark-9',
  '--mantine-color-agua-5',
  '--mantine-primary-color-filled',
  '--mantine-primary-color-filled-hover',
  '--mantine-primary-color-light',
  '--mantine-primary-color-light-hover',
  '--mantine-primary-color-light-color',
  '--mantine-primary-color-0',
  '--mantine-primary-color-1',
  '--mantine-primary-color-2',
  '--mantine-primary-color-3',
  '--mantine-primary-color-4',
  '--mantine-primary-color-5',
  '--mantine-primary-color-6',
  '--mantine-primary-color-7',
  '--mantine-primary-color-8',
  '--mantine-primary-color-9',
] as const;

function readStoredBrandId(): BrandId {
  if (typeof globalThis.localStorage === 'undefined') return DEFAULT_BRAND_ID;
  try {
    const raw = globalThis.localStorage.getItem(BRAND_STORAGE_KEY);
    if (isBrandId(raw)) return raw;
  } catch {
    // private mode / blocked storage — fall through to default
  }
  return DEFAULT_BRAND_ID;
}

function persistBrandId(id: BrandId): void {
  if (typeof globalThis.localStorage === 'undefined') return;
  try {
    if (id === DEFAULT_BRAND_ID) {
      globalThis.localStorage.removeItem(BRAND_STORAGE_KEY);
    } else {
      globalThis.localStorage.setItem(BRAND_STORAGE_KEY, id);
    }
  } catch {
    // ignore quota / private mode
  }
}

function syncThemeColorMeta(hex: string): void {
  if (typeof document === 'undefined') return;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', hex);
  const tile = document.querySelector('meta[name="msapplication-TileColor"]');
  if (tile) tile.setAttribute('content', hex);
}

function clearManagedVars(root: HTMLElement): void {
  for (const name of MANAGED_VARS) {
    root.style.removeProperty(name);
  }
}

function writeBrandVars(root: HTMLElement, id: BrandId): void {
  const preset = BRAND_PRESETS[id];
  clearManagedVars(root);

  // Default pack = theme.ts SoT. Drop data-brand + inline overrides so Mantine
  // stylesheet values win without duplicating the Río scale here forever.
  if (id === DEFAULT_BRAND_ID) {
    root.removeAttribute('data-brand');
    syncThemeColorMeta(preset.institucional[5]);
    return;
  }

  root.setAttribute('data-brand', id);

  for (let i = 0; i < 10; i += 1) {
    const shade = preset.institucional[i]!;
    root.style.setProperty(`${INSTITUCIONAL_VAR_PREFIX}${i}`, shade);
    root.style.setProperty(`--mantine-primary-color-${i}`, shade);
  }

  // Filled action uses shade 6 (same as theme primaryShade).
  const action = preset.institucional[6]!;
  const brand = preset.institucional[5]!;
  const light = preset.institucional[0]!;
  const lightColor = preset.institucional[7]!;

  root.style.setProperty('--mantine-primary-color-filled', action);
  root.style.setProperty('--mantine-primary-color-filled-hover', preset.institucional[7]!);
  root.style.setProperty('--mantine-primary-color-light', light);
  root.style.setProperty('--mantine-primary-color-light-hover', preset.institucional[1]!);
  root.style.setProperty('--mantine-primary-color-light-color', lightColor);

  root.style.setProperty('--mantine-color-gray-0', preset.surface);
  root.style.setProperty('--mantine-color-dimmed', preset.mutedLight);
  root.style.setProperty('--mantine-color-placeholder', preset.mutedLight);
  root.style.setProperty('--mantine-color-dark-7', preset.darkShell);
  root.style.setProperty('--mantine-color-dark-8', preset.darkDeep);
  root.style.setProperty('--mantine-color-dark-9', preset.darkDeep);
  root.style.setProperty('--mantine-color-agua-5', preset.water);

  // Brand mark for PWA chrome; filled buttons keep shade 6 via primary vars.
  syncThemeColorMeta(brand);
}

export interface ApplyBrandOptions {
  /** Persist to localStorage (default true). */
  readonly persist?: boolean;
  /** Dispatch `cc-brand-change` (default true). */
  readonly notify?: boolean;
}

/**
 * Apply a brand pack. Safe to call before React mounts (boot) and from UI.
 */
export function applyBrand(id: BrandId, options: ApplyBrandOptions = {}): BrandId {
  const { persist = true, notify = true } = options;
  if (typeof document === 'undefined') return id;

  const root = document.documentElement;
  writeBrandVars(root, id);

  if (persist) persistBrandId(id);

  if (notify && typeof globalThis.dispatchEvent === 'function') {
    globalThis.dispatchEvent(
      new CustomEvent(BRAND_CHANGE_EVENT, { detail: { brandId: id } })
    );
  }

  return id;
}

/** Read the active brand from `data-brand` or storage (boot-safe). */
export function getActiveBrandId(): BrandId {
  if (typeof document !== 'undefined') {
    const attr = document.documentElement.getAttribute('data-brand');
    if (isBrandId(attr)) return attr;
  }
  return readStoredBrandId();
}

/**
 * Boot hook: restore the last preview brand before first paint.
 * Call once from `main.tsx` before `ReactDOM.createRoot(...).render`.
 */
export function bootBrandFromStorage(): BrandId {
  const id = readStoredBrandId();
  return applyBrand(id, { persist: false, notify: false });
}
