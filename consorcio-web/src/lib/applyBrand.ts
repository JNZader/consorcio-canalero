/**
 * Apply a Theme Lab brand pack to the live document via CSS variables.
 *
 * Strategy: set `html[data-brand]` and override Mantine shade CSS vars on
 * `document.documentElement`. Components that read `--mantine-color-institucional-*`
 * or `--cc-color-primary` (alias to institucional-5) update without remounting
 * MantineProvider. Map scientific `--cc-map-*` hexes are never written here.
 */

import type { CSSProperties } from 'react';
import {
  BRAND_CHANGE_EVENT,
  BRAND_PRESETS,
  type BrandId,
  type BrandPreset,
  BRAND_STORAGE_KEY,
  DEFAULT_BRAND_ID,
  isBrandId,
} from './brandPresets';

const INSTITUCIONAL_VAR_PREFIX = '--mantine-color-institucional-';

/** CSS custom properties this module owns (cleared / rewritten on each apply). */
const MANAGED_VARS = [
  ...Array.from({ length: 10 }, (_, i) => `${INSTITUCIONAL_VAR_PREFIX}${i}`),
  `${INSTITUCIONAL_VAR_PREFIX}filled`,
  `${INSTITUCIONAL_VAR_PREFIX}filled-hover`,
  `${INSTITUCIONAL_VAR_PREFIX}light`,
  `${INSTITUCIONAL_VAR_PREFIX}light-hover`,
  `${INSTITUCIONAL_VAR_PREFIX}light-color`,
  `${INSTITUCIONAL_VAR_PREFIX}outline`,
  `${INSTITUCIONAL_VAR_PREFIX}outline-hover`,
  `${INSTITUCIONAL_VAR_PREFIX}text`,
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

function hexLuminance(hex: string): number {
  const clean = hex.replace('#', '');
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map((ch) => ch + ch)
          .join('')
      : clean;
  const toLinear = (offset: number) => {
    const srgb = Number.parseInt(full.slice(offset, offset + 2), 16) / 255;
    return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * toLinear(0) + 0.7152 * toLinear(2) + 0.0722 * toLinear(4);
}

/** Pick AA foreground ink on a custom accent badge background. */
export function pickAccentContrastInk(
  accentHex: string
): 'var(--mantine-color-white)' | 'var(--mantine-color-dark-9)' {
  return hexLuminance(accentHex) < 0.1791
    ? 'var(--mantine-color-white)'
    : 'var(--mantine-color-dark-9)';
}

/** Isolated CSS custom properties for previewing a brand preset card independently. */
export function buildBrandPreviewCssVars(preset: BrandPreset): CSSProperties {
  const vars: Record<string, string> = {};
  for (let i = 0; i < 10; i += 1) {
    const shade = preset.institucional[i]!;
    vars[`${INSTITUCIONAL_VAR_PREFIX}${i}`] = shade;
    vars[`--mantine-primary-color-${i}`] = shade;
  }

  const action = preset.institucional[6]!;
  const light = preset.institucional[0]!;
  const lightInk = preset.institucional[7]!;
  const darkInk = preset.institucional[3]!;
  const schemeInk = `light-dark(${lightInk}, ${darkInk})`;
  const lightTint = `light-dark(${light}, color-mix(in srgb, ${preset.institucional[4]!} 18%, transparent))`;
  const lightHover = `light-dark(${preset.institucional[1]!}, color-mix(in srgb, ${preset.institucional[4]!} 26%, transparent))`;
  const outlineHover = `light-dark(${light}, color-mix(in srgb, ${preset.institucional[4]!} 14%, transparent))`;

  vars[`${INSTITUCIONAL_VAR_PREFIX}7`] = schemeInk;
  vars['--mantine-primary-color-7'] = schemeInk;
  vars[`${INSTITUCIONAL_VAR_PREFIX}filled`] = action;
  vars['--mantine-primary-color-filled'] = action;
  vars[`${INSTITUCIONAL_VAR_PREFIX}filled-hover`] = lightInk;
  vars['--mantine-primary-color-filled-hover'] = lightInk;
  vars[`${INSTITUCIONAL_VAR_PREFIX}light`] = lightTint;
  vars['--mantine-primary-color-light'] = lightTint;
  vars[`${INSTITUCIONAL_VAR_PREFIX}light-hover`] = lightHover;
  vars['--mantine-primary-color-light-hover'] = lightHover;
  vars[`${INSTITUCIONAL_VAR_PREFIX}light-color`] = schemeInk;
  vars['--mantine-primary-color-light-color'] = schemeInk;
  vars[`${INSTITUCIONAL_VAR_PREFIX}outline`] = schemeInk;
  vars[`${INSTITUCIONAL_VAR_PREFIX}outline-hover`] = outlineHover;
  vars[`${INSTITUCIONAL_VAR_PREFIX}text`] = schemeInk;
  vars['--mantine-color-agua-5'] = preset.water;

  return vars as CSSProperties;
}

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

  for (const [prop, value] of Object.entries(buildBrandPreviewCssVars(preset)) as [
    string,
    string,
  ][]) {
    root.style.setProperty(prop, value);
  }

  const brand = preset.institucional[5]!;

  root.style.setProperty('--mantine-color-gray-0', preset.surface);
  // Scheme-aware: inline styles beat Mantine's dark resolver. A light muted
  // hex left here permanently fails AA on darkShell (~2:1). light-dark()
  // tracks data-mantine-color-scheme the same way theme shadows do.
  const muted = `light-dark(${preset.mutedLight}, ${preset.mutedDark})`;
  root.style.setProperty('--mantine-color-dimmed', muted);
  root.style.setProperty('--mantine-color-placeholder', muted);
  root.style.setProperty('--mantine-color-dark-7', preset.darkShell);
  root.style.setProperty('--mantine-color-dark-8', preset.darkDeep);
  root.style.setProperty('--mantine-color-dark-9', preset.darkDeep);

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
