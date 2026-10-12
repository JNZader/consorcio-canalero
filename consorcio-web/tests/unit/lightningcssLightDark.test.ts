import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(join(import.meta.dirname, '../../src/styles/global.css'), 'utf8');

describe('UX-27 lightningcss light-dark polyfill', () => {
  it('defines --lightningcss-light/dark for light and Mantine dark', () => {
    expect(css).toMatch(/:root \{[\s\S]*--lightningcss-light:\s*initial;/);
    expect(css).toMatch(
      /:root\[data-mantine-color-scheme='dark'\] \{[\s\S]*--lightningcss-dark:\s*initial;/,
    );
    expect(css).toMatch(/:root \{[\s\S]*color-scheme:\s*light;/);
    expect(css).toMatch(
      /:root\[data-mantine-color-scheme='dark'\] \{[\s\S]*color-scheme:\s*dark;/,
    );
  });
});
