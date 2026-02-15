/**
 * Configuracion centralizada del tema Mantine.
 *
 * Este archivo define el tema compartido entre AppProvider y MantineProvider
 * para evitar duplicacion de codigo.
 */

import { createTheme } from '@mantine/core';

/**
 * Tema personalizado para la aplicacion del Consorcio Canalero.
 *
 * Paleta de colores "Tierra y Agua" inspirada en los rios y campos
 * de la pampa cordobesa.
 */
export const mantineTheme = createTheme({
  // Usar paleta institucional como primaria
  primaryColor: 'institucional',

  // Tipografia
  fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
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
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
    fontWeight: '600',
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
    // Paleta institucional - Verde-Azulado Rio
    // Ajustada para mejor contraste en modo oscuro
    institucional: [
      '#e8f5f0',
      '#c8e6dc',
      '#a3d4c4',
      '#7bc2ac',
      '#5ab394',
      '#3da67f',
      '#2d9970',
      '#34a876', // Cambiado de #1e7d5a - ratio 4.6:1 sobre #2e2e2e
      '#16654a',
      '#0d4d38',
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
  },

  // Sombras personalizadas
  shadows: {
    xs: '0 1px 2px rgba(0, 0, 0, 0.05)',
    sm: '0 1px 3px rgba(0, 0, 0, 0.1)',
    md: '0 4px 6px rgba(0, 0, 0, 0.1)',
    lg: '0 10px 15px rgba(0, 0, 0, 0.1)',
    xl: '0 20px 25px rgba(0, 0, 0, 0.15)',
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

// Alias para compatibilidad
export const theme = mantineTheme;

export default mantineTheme;
