import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  applyBrand,
  bootBrandFromStorage,
  getActiveBrandId,
} from '../../src/lib/applyBrand';
import {
  BRAND_CHANGE_EVENT,
  BRAND_IDS,
  BRAND_PRESETS,
  BRAND_STORAGE_KEY,
  DEFAULT_BRAND_ID,
  isBrandId,
} from '../../src/lib/brandPresets';
import { PRIMARY_GREEN } from '../../src/lib/theme';

describe('brandPresets', () => {
  it('keeps rio shade 5/6 aligned with theme.ts', () => {
    const rio = BRAND_PRESETS.rio;
    expect(rio.institucional[5]).toBe(PRIMARY_GREEN);
    expect(rio.institucional[6]).toBe('#16654a');
    expect(rio.institucional).toHaveLength(10);
  });

  it('exposes seven packs with distinct brand marks', () => {
    const marks = BRAND_PRESET_LIST_MARKS();
    expect(marks).toHaveLength(7);
    expect(new Set(marks).size).toBe(7);
  });

  it('type-guards brand ids including APRHI / IDECOR / hídrico', () => {
    expect(isBrandId('cuenca')).toBe(true);
    expect(isBrandId('aprhi')).toBe(true);
    expect(isBrandId('idecor')).toBe(true);
    expect(isBrandId('hidrico')).toBe(true);
    expect(isBrandId('nope')).toBe(false);
    expect(isBrandId(null)).toBe(false);
  });

  it('pins official portal marks for the three Córdoba packs', () => {
    expect(BRAND_PRESETS.aprhi.institucional[5]).toBe('#368EB8');
    expect(BRAND_PRESETS.aprhi.institucional[6]).toBe('#005686');
    expect(BRAND_PRESETS.aprhi.accent).toBe('#F7BC30');
    expect(BRAND_PRESETS.idecor.institucional[5]).toBe('#34BAF8');
    expect(BRAND_PRESETS.idecor.institucional[6]).toBe('#0C71C3');
    expect(BRAND_PRESETS.idecor.accent).toBe('#F8A310');
    expect(BRAND_PRESETS.hidrico.institucional[5]).toBe('#28B5E8');
    expect(BRAND_PRESETS.hidrico.institucional[6]).toBe('#155e75');
    expect(BRAND_PRESETS.hidrico.water).toBe('#0e7490');
    expect(BRAND_PRESETS.hidrico.accent).toBe('#E8A317');
  });
});

function BRAND_PRESET_LIST_MARKS(): string[] {
  return Object.values(BRAND_PRESETS).map((p) => p.institucional[5]!);
}

describe('applyBrand', () => {
  let localStore: Record<string, string>;

  beforeEach(() => {
    localStore = {};
    vi.mocked(window.localStorage.getItem).mockImplementation(
      (key: string) => localStore[key] ?? null
    );
    vi.mocked(window.localStorage.setItem).mockImplementation((key: string, value: string) => {
      localStore[key] = value;
    });
    vi.mocked(window.localStorage.removeItem).mockImplementation((key: string) => {
      delete localStore[key];
    });
    vi.mocked(window.localStorage.clear).mockImplementation(() => {
      localStore = {};
    });

    document.documentElement.removeAttribute('data-brand');
    document.documentElement.removeAttribute('style');
    document.head.innerHTML =
      '<meta name="theme-color" content="#2d8f68" />' +
      '<meta name="msapplication-TileColor" content="#2d8f68" />';
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-brand');
    document.documentElement.removeAttribute('style');
  });

  it('applies cuenca CSS vars and data-brand', () => {
    applyBrand(BRAND_IDS.CUENCA, { notify: false });

    expect(document.documentElement.getAttribute('data-brand')).toBe('cuenca');
    expect(
      document.documentElement.style.getPropertyValue('--mantine-color-institucional-5')
    ).toBe(BRAND_PRESETS.cuenca.institucional[5]);
    expect(
      document.documentElement.style.getPropertyValue('--mantine-primary-color-filled')
    ).toBe(BRAND_PRESETS.cuenca.institucional[6]);
    expect(window.localStorage.getItem(BRAND_STORAGE_KEY)).toBe('cuenca');
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe(
      BRAND_PRESETS.cuenca.institucional[5]
    );
  });

  it('clears overrides when returning to rio default', () => {
    applyBrand(BRAND_IDS.HUMEDAL, { notify: false });
    applyBrand(BRAND_IDS.RIO, { notify: false });

    expect(document.documentElement.getAttribute('data-brand')).toBeNull();
    expect(
      document.documentElement.style.getPropertyValue('--mantine-color-institucional-5')
    ).toBe('');
    expect(window.localStorage.getItem(BRAND_STORAGE_KEY) ?? null).toBeNull();
    expect(getActiveBrandId()).toBe(DEFAULT_BRAND_ID);
  });

  it('boots from localStorage without rewriting storage', () => {
    window.localStorage.setItem(BRAND_STORAGE_KEY, 'campo');
    const id = bootBrandFromStorage();
    expect(id).toBe('campo');
    expect(document.documentElement.getAttribute('data-brand')).toBe('campo');
    expect(window.localStorage.getItem(BRAND_STORAGE_KEY)).toBe('campo');
  });

  it('ignores garbage storage values', () => {
    window.localStorage.setItem(BRAND_STORAGE_KEY, 'hot-pink');
    expect(bootBrandFromStorage()).toBe(DEFAULT_BRAND_ID);
    expect(document.documentElement.getAttribute('data-brand')).toBeNull();
  });

  it('dispatches cc-brand-change when notify is true', () => {
    const handler = vi.fn();
    globalThis.addEventListener(BRAND_CHANGE_EVENT, handler);
    applyBrand(BRAND_IDS.CUENCA);
    expect(handler).toHaveBeenCalledTimes(1);
    globalThis.removeEventListener(BRAND_CHANGE_EVENT, handler);
  });

  it('does not write map scientific CSS vars', () => {
    applyBrand(BRAND_IDS.CAMPO, { notify: false });
    const inline = document.documentElement.getAttribute('style') ?? '';
    expect(inline.includes('--cc-map-')).toBe(false);
  });

  it('writes scheme-aware dimmed so dark mode keeps AA muted text', () => {
    applyBrand(BRAND_IDS.CUENCA, { notify: false });
    const dimmed = document.documentElement.style.getPropertyValue(
      '--mantine-color-dimmed'
    );
    expect(dimmed).toBe(
      `light-dark(${BRAND_PRESETS.cuenca.mutedLight}, ${BRAND_PRESETS.cuenca.mutedDark})`
    );
    expect(
      document.documentElement.style.getPropertyValue('--mantine-color-placeholder')
    ).toBe(dimmed);
  });
});
