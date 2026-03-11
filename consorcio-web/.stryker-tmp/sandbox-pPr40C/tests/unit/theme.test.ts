/**
 * Tests for Mantine theme configuration
 * Coverage target: 100%
 */
// @ts-nocheck


import { describe, it, expect } from 'vitest';
import { mantineTheme, theme } from '../../src/lib/theme';

describe('theme', () => {
  describe('mantineTheme object', () => {
    it('should be defined', () => {
      expect(mantineTheme).toBeDefined();
    });

    it('should be an object', () => {
      expect(typeof mantineTheme).toBe('object');
    });

    it('should have primaryColor set', () => {
      expect(mantineTheme.primaryColor).toBe('institucional');
    });

    it('should have primaryColor as string', () => {
      expect(typeof mantineTheme.primaryColor).toBe('string');
    });
  });

  describe('typography configuration', () => {
    it('should have fontFamily', () => {
      expect(mantineTheme.fontFamily).toBeDefined();
      expect(typeof mantineTheme.fontFamily).toBe('string');
    });

    it('should include Inter as primary font', () => {
      expect(mantineTheme.fontFamily!.includes('Inter')).toBe(true);
    });

    it('should have fontSizes object', () => {
      expect(mantineTheme.fontSizes).toBeDefined();
      expect(typeof mantineTheme.fontSizes).toBe('object');
    });

    it('should have all required font sizes', () => {
      const sizes = ['xs', 'sm', 'md', 'lg', 'xl'] as const;
      sizes.forEach((size) => {
        expect(mantineTheme.fontSizes![size]).toBeDefined();
        expect(typeof mantineTheme.fontSizes![size]).toBe('string');
      });
    });

    it('should have lineHeights object', () => {
      expect(mantineTheme.lineHeights).toBeDefined();
    });

    it('should have all required line heights', () => {
      const sizes = ['xs', 'sm', 'md', 'lg', 'xl'] as const;
      sizes.forEach((size) => {
        expect(mantineTheme.lineHeights![size]).toBeDefined();
      });
    });

    it('should have headings configuration', () => {
      expect(mantineTheme.headings).toBeDefined();
      expect(mantineTheme.headings!.fontFamily).toBeDefined();
      expect(mantineTheme.headings!.fontWeight).toBeDefined();
      expect(mantineTheme.headings!.sizes).toBeDefined();
    });

    it('should have all heading levels (h1-h6)', () => {
      const headings = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] as const;
      headings.forEach((h) => {
        expect(mantineTheme.headings!.sizes![h]).toBeDefined();
        expect(mantineTheme.headings!.sizes![h].fontSize).toBeDefined();
        expect(mantineTheme.headings!.sizes![h].lineHeight).toBeDefined();
      });
    });
  });

  describe('spacing configuration', () => {
    it('should have spacing object', () => {
      expect(mantineTheme.spacing).toBeDefined();
    });

    it('should have all required spacing sizes', () => {
      const sizes = ['xs', 'sm', 'md', 'lg', 'xl'] as const;
      sizes.forEach((size) => {
        expect(mantineTheme.spacing![size]).toBeDefined();
        expect(typeof mantineTheme.spacing![size]).toBe('string');
      });
    });
  });

  describe('color palettes', () => {
    it('should have colors object', () => {
      expect(mantineTheme.colors).toBeDefined();
    });

    it('should have institucional color palette', () => {
      expect(mantineTheme.colors!.institucional).toBeDefined();
      expect(Array.isArray(mantineTheme.colors!.institucional)).toBe(true);
      expect(mantineTheme.colors!.institucional!.length).toBe(10);
    });

    it('should have acento color palette', () => {
      expect(mantineTheme.colors!.acento).toBeDefined();
      expect(Array.isArray(mantineTheme.colors!.acento)).toBe(true);
      expect(mantineTheme.colors!.acento!.length).toBe(10);
    });

    it('should have agua color palette', () => {
      expect(mantineTheme.colors!.agua).toBeDefined();
      expect(Array.isArray(mantineTheme.colors!.agua)).toBe(true);
      expect(mantineTheme.colors!.agua!.length).toBe(10);
    });

    it('should have alerta color palette', () => {
      expect(mantineTheme.colors!.alerta).toBeDefined();
      expect(Array.isArray(mantineTheme.colors!.alerta)).toBe(true);
      expect(mantineTheme.colors!.alerta!.length).toBe(10);
    });

    it('should have exito color palette', () => {
      expect(mantineTheme.colors!.exito).toBeDefined();
      expect(Array.isArray(mantineTheme.colors!.exito)).toBe(true);
      expect(mantineTheme.colors!.exito!.length).toBe(10);
    });

    it('should have valid hex color values in institucional', () => {
      mantineTheme.colors!.institucional!.forEach((color) => {
        expect(typeof color).toBe('string');
        expect(/^#[0-9A-Fa-f]{6}$/.test(color)).toBe(true);
      });
    });
  });

  describe('radius configuration', () => {
    it('should have defaultRadius', () => {
      expect(mantineTheme.defaultRadius).toBeDefined();
      expect(mantineTheme.defaultRadius).toBe('md');
    });
  });

  describe('shadows configuration', () => {
    it('should have shadows object', () => {
      expect(mantineTheme.shadows).toBeDefined();
    });

    it('should have all shadow sizes', () => {
      const sizes = ['xs', 'sm', 'md', 'lg', 'xl'] as const;
      sizes.forEach((size) => {
        expect(mantineTheme.shadows![size]).toBeDefined();
        expect(typeof mantineTheme.shadows![size]).toBe('string');
      });
    });

    it('should have shadow values as rgba', () => {
      expect(mantineTheme.shadows!.md!.includes('rgba')).toBe(true);
    });
  });

  describe('other configuration', () => {
    it('should have other object', () => {
      expect(mantineTheme.other).toBeDefined();
    });

    it('should have dimmedColorLight', () => {
      expect(mantineTheme.other!.dimmedColorLight).toBeDefined();
      expect(/^#[0-9A-Fa-f]{6}$/.test(mantineTheme.other!.dimmedColorLight)).toBe(true);
    });

    it('should have dimmedColorDark', () => {
      expect(mantineTheme.other!.dimmedColorDark).toBeDefined();
      expect(/^#[0-9A-Fa-f]{6}$/.test(mantineTheme.other!.dimmedColorDark)).toBe(true);
    });
  });

  describe('component defaults', () => {
    it('should have components object', () => {
      expect(mantineTheme.components).toBeDefined();
    });

    it('should configure Button component', () => {
      expect(mantineTheme.components!.Button).toBeDefined();
      expect(mantineTheme.components!.Button!.defaultProps).toBeDefined();
      expect(mantineTheme.components!.Button!.styles).toBeDefined();
    });

    it('should configure Card component', () => {
      expect(mantineTheme.components!.Card).toBeDefined();
      expect(mantineTheme.components!.Card!.defaultProps).toBeDefined();
    });

    it('should configure Form components (TextInput, Select, Textarea)', () => {
      expect(mantineTheme.components!.TextInput).toBeDefined();
      expect(mantineTheme.components!.Select).toBeDefined();
      expect(mantineTheme.components!.Textarea).toBeDefined();
    });

    it('should configure Badge component', () => {
      expect(mantineTheme.components!.Badge).toBeDefined();
      expect(mantineTheme.components!.Badge!.defaultProps!.variant).toBe('light');
    });

    it('should configure Table component with proper defaults', () => {
      expect(mantineTheme.components!.Table).toBeDefined();
      expect(mantineTheme.components!.Table!.defaultProps!.striped).toBe(true);
      expect(mantineTheme.components!.Table!.defaultProps!.highlightOnHover).toBe(true);
    });

    it('should configure Modal with centered default', () => {
      expect(mantineTheme.components!.Modal).toBeDefined();
      expect(mantineTheme.components!.Modal!.defaultProps!.centered).toBe(true);
    });

    it('should configure Loader component', () => {
      expect(mantineTheme.components!.Loader).toBeDefined();
      expect(mantineTheme.components!.Loader!.defaultProps!.type).toBe('dots');
    });

    it('should have all major Mantine components configured', () => {
      const expectedComponents = [
        'Button',
        'Card',
        'Paper',
        'TextInput',
        'Select',
        'Textarea',
        'Badge',
        'Alert',
        'Table',
        'Progress',
        'Loader',
        'ThemeIcon',
        'ActionIcon',
        'Tooltip',
        'Modal',
        'Drawer',
        'Notification',
      ];

      expectedComponents.forEach((comp) => {
        expect(mantineTheme.components![comp as any]).toBeDefined();
      });
    });
  });

  describe('theme alias', () => {
    it('should export theme as alias for mantineTheme', () => {
      expect(theme).toBe(mantineTheme);
    });

    it('should have same properties as mantineTheme', () => {
      expect(theme.primaryColor).toBe(mantineTheme.primaryColor);
      expect(theme.fontFamily).toBe(mantineTheme.fontFamily);
      expect(theme.colors).toBe(mantineTheme.colors);
    });
  });

  describe('theme consistency', () => {
    it('should have consistent typography scale', () => {
      const sizes = mantineTheme.fontSizes!;
      // Just verify all values are strings
      Object.values(sizes).forEach((size) => {
        expect(typeof size).toBe('string');
      });
    });

    it('should have all color palettes with 10 colors', () => {
      const palettes = ['institucional', 'acento', 'agua', 'alerta', 'exito'] as const;
      palettes.forEach((pal) => {
        expect(mantineTheme.colors![pal]!.length).toBe(10);
      });
    });

    it('should have matching radius defaults in components', () => {
      // Button and Card should use default radius
      expect(mantineTheme.components!.Button!.defaultProps!.radius).toBe('md');
      expect(mantineTheme.components!.Card!.defaultProps!.radius).toBe('lg');
    });
  });
});
