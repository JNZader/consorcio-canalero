/* hex-color-allow-file: paleta del tema. Los hex de UI y de mapa se definen acá, no en los componentes. */
/**
 * Configuracion centralizada del tema Mantine.
 *
 * Este archivo define el tema compartido del MantineProvider de `main.tsx`
 * para evitar duplicacion de codigo. `cssVariablesResolver` publica la capa
 * semántica (`--cc-*`, `--cc-map-*`, `--z-*`) sin reemplazar las variables
 * de Mantine: el provider las fusiona.
 */

import {
  type CSSVariablesResolver,
  createTheme,
  defaultVariantColorsResolver,
  type VariantColorsResolver,
} from '@mantine/core';
import { aboveBreakpoint, belowBreakpoint, breakpoints } from './breakpoints';
import { Z_INDEX, Z_INDEX_VAR } from './zIndex';

/** Verde río. `institucional[5]`. `index.html` y el manifest PWA usan este hex. */
export const PRIMARY_GREEN = '#2d8f68';

/**
 * `institucional[9]`. Más oscuro que [8] (`#0a3d2d`).
 * Antes repetía [7] (`#0d4d38`).
 */
export const INSTITUCIONAL_9 = '#082d21';

/** Piso táctil (WCAG 2.5.5). */
export const TOUCH_MIN = '44px';

/**
 * Rótulo blanco en los filled del primario.
 * `autoContrast` no puede volverlos negros sobre el verde.
 * Un tono explícito (`institucional.1`) sigue el resolver de Mantine.
 */
export const variantColorResolver: VariantColorsResolver = (input) => {
  const resolved = defaultVariantColorsResolver(input);
  const name = input.color || input.theme.primaryColor;
  const primaryFilled =
    input.variant === 'filled' &&
    typeof name === 'string' &&
    !name.includes('.') &&
    (name === 'institucional' || name === input.theme.primaryColor);
  if (!primaryFilled) return resolved;
  return {
    ...resolved,
    color: 'var(--mantine-color-white)',
    hoverColor: 'var(--mantine-color-white)',
  };
};

/**
 * Paleta cartográfica. Los valores son los hex que ya pintaba el mapa.
 * `cssVariablesResolver` los publica como `--cc-map-<hex>`.
 * No reasigna rampas científicas ni las marcas (el logo de Google conserva su hex).
 */
export const mapColorTokens = {
  h000000: '#000000',
  h00000066: '#00000066',
  h0072b2: '#0072b2',
  h006064: '#006064',
  h00695C: '#00695C',
  h00838F: '#00838F',
  h00897B: '#00897B',
  h00ACC1: '#00ACC1',
  h045a8d: '#045a8d',
  h06b6d4: '#06b6d4',
  h08306b: '#08306b',
  h0891b2: '#0891b2',
  h0B3D91: '#0B3D91',
  h0c2c84: '#0c2c84',
  h0D47A1: '#0D47A1',
  h0e7490: '#0e7490',
  h0EA5E9: '#0EA5E9',
  h0f172a: '#0f172a',
  h0f766e: '#0f766e',
  h10B981: '#10B981',
  h111111: '#111111',
  h111827: '#111827',
  h14532D: '#14532D',
  h14b8a6: '#14b8a6',
  h1565C0: '#1565C0',
  h166534: '#166534',
  h16A34A: '#16A34A',
  h1971c2: '#1971c2',
  h1976d2: '#1976d2',
  h1ABC9C: '#1ABC9C',
  h1b5e20: '#1b5e20',
  h1c7ed6: '#1c7ed6',
  h1D4ED8: '#1D4ED8',
  h1d4ed8: '#1d4ed8',
  h1d91c0: '#1d91c0',
  h1E3A8A: '#1E3A8A',
  h1E40AF: '#1E40AF',
  h1E88E5: '#1E88E5',
  h212121: '#212121',
  h2166ac: '#2166ac',
  h2171b5: '#2171b5',
  h2196F3: '#2196F3',
  h22C55E: '#22C55E',
  h22c55e: '#22c55e',
  h2563eb: '#2563eb',
  h2563EB: '#2563EB',
  h27AE60: '#27AE60',
  h2b83ba: '#2b83ba',
  h2b8cbe: '#2b8cbe',
  h2e7d32: '#2e7d32',
  h2ECC71: '#2ECC71',
  h333: '#333',
  h333399: '#333399',
  h334155: '#334155',
  h3388ff: '#3388ff',
  h3498DB: '#3498DB',
  h34A853: '#34A853',
  h3b82f6: '#3b82f6',
  h3B82F6: '#3B82F6',
  h41b6c4: '#41b6c4',
  h4285F4: '#4285F4',
  h42A5F5: '#42A5F5',
  h4C1D95: '#4C1D95',
  h4CAF50: '#4CAF50',
  h5C6BC0: '#5C6BC0',
  h60A5FA: '#60A5FA',
  h64B5F6: '#64B5F6',
  h67a9cf: '#67a9cf',
  h689f38: '#689f38',
  h6baed6: '#6baed6',
  h6d4c41: '#6d4c41',
  h74a9cf: '#74a9cf',
  h78716c: '#78716c',
  h78c679: '#78c679',
  h7B1FA2: '#7B1FA2',
  h7c3aed: '#7c3aed',
  h7fcdbb: '#7fcdbb',
  h868e96: '#868e96',
  h86EFAC: '#86EFAC',
  h87CEEB: '#87CEEB',
  h888888: '#888888',
  h8b5cf6: '#8b5cf6',
  h8B5CF6: '#8B5CF6',
  h8d6e63: '#8d6e63',
  h94a3b8: '#94a3b8',
  h991B1B: '#991B1B',
  h993404: '#993404',
  h9B59B6: '#9B59B6',
  h9C27B0: '#9C27B0',
  h9e9e9e: '#9e9e9e',
  ha1d99b: '#a1d99b',
  ha50026: '#a50026',
  ha63603: '#a63603',
  hA855F7: '#A855F7',
  habdda4: '#abdda4',
  haddd8e: '#addd8e',
  hB10026: '#B10026',
  hb2182b: '#b2182b',
  hB45309: '#B45309',
  hb91c1c: '#b91c1c',
  hbd0026: '#bd0026',
  hbdc9e1: '#bdc9e1',
  hc026d3: '#c026d3',
  hc0ca33: '#c0ca33',
  hc2410c: '#c2410c',
  hc45c26: '#c45c26',
  hc62828: '#c62828',
  hc6dbef: '#c6dbef',
  hc7e9b4: '#c7e9b4',
  hc8d6e5: '#c8d6e5',
  hccc: '#ccc',
  hd1e5f0: '#d1e5f0',
  hD32F2F: '#D32F2F',
  hD35400: '#D35400',
  hd55e00: '#d55e00',
  hd7191c: '#d7191c',
  hd84315: '#d84315',
  hd8e1ea: '#d8e1ea',
  hd95f0e: '#d95f0e',
  hd9f0a3: '#d9f0a3',
  hdc2626: '#dc2626',
  hDC2626: '#DC2626',
  hDCFCE7: '#DCFCE7',
  hddd6fe: '#ddd6fe',
  he03131: '#e03131',
  he0a100: '#e0a100',
  hE31A1C: '#E31A1C',
  he6550d: '#e6550d',
  he69f00: '#e69f00',
  hE74C3C: '#E74C3C',
  he8590c: '#e8590c',
  hEA4335: '#EA4335',
  hea580c: '#ea580c',
  heab308: '#eab308',
  hEDE9FE: '#EDE9FE',
  hef4444: '#ef4444',
  hef6c00: '#ef6c00',
  hef8a62: '#ef8a62',
  hf03b20: '#f03b20',
  hf08c00: '#f08c00',
  hf1eef6: '#f1eef6',
  hF39C12: '#F39C12',
  hf46d43: '#f46d43',
  hF59E0B: '#F59E0B',
  hf59f00: '#f59f00',
  hf7f7f7: '#f7f7f7',
  hf7fbff: '#f7fbff',
  hf97316: '#f97316',
  hF97316: '#F97316',
  hf9a825: '#f9a825',
  hfacc15: '#facc15',
  hfb8c00: '#fb8c00',
  hfb923c: '#fb923c',
  hFBBC05: '#FBBC05',
  hFC4E2A: '#FC4E2A',
  hFCD34D: '#FCD34D',
  hfd7e14: '#fd7e14',
  hfd8d3c: '#fd8d3c',
  hFD8D3C: '#FD8D3C',
  hfdae61: '#fdae61',
  hfdbe85: '#fdbe85',
  hfddbc7: '#fddbc7',
  hfe9929: '#fe9929',
  hFEB24C: '#FEB24C',
  hfec44f: '#fec44f',
  hfecc5c: '#fecc5c',
  hfee391: '#fee391',
  hfeedde: '#feedde',
  hFF0000: '#FF0000',
  hFF6D00: '#FF6D00',
  hFF8F00: '#FF8F00',
  hFF9800: '#FF9800',
  hFFA500: '#FFA500',
  hFFEB3B: '#FFEB3B',
  hffedd5: '#ffedd5',
  hfff: '#fff',
  hffffb2: '#ffffb2',
  hffffbf: '#ffffbf',
  hffffcc: '#ffffcc',
  hffffd4: '#ffffd4',
  hffffff: '#ffffff',
  hFFFFFF: '#FFFFFF',
  hffffff55: '#ffffff55',
} as const;

export type MapColorToken = keyof typeof mapColorTokens;

/** Nombre CSS `--cc-map-<hex>`. Claves que solo cambian de caja comparten variable. */
export function mapCssVariable(token: MapColorToken): `--cc-map-${string}` {
  return `--cc-map-${token.slice(1).toLowerCase()}`;
}

/** `var(--cc-map-…)` para el DOM. MapLibre sigue leyendo el hex en `mapColorTokens`. */
export function mapColorVar(token: MapColorToken): `var(--cc-map-${string})` {
  return `var(${mapCssVariable(token)})`;
}

/**
 * Cromo del mapa que sigue a Río limpio y al oscuro.
 * Las rampas científicas no: `--cc-map-<hex>` vale igual en los dos esquemas.
 */
export const mapChromeVars = {
  labelSurface: 'var(--cc-map-label-surface)',
  labelText: 'var(--cc-map-label-text)',
  labelBorder: 'var(--cc-map-label-border)',
  profileBorder: 'var(--cc-map-profile-border)',
  profileSurface: 'var(--cc-map-profile-surface)',
  profileText: 'var(--cc-map-profile-text)',
} as const;

const SCALE = ['xs', 'sm', 'md', 'lg', 'xl'] as const;
const HEADINGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] as const;

/**
 * Tema personalizado para la aplicacion del Consorcio Canalero.
 *
 * Paleta "Río más limpio": un solo verde de marca, superficies claras
 * quietas y un oscuro verdoso. El wordmark usa ese verde.
 */
export const mantineTheme = createTheme({
  // Respect user's OS-level reduced motion preference for all Mantine
  // transitions, modals, and popovers (our custom CSS already handles
  // this via @media prefers-reduced-motion, this covers Mantine internals).
  respectReducedMotion: true,

  // Usar paleta institucional como primaria.
  // El filled usa el tono 6 en claro y en oscuro: blanco sobre #16654a
  // pasa AA. El tono 5 es el verde de marca y se queda corto con blanco.
  primaryColor: 'institucional',
  primaryShade: { light: 6, dark: 6 },
  variantColorResolver,

  // Misma escala que los defaults de Mantine. Fuente única para
  // `visibleFrom` / `hiddenFrom` y para los helpers de `breakpoints.ts`.
  breakpoints,

  // Tipografia.
  //
  // ``Inter Fallback`` / ``DM Serif Display Fallback`` son las caras locales
  // con metricas corregidas que define ``src/styles/global.css`` (size-adjust +
  // ascent/descent/line-gap-override). Van SIEMPRE inmediatamente despues de la
  // webfont real: mientras el woff2 baja, el texto se pinta con la cara local
  // ya ajustada, asi el ``font-display: swap`` no mueve el layout.
  fontFamily:
    'Inter, "Inter Fallback", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  fontSizes: {
    xs: '0.75rem',
    sm: '0.875rem',
    md: '1rem',
    lg: '1.125rem',
    xl: '1.25rem',
  },
  lineHeights: {
    xs: '1.4',
    sm: '1.45',
    md: '1.55',
    lg: '1.6',
    xl: '1.65',
  },
  headings: {
    fontFamily:
      '"DM Serif Display", "DM Serif Display Fallback", Georgia, "Times New Roman", serif',
    fontWeight: '400',
    sizes: {
      h1: { fontSize: '2.25rem', lineHeight: '1.2' },
      h2: { fontSize: '1.75rem', lineHeight: '1.25' },
      h3: { fontSize: '1.375rem', lineHeight: '1.3' },
      h4: { fontSize: '1.125rem', lineHeight: '1.35' },
      h5: { fontSize: '1rem', lineHeight: '1.4' },
      h6: { fontSize: '0.875rem', lineHeight: '1.45' },
    },
  },

  // Escalas de espaciado
  spacing: {
    xs: '0.5rem',
    sm: '0.75rem',
    md: '1rem',
    lg: '1.5rem',
    xl: '2rem',
  },

  // Escalas de Río más limpio. El verde de marca es institucional[5].
  // Optimizado para contraste WCAG AA (4.5:1 para texto, 3:1 para elementos grandes)
  colors: {
    // Paletas Mantine base ajustadas para que variantes `filled` y `light`
    // mantengan contraste AA en texto chico.
    blue: [
      '#e7f5ff',
      '#d0ebff',
      '#a5d8ff',
      '#74c0fc',
      '#4dabf7',
      '#339af0',
      '#1971c2',
      '#1864ab',
      '#0b4f8a',
      '#083b66',
    ],
    red: [
      '#fff5f5',
      '#ffe3e3',
      '#ffc9c9',
      '#ffa8a8',
      '#ff8787',
      '#ff6b6b',
      '#a61e1e',
      '#8a1919',
      '#681212',
      '#681212',
    ],
    orange: [
      '#fff4e6',
      '#ffe8cc',
      '#ffd8a8',
      '#ffc078',
      '#ffa94d',
      '#ff922b',
      '#9a3412',
      '#7c2d12',
      '#5f210d',
      '#5f210d',
    ],
    // Papel claro, con un verde apenas insinuado. gray-6 se queda en
    // #4b5563: es el texto chico y pasa AA sobre blanco y sobre gray-0.
    gray: [
      '#f5f8f6',
      '#e9efeb',
      '#dde6e0',
      '#cfd9d3',
      '#b7c4bd',
      '#8d9b94',
      '#4b5563',
      '#3f4a44',
      '#2c3530',
      '#1b221e',
    ],
    // Oscuro del río. Mantine 9 trae un neutro (#242424 en el tono 7)
    // que se corta contra el hero verde. El texto atenuado (#a3a3a3)
    // sigue en AA sobre los tonos 4, 6 y 7.
    dark: [
      '#e4eee8',
      '#c5d4cb',
      '#9fb0a6',
      '#7f978c',
      '#293c34',
      '#22332c',
      '#1b2a24',
      '#14201b',
      '#101a16',
      '#0b1411',
    ],
    // Paleta institucional - Verde-Azulado Rio
    // Ajustada para mejor contraste en modo oscuro
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
    // Paleta para estados de agua/inundacion
    agua: [
      '#e8f4f8',
      '#c5e4ed',
      '#9dd2e1',
      '#72bfd4',
      '#4aadc7',
      '#2d9ab8',
      '#2387a3',
      '#1a6f86',
      '#135869',
      '#0c424e',
    ],
    // Paleta para alertas/emergencias
    alerta: [
      '#fef2f0',
      '#fde0db',
      '#fbcac2',
      '#f8afa3',
      '#f59082',
      '#f06d5c',
      '#e54f3a',
      '#c73d2a',
      '#a3301f',
      '#7f2516',
    ],
    // Paleta para exito/resuelto
    exito: [
      '#e9f7ec',
      '#c8ebd0',
      '#a3ddb2',
      '#7bce92',
      '#56c074',
      '#38b058',
      '#2d9648',
      '#237a3a',
      '#1a5f2d',
      '#124521',
    ],
  },

  // Radio por defecto
  defaultRadius: 'md',

  // Colores personalizados para mejor contraste WCAG AA
  other: {
    // Texto chico / atenuado. AA 4.5:1 medido con gamma (no el promedio lineal).
    // gray-6 sobre blanco 7.6:1 y sobre gray-0 7.2:1. #6b7280 se quedaba en 4.8:1
    // sobre blanco y bajaba de 4.5:1 sobre gray-1.
    dimmedColorLight: '#4b5563',
    // #a3a3a3 sobre dark-7 6.6:1, sobre dark-6 5.9:1, sobre dark-4 4.6:1.
    dimmedColorDark: '#a3a3a3',
    /** Hex de mapa. Mismo objeto que reexporta `mapColorTokens.ts`. */
    mapColors: mapColorTokens,
    touchMin: TOUCH_MIN,
    zIndex: Z_INDEX,
  },

  // Sombras personalizadas — dark mode gets stronger shadows since
  // dark surfaces need more contrast to show depth.
  shadows: {
    xs: '0 1px 2px light-dark(rgba(0,0,0,0.05), rgba(0,0,0,0.2))',
    sm: '0 1px 3px light-dark(rgba(0,0,0,0.1), rgba(0,0,0,0.3))',
    md: '0 4px 6px light-dark(rgba(0,0,0,0.1), rgba(0,0,0,0.35))',
    lg: '0 10px 15px light-dark(rgba(0,0,0,0.1), rgba(0,0,0,0.4))',
    xl: '0 20px 25px light-dark(rgba(0,0,0,0.15), rgba(0,0,0,0.5))',
  },

  // Componentes personalizados
  components: {
    Button: {
      defaultProps: {
        radius: 'md',
      },
      styles: {
        root: {
          fontWeight: 500,
          transition: 'all 0.2s ease',
        },
      },
    },
    Card: {
      defaultProps: {
        radius: 'lg',
        shadow: 'sm',
      },
      styles: {
        root: {
          transition: 'box-shadow 0.2s ease, transform 0.2s ease',
        },
      },
    },
    Paper: {
      defaultProps: {
        radius: 'lg',
      },
    },
    TextInput: {
      defaultProps: {
        radius: 'md',
      },
    },
    Select: {
      defaultProps: {
        radius: 'md',
      },
    },
    Textarea: {
      defaultProps: {
        radius: 'md',
      },
    },
    Badge: {
      defaultProps: {
        radius: 'sm',
        variant: 'light',
      },
    },
    Alert: {
      defaultProps: {
        radius: 'md',
      },
    },
    Table: {
      defaultProps: {
        striped: true,
        highlightOnHover: true,
        verticalSpacing: 'sm',
      },
    },
    Progress: {
      defaultProps: {
        radius: 'xl',
        size: 'md',
      },
    },
    Loader: {
      defaultProps: {
        type: 'dots',
      },
    },
    ThemeIcon: {
      defaultProps: {
        radius: 'md',
      },
    },
    ActionIcon: {
      defaultProps: {
        radius: 'md',
      },
    },
    Tooltip: {
      defaultProps: {
        radius: 'md',
        transitionProps: { transition: 'fade', duration: 200 },
      },
    },
    Modal: {
      defaultProps: {
        radius: 'lg',
        centered: true,
      },
    },
    Drawer: {
      defaultProps: {
        radius: 'md',
      },
    },
    Notification: {
      defaultProps: {
        radius: 'md',
      },
    },
  },
});

const Z_INDEX_ENTRIES = Object.entries(Z_INDEX_VAR) as [keyof typeof Z_INDEX, `--z-${string}`][];

/**
 * Capa semántica. Mantine fusiona este objeto con el suyo, así que acá
 * solo se agregan `--cc-*`, `--cc-map-*` y `--z-*`. Los alias de cromo
 * apuntan a variables de Mantine para seguir claro/oscuro sin duplicar
 * el hex. Las rampas del mapa salen con el mismo hex en los dos esquemas.
 */
export const cssVariablesResolver: CSSVariablesResolver = (theme) => {
  const variables: Record<`--${string}`, string> = {
    '--cc-color-primary': 'var(--mantine-color-institucional-5)',
    '--cc-color-wordmark': 'var(--mantine-color-institucional-7)',
    '--cc-color-surface': 'var(--mantine-color-body)',
    '--cc-color-text': 'var(--mantine-color-text)',
    '--cc-color-text-muted': 'var(--mantine-color-dimmed)',
    '--cc-color-border': 'var(--mantine-color-default-border)',
    '--cc-font-family': 'var(--mantine-font-family)',
    '--cc-font-family-heading': 'var(--mantine-font-family-headings)',
    '--cc-touch-min': String(theme.other.touchMin ?? TOUCH_MIN),
    '--cc-breakpoint-sm-max': belowBreakpoint('sm'),
    '--cc-breakpoint-md-above': aboveBreakpoint('md'),
  };

  for (const size of SCALE) {
    variables[`--cc-space-${size}`] = `var(--mantine-spacing-${size})`;
    variables[`--cc-radius-${size}`] = `var(--mantine-radius-${size})`;
    variables[`--cc-shadow-${size}`] = `var(--mantine-shadow-${size})`;
    variables[`--cc-font-size-${size}`] = `var(--mantine-font-size-${size})`;
    variables[`--cc-line-height-${size}`] = `var(--mantine-line-height-${size})`;
  }

  for (const heading of HEADINGS) {
    variables[`--cc-font-size-${heading}`] = `var(--mantine-${heading}-font-size)`;
    variables[`--cc-line-height-${heading}`] = `var(--mantine-${heading}-line-height)`;
  }

  for (const [token, value] of Object.entries(theme.breakpoints)) {
    variables[`--cc-breakpoint-${token}`] = String(value);
  }

  for (const [token, cssVar] of Z_INDEX_ENTRIES) {
    variables[cssVar] = String(Z_INDEX[token]);
  }

  const seenMapVars = new Set<string>();
  for (const token of Object.keys(mapColorTokens) as MapColorToken[]) {
    const cssVar = mapCssVariable(token);
    if (seenMapVars.has(cssVar)) continue;
    seenMapVars.add(cssVar);
    variables[cssVar] = mapColorTokens[token];
  }

  return {
    variables,
    light: {
      '--cc-color-surface-raised': 'var(--mantine-color-gray-0)',
      '--cc-color-danger': 'var(--mantine-color-alerta-6)',
      '--cc-color-warning': 'var(--mantine-color-orange-6)',
      '--cc-color-success': 'var(--mantine-color-exito-6)',
      '--mantine-color-dimmed': String(theme.other.dimmedColorLight ?? '#4b5563'),
      '--mantine-color-placeholder': String(theme.other.dimmedColorLight ?? '#4b5563'),
      '--cc-map-label-surface': 'rgba(255, 255, 255, 0.96)',
      '--cc-map-label-text': mapColorTokens.h333,
      '--cc-map-label-border': mapColorTokens.hfd7e14,
      '--cc-map-profile-border': 'var(--mantine-color-blue-3)',
      '--cc-map-profile-surface': 'var(--mantine-color-blue-0)',
      '--cc-map-profile-text': 'var(--mantine-color-blue-6)',
    },
    dark: {
      '--cc-color-surface-raised': 'var(--mantine-color-dark-6)',
      '--cc-color-danger': 'var(--mantine-color-alerta-4)',
      '--cc-color-warning': 'var(--mantine-color-orange-4)',
      '--cc-color-success': 'var(--mantine-color-exito-4)',
      '--cc-color-wordmark': 'var(--mantine-color-institucional-3)',
      '--mantine-color-dimmed': String(theme.other.dimmedColorDark ?? '#a3a3a3'),
      '--mantine-color-placeholder': String(theme.other.dimmedColorDark ?? '#a3a3a3'),
      // gray-6 del tema es un gris oscuro pensado para texto sobre claro.
      '--mantine-color-gray-6': String(theme.other.dimmedColorDark ?? '#a3a3a3'),
      '--cc-map-label-surface': 'color-mix(in srgb, var(--mantine-color-dark-7) 94%, transparent)',
      '--cc-map-label-text': 'var(--cc-color-text)',
      '--cc-map-label-border': mapColorTokens.hfd7e14,
      '--cc-map-profile-border': 'var(--mantine-color-blue-4)',
      '--cc-map-profile-surface': 'var(--mantine-color-dark-5)',
      '--cc-map-profile-text': 'var(--mantine-color-blue-2)',
    },
  };
};

// Alias para compatibilidad
export const theme = mantineTheme;

export default mantineTheme;
