/* hex-color-allow-file: brand Theme Lab packs. UI hex lives here; map scientific ramps stay in theme.ts. */
/**
 * Brand presets for the admin Theme Lab.
 *
 * Each pack overrides Mantine `institucional` / surface / dark / agua shades via
 * CSS variables on `document.documentElement` (`data-brand`). Scientific map
 * ramps (`--cc-map-*` from `mapColorTokens`) are intentionally untouched.
 *
 * Default `rio` matches `theme.ts` ("Río más limpio").
 */

import { INSTITUCIONAL_9, PRIMARY_GREEN } from './theme';

/** localStorage key — browser-local preview only, not a server preference. */
export const BRAND_STORAGE_KEY = 'cc-brand-id';

/** Fired on `window` after a brand apply so React surfaces can sync. */
export const BRAND_CHANGE_EVENT = 'cc-brand-change';

export const BRAND_IDS = {
  RIO: 'rio',
  CUENCA: 'cuenca',
  HUMEDAL: 'humedal',
  CAMPO: 'campo',
} as const;

export type BrandId = (typeof BRAND_IDS)[keyof typeof BRAND_IDS];

export const DEFAULT_BRAND_ID: BrandId = BRAND_IDS.RIO;

/** Mantine 10-shade tuple. Index 5 = brand mark; index 6 = filled action. */
export type BrandShadeScale = readonly [
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
];

export interface BrandSwatch {
  readonly label: string;
  readonly hex: string;
}

export interface BrandPreset {
  readonly id: BrandId;
  readonly name: string;
  readonly tagline: string;
  readonly notes: string;
  /** institucional[0..9] */
  readonly institucional: BrandShadeScale;
  /** gray[0] surface tint (light body paper) */
  readonly surface: string;
  /** gray[6] / dimmed light text */
  readonly mutedLight: string;
  /** dark[7] shell surface */
  readonly darkShell: string;
  /** dark[9] deepest */
  readonly darkDeep: string;
  /** dimmed dark text */
  readonly mutedDark: string;
  /** agua[5] water accent (UI only; map ramps stay put) */
  readonly water: string;
  /** Optional clay / earth accent for preview chips */
  readonly accent?: string;
  readonly swatches: readonly BrandSwatch[];
}

export const BRAND_PRESETS: Record<BrandId, BrandPreset> = {
  [BRAND_IDS.RIO]: {
    id: BRAND_IDS.RIO,
    name: 'Río limpio',
    tagline: 'Actual — verde de marca del consorcio',
    notes:
      'PRIMARY_GREEN #2d8f68 (marca) y filled #16654a (acción AA). Las rampas científicas del mapa no cambian.',
    institucional: [
      '#e8f5f0',
      '#c8e6dc',
      '#a3d4c4',
      '#7bc2ac',
      '#5ab394',
      PRIMARY_GREEN,
      '#16654a',
      '#0d4d38',
      '#0a3d2d',
      INSTITUCIONAL_9,
    ],
    surface: '#f5f8f6',
    mutedLight: '#4b5563',
    darkShell: '#14201b',
    darkDeep: '#0b1411',
    mutedDark: '#a3a3a3',
    water: '#2d9ab8',
    swatches: [
      { label: 'Marca', hex: PRIMARY_GREEN },
      { label: 'Acción', hex: '#16654a' },
      { label: 'Superficie', hex: '#f5f8f6' },
      { label: 'Agua UI', hex: '#2d9ab8' },
    ],
  },
  [BRAND_IDS.CUENCA]: {
    id: BRAND_IDS.CUENCA,
    name: 'Cuenca azul',
    tagline: 'Teal-azul — autoridad hídrica',
    notes:
      'Marca #0e7490 y acción #155e75. Más institucional / APRHI; buen contraste sobre satélite. Mapas científicos intactos.',
    institucional: [
      '#e6f7fb',
      '#c5ebf3',
      '#9ad9e8',
      '#6bc4da',
      '#3aabc7',
      '#0e7490',
      '#155e75',
      '#0f4c5c',
      '#0a3a47',
      '#062830',
    ],
    surface: '#f0f7fa',
    mutedLight: '#475569',
    darkShell: '#0f172a',
    darkDeep: '#020617',
    mutedDark: '#94a3b8',
    water: '#0284c7',
    swatches: [
      { label: 'Marca', hex: '#0e7490' },
      { label: 'Acción', hex: '#155e75' },
      { label: 'Superficie', hex: '#f0f7fa' },
      { label: 'Agua UI', hex: '#0284c7' },
    ],
  },
  [BRAND_IDS.HUMEDAL]: {
    id: BRAND_IDS.HUMEDAL,
    name: 'Humedal',
    tagline: 'Verde bosque + acento clay',
    notes:
      'Verde más oscuro #1b5e4b / filled #0f3d32. Acento clay #c2410c para chips de preview; alerta semántica sigue en paleta alerta.',
    institucional: [
      '#e8f3ef',
      '#c5e2d8',
      '#9ccbbd',
      '#6fad9b',
      '#458f7a',
      '#1b5e4b',
      '#0f3d32',
      '#0c3229',
      '#0a2821',
      '#071c17',
    ],
    surface: '#f4f6f3',
    mutedLight: '#3f4a44',
    darkShell: '#0b1411',
    darkDeep: '#050a08',
    mutedDark: '#a3a3a3',
    water: '#0e7490',
    accent: '#c2410c',
    swatches: [
      { label: 'Marca', hex: '#1b5e4b' },
      { label: 'Acción', hex: '#0f3d32' },
      { label: 'Superficie', hex: '#f4f6f3' },
      { label: 'Clay', hex: '#c2410c' },
    ],
  },
  [BRAND_IDS.CAMPO]: {
    id: BRAND_IDS.CAMPO,
    name: 'Campo al atardecer',
    tagline: 'Tierra / ocre — acento rural',
    notes:
      'Primario ocre #b45309 / filled #9a3412. El verde del río queda como secundario en el preview. Cuidado: cerca del warning naranja de hazard.',
    institucional: [
      '#fef6ee',
      '#fde8d2',
      '#fbcfa4',
      '#f5b06d',
      '#e8923a',
      '#b45309',
      '#9a3412',
      '#7c2d12',
      '#5f210d',
      '#431407',
    ],
    surface: '#faf7f2',
    mutedLight: '#57534e',
    darkShell: '#1c1917',
    darkDeep: '#0c0a09',
    mutedDark: '#a8a29e',
    water: '#0891b2',
    accent: PRIMARY_GREEN,
    swatches: [
      { label: 'Marca', hex: '#b45309' },
      { label: 'Acción', hex: '#9a3412' },
      { label: 'Superficie', hex: '#faf7f2' },
      { label: 'Verde sec.', hex: PRIMARY_GREEN },
    ],
  },
};

export const BRAND_PRESET_LIST: readonly BrandPreset[] = [
  BRAND_PRESETS.rio,
  BRAND_PRESETS.cuenca,
  BRAND_PRESETS.humedal,
  BRAND_PRESETS.campo,
];

export function isBrandId(value: unknown): value is BrandId {
  return (
    typeof value === 'string' &&
    (Object.values(BRAND_IDS) as string[]).includes(value)
  );
}
