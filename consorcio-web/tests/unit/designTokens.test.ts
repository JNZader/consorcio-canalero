import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { DEFAULT_THEME, mergeMantineTheme } from '@mantine/core';
import { describe, expect, it } from 'vitest';
import { MAP_DESKTOP_MEDIA_QUERY } from '../../src/components/map2d/MapWorkspace';
import {
  aboveBreakpoint,
  belowBreakpoint,
  breakpoints,
  mediaAbove,
  mediaBelow,
  mediaMaxWidth,
  mediaMinWidth,
} from '../../src/lib/breakpoints';
import {
  cssVariablesResolver,
  INSTITUCIONAL_9,
  mantineTheme,
  PRIMARY_GREEN,
  TOUCH_MIN,
} from '../../src/lib/theme';
import { Z_INDEX, Z_INDEX_VAR } from '../../src/lib/zIndex';

function luma(hex: string): number {
  const channel = (offset: number) => Number.parseInt(hex.slice(offset, offset + 2), 16);
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function walk(dir: string, acc: string[]): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walk(full, acc);
    else if (/\.tsx?$/.test(entry.name)) acc.push(full);
  }
  return acc;
}

describe('design tokens', () => {
  it('keeps Mantine breakpoints as the only width scale', () => {
    expect(mantineTheme.breakpoints).toEqual(breakpoints);
    expect(breakpoints).toEqual({
      xs: '36em',
      sm: '48em',
      md: '62em',
      lg: '75em',
      xl: '88em',
    });
    expect(belowBreakpoint('sm')).toBe('47.9375em');
    expect(aboveBreakpoint('md')).toBe('62.0625em');
    expect(mediaMinWidth('sm')).toBe('(min-width: 48em)');
    expect(mediaMaxWidth('md')).toBe('(max-width: 62em)');
    expect(mediaBelow('sm')).toBe('(max-width: 47.9375em)');
    expect(mediaAbove('md')).toBe('(min-width: 62.0625em)');
  });

  it('builds the map desktop query from the sm token', () => {
    expect(MAP_DESKTOP_MEDIA_QUERY).toBe(`${mediaMinWidth('sm')} and (min-height: 40em)`);
  });

  it('pins the map CSS literals to those tokens', () => {
    const mapCss = readFileSync('src/styles/components/map.module.css', 'utf8');
    const rainfallCss = readFileSync(
      'src/components/map2d/rainfall/RainfallAnswerCard.module.css',
      'utf8'
    );
    expect(mapCss).toContain(`max-width: ${breakpoints.md}`);
    expect(mapCss).toContain(`max-width: ${belowBreakpoint('sm')}`);
    expect(mapCss).toContain(`min-width: ${aboveBreakpoint('md')}`);
    expect(rainfallCss).toContain(`max-width: ${breakpoints.md}`);
  });

  it('does not leave the old width literals in shared CSS or TS media queries', () => {
    const shared = [
      'src/styles/global.css',
      'src/styles/components/header.module.css',
      'src/styles/components/footer.module.css',
      'src/styles/components/home.module.css',
      'src/styles/components/form.module.css',
    ];
    for (const file of shared) {
      const css = readFileSync(file, 'utf8');
      expect(css, file).not.toMatch(/62em|47\.9375em|48em|768px/);
    }

    const rawQuery = /useMediaQuery\(\s*['"`]\((?:max-width: (?:62em|768px)|min-width: 48em)\)/;
    for (const file of walk('src', [])) {
      if (file.endsWith('src/lib/breakpoints.ts')) continue;
      expect(readFileSync(file, 'utf8'), file).not.toMatch(rawQuery);
    }
  });

  it('gives institucional[9] a darker shade and syncs theme-color', () => {
    const institucional = mantineTheme.colors!.institucional!;
    expect(institucional[5]).toBe(PRIMARY_GREEN);
    expect(institucional[9]).toBe(INSTITUCIONAL_9);
    expect(institucional[9]).not.toBe(institucional[7]);
    expect(institucional[9]).not.toBe(institucional[8]);
    expect(luma(institucional[9]!)).toBeLessThan(luma(institucional[8]!));
    expect(luma(institucional[8]!)).toBeLessThan(luma(institucional[7]!));

    const html = readFileSync('index.html', 'utf8');
    const vite = readFileSync('vite.config.ts', 'utf8');
    expect(html).toContain(`name="theme-color" content="${PRIMARY_GREEN}"`);
    expect(html).toContain(`name="msapplication-TileColor" content="${PRIMARY_GREEN}"`);
    expect(vite).toContain(`theme_color: '${PRIMARY_GREEN}'`);
    expect(html).not.toContain('#2d9970');
    expect(vite).not.toContain('#2d9970');
  });

  it('publishes semantic CSS variables and the z-index scale', () => {
    const theme = mergeMantineTheme(DEFAULT_THEME, mantineTheme);
    const resolved = cssVariablesResolver(theme);

    expect(resolved.variables['--cc-color-primary']).toBe('var(--mantine-color-institucional-5)');
    expect(resolved.variables['--cc-color-surface']).toBe('var(--mantine-color-body)');
    expect(resolved.variables['--cc-color-text']).toBe('var(--mantine-color-text)');
    expect(resolved.variables['--cc-color-text-muted']).toBe('var(--mantine-color-dimmed)');
    expect(resolved.variables['--cc-color-border']).toBe('var(--mantine-color-default-border)');
    expect(resolved.variables['--cc-touch-min']).toBe(TOUCH_MIN);
    const withoutTouch = cssVariablesResolver({ ...theme, other: {} });
    expect(withoutTouch.variables['--cc-touch-min']).toBe(TOUCH_MIN);
    expect(resolved.variables['--cc-space-md']).toBe('var(--mantine-spacing-md)');
    expect(resolved.variables['--cc-radius-md']).toBe('var(--mantine-radius-md)');
    expect(resolved.variables['--cc-shadow-md']).toBe('var(--mantine-shadow-md)');
    expect(resolved.variables['--cc-font-family']).toBe('var(--mantine-font-family)');
    expect(resolved.variables['--cc-font-size-md']).toBe('var(--mantine-font-size-md)');
    expect(resolved.variables['--cc-font-size-h1']).toBe('var(--mantine-h1-font-size)');
    expect(resolved.variables['--cc-breakpoint-sm']).toBe(breakpoints.sm);
    expect(resolved.variables['--cc-breakpoint-sm-max']).toBe(belowBreakpoint('sm'));
    expect(resolved.light['--cc-color-danger']).toBe('var(--mantine-color-alerta-6)');
    expect(resolved.light['--cc-color-warning']).toBe('var(--mantine-color-orange-6)');
    expect(resolved.light['--cc-color-success']).toBe('var(--mantine-color-exito-6)');
    expect(resolved.dark['--cc-color-surface-raised']).toBe('var(--mantine-color-dark-6)');
    expect(resolved.variables['--mantine-color-white']).toBeUndefined();

    for (const [token, cssVar] of Object.entries(Z_INDEX_VAR)) {
      expect(resolved.variables[cssVar]).toBe(String(Z_INDEX[token as keyof typeof Z_INDEX]));
    }

    const globalCss = readFileSync('src/styles/global.css', 'utf8');
    const headerCss = readFileSync('src/styles/components/header.module.css', 'utf8');
    expect(headerCss).toContain('z-index: var(--z-header, 100)');
    expect(globalCss).toContain('z-index: var(--z-base, 0)');
    expect(globalCss).toContain('z-index: var(--z-portal, 9999)');
    expect(globalCss).toContain('z-index: var(--z-popover, 10000)');
    expect(globalCss).toContain('z-index: var(--z-overlay, 10001)');
    expect(globalCss).toContain('z-index: var(--z-skip-link, 100000)');
    expect(globalCss).toContain('var(--cc-touch-min, 44px)');
    expect(statSync('src/lib/zIndex.ts').isFile()).toBe(true);
  });
});
