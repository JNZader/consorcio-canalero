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
  /** Official APRHI portal — navy authority + cyan + gold. */
  APRHI: 'aprhi',
  /** Official IDECOR portal — sky cyan + amber CTA. */
  IDECOR: 'idecor',
  /** Hybrid Córdoba hídrico-geo (APRHI navy chrome + IDECOR sky + river secondary). */
  HIDRICO: 'hidrico',
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
  [BRAND_IDS.APRHI]: {
    id: BRAND_IDS.APRHI,
    name: 'APRHI',
    tagline: 'Portal aprhi.gob.ar — autoridad hídrica',
    notes:
      'Tokens tomados del sitio oficial: navy #004469/#005686, cyan Elementor #6EC1E4, acento #368EB8, oro #F7BC30. Rampas científicas del mapa intactas.',
    institucional: [
      '#e8f4fa',
      '#c5e4f2',
      '#9dcee6',
      '#6eb6d6',
      '#4a9ec4',
      '#368EB8',
      '#005686',
      '#004469',
      '#0c3550',
      '#091635',
    ],
    surface: '#F2F5F7',
    mutedLight: '#67768e',
    darkShell: '#091635',
    darkDeep: '#050b14',
    mutedDark: '#94a3b8',
    water: '#6EC1E4',
    accent: '#F7BC30',
    swatches: [
      { label: 'Marca', hex: '#368EB8' },
      { label: 'Acción', hex: '#005686' },
      { label: 'Navy', hex: '#004469' },
      { label: 'Oro', hex: '#F7BC30' },
    ],
  },
  [BRAND_IDS.IDECOR]: {
    id: BRAND_IDS.IDECOR,
    name: 'IDECOR',
    tagline: 'Portal idecor.gob.ar — datos geo',
    notes:
      'Tokens del portal renovado: cielo #34BAF8, link #0C71C3, soft #7EBEC5, ámbar CTA #F8A310, near-black #060815. Ámbar solo como chip (no botón danger). Mapas científicos intactos.',
    institucional: [
      '#eaf7fd',
      '#c5ebfb',
      '#9adbf7',
      '#6ac8f2',
      '#3eb8ec',
      '#34BAF8',
      '#0C71C3',
      '#0a5a9c',
      '#084578',
      '#060815',
    ],
    surface: '#F2FBFF',
    mutedLight: '#515151',
    darkShell: '#060815',
    darkDeep: '#02040a',
    mutedDark: '#a8b0bc',
    water: '#7EBEC5',
    accent: '#F8A310',
    swatches: [
      { label: 'Marca', hex: '#34BAF8' },
      { label: 'Acción', hex: '#0C71C3' },
      { label: 'Soft', hex: '#7EBEC5' },
      { label: 'Ámbar', hex: '#F8A310' },
    ],
  },
  [BRAND_IDS.HIDRICO]: {
    id: BRAND_IDS.HIDRICO,
    name: 'Hídrico Córdoba',
    tagline: 'Híbrido APRHI + IDECOR + verde río',
    notes:
      'Marca cielo #28B5E8 (puente IDECOR), acción teal #155e75, shell navy #0B2A3D (puente APRHI), chip ámbar #E8A317, secundario río #2d8f68. Distinto de Cuenca (#0e7490) a propósito.',
    institucional: [
      '#e8f7fc',
      '#c8ebf8',
      '#9edaf2',
      '#6fc6e8',
      '#45b8e0',
      '#28B5E8',
      '#155e75',
      '#0f4c5c',
      '#0B2A3D',
      '#060e16',
    ],
    surface: '#F0F7FA',
    mutedLight: '#475569',
    darkShell: '#0B2A3D',
    darkDeep: '#060e16',
    mutedDark: '#94a3b8',
    water: '#0e7490',
    accent: '#E8A317',
    swatches: [
      { label: 'Marca', hex: '#28B5E8' },
      { label: 'Acción', hex: '#155e75' },
      { label: 'Teal', hex: '#0e7490' },
      { label: 'Ámbar', hex: '#E8A317' },
      { label: 'Río', hex: PRIMARY_GREEN },
    ],
  },
};

export const BRAND_PRESET_LIST: readonly BrandPreset[] = [
  BRAND_PRESETS.rio,
  BRAND_PRESETS.aprhi,
  BRAND_PRESETS.idecor,
  BRAND_PRESETS.hidrico,
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
