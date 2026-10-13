import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SPEC = readFileSync(resolve(process.cwd(), 'tests/accessibility/a11y.spec.ts'), 'utf-8');

describe('A11Y-11 axe routes', () => {
  it('covers participacion and perfil, not only home/mapa/login', () => {
    expect(SPEC).toContain("path: '/participacion'");
    expect(SPEC).toContain("path: '/perfil'");
  });
});
