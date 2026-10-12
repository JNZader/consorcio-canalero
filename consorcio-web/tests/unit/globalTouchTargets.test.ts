import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const GLOBAL_CSS = readFileSync(resolve(process.cwd(), 'src/styles/global.css'), 'utf-8');

function coarseBlock(): string {
  const start = GLOBAL_CSS.indexOf('@media (pointer: coarse) {');
  expect(start).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = GLOBAL_CSS.indexOf('{', start); i < GLOBAL_CSS.length; i += 1) {
    if (GLOBAL_CSS[i] === '{') depth += 1;
    if (GLOBAL_CSS[i] === '}') {
      depth -= 1;
      if (depth === 0) return GLOBAL_CSS.slice(start, i + 1);
    }
  }
  throw new Error('unterminated coarse media block');
}

describe('coarse pointer touch targets (MOB-01 / A11Y-04)', () => {
  it('includes ActionIcon buttons in the 44px coarse rule', () => {
    const block = coarseBlock();
    expect(block).toMatch(/^\s*button,/m);
    expect(block).not.toContain(':not(.mantine-ActionIcon-root)');
    expect(block).toContain('min-height: 44px');
    expect(block).toContain('min-width: 44px');
  });
});
