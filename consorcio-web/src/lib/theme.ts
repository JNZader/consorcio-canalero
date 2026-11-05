/* hex-color-allow-file: paleta del tema. Los hex de UI se definen acá, no en los componentes. */
/**
 * Configuracion centralizada del tema Mantine.
 *
 * Este archivo define el tema compartido entre AppProvider y MantineProvider
 * para evitar duplicacion de codigo. `cssVariablesResolver` publica la capa
 * semántica (`--cc-*`, `--z-*`) sin reemplazar las variables de Mantine:
 * el provider las fusiona.
 */

import { type CSSVariablesResolver, createTheme } from '@mantine/core';
import { aboveBreakpoint, belowBreakpoint, breakpoints } from './breakpoints';
import { mapColorTokens } from './mapColorTokens';
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

const SCALE = ['xs', 'sm', 'md', 'lg', 'xl'] as const;
const HEADINGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] as const;

/**
 * Tema personalizado para la aplicacion del Consorcio Canalero.
 *
 * Paleta de colores "Tierra y Agua" inspirada en los rios y campos
 * de la pampa cordobesa.
 */
export const mantineTheme = createTheme({
  // Respect user's OS-level reduced motion preference for all Mantine
  // transitions, modals, and popovers (our custom CSS already handles
  // this via @media prefers-reduced-motion, this covers Mantine internals).
  respectReducedMotion: true,

  // Usar paleta institucional como primaria
  primaryColor: 'institucional',

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

  // Paletas de colores - "Tierra y Agua"
  // Inspirada en los rios y campos de la pampa cordobesa
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
    // Paleta base Mantine ajustada: gray.6 por defecto (#868e96) no alcanza
    // contraste AA sobre blanco para texto chico; mantenemos escala compatible.
    gray: [
      '#f8f9fa',
      '#f1f3f5',
      '#e9ecef',
      '#dee2e6',
      '#ced4da',
      '#adb5bd',
      '#4b5563',
      '#495057',
      '#343a40',
      '#212529',
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
    // Paleta de acento - Dorado Trigal
    acento: [
      '#fef9e7',
      '#fdf0c4',
      '#fce59c',
      '#fbd971',
      '#f9cb4a',
      '#f7be24',
      '#e5ad14',
      '#c9960f',
      '#a87c0c',
      '#866409',
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
    // Color dimmed con mejor contraste en modo oscuro
    // #a0a0a0 tiene ratio 5.5:1 sobre #242424 (supera 4.5:1 requerido)
    dimmedColorLight: '#6b7280', // gray-500 - ratio 5.9:1 sobre blanco
    dimmedColorDark: '#a3a3a3', // neutral-400 - ratio 5.5:1 sobre #242424
    /** Hex de mapa y estilos en línea. Mismo objeto que `mapColorTokens`. */
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
 * solo se agregan `--cc-*` y `--z-*`. Los alias apuntan a variables de
 * Mantine para seguir claro/oscuro sin duplicar el hex.
 */
export const cssVariablesResolver: CSSVariablesResolver = (theme) => {
  const variables: Record<`--${string}`, string> = {
    '--cc-color-primary': 'var(--mantine-color-institucional-5)',
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

  return {
    variables,
    light: {
      '--cc-color-surface-raised': 'var(--mantine-color-gray-0)',
      '--cc-color-danger': 'var(--mantine-color-alerta-6)',
      '--cc-color-warning': 'var(--mantine-color-orange-6)',
      '--cc-color-success': 'var(--mantine-color-exito-6)',
    },
    dark: {
      '--cc-color-surface-raised': 'var(--mantine-color-dark-6)',
      '--cc-color-danger': 'var(--mantine-color-alerta-4)',
      '--cc-color-warning': 'var(--mantine-color-orange-4)',
      '--cc-color-success': 'var(--mantine-color-exito-4)',
    },
  };
};

// Alias para compatibilidad
export const theme = mantineTheme;

export default mantineTheme;
