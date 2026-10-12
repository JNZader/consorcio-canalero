import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const MAP_CSS = readFileSync(
  resolve(process.cwd(), 'src/styles/components/map.module.css'),
  'utf-8',
);

function coarseBlock(): string {
  const start = MAP_CSS.indexOf('@media (pointer: coarse) {');
  expect(start).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = MAP_CSS.indexOf('{', start); i < MAP_CSS.length; i += 1) {
    if (MAP_CSS[i] === '{') depth += 1;
    if (MAP_CSS[i] === '}') {
      depth -= 1;
      if (depth === 0) return MAP_CSS.slice(start, i + 1);
    }
  }
  throw new Error('unterminated @media (pointer: coarse) block');
}

function pxOf(css: string, selector: string, prop: string): number {
  const rule = new RegExp(`\\.${selector}\\s*\\{([^}]*)\\}`).exec(css);
  expect(rule, `${selector} rule`).not.toBeNull();
  const value = new RegExp(`${prop}:\\s*(-?[\\d.]+)px`).exec(rule?.[1] ?? '')?.[1];
  expect(value, `${selector}.${prop}`).toBeDefined();
  return Number(value);
}

describe('mapRightStack (UX-19)', () => {
  it('stacks home, places and export in one column below the native controls', () => {
    const rule = /\.mapRightStack\s*\{([^}]*)\}/.exec(MAP_CSS)?.[1] ?? '';
    expect(rule).toMatch(/display:\s*flex/);
    expect(rule).toMatch(/flex-direction:\s*column/);
    expect(rule).toMatch(/gap:\s*10px/);
    expect(pxOf(MAP_CSS, 'mapRightStack', 'top')).toBeGreaterThanOrEqual(146);
  });

  it('does not give places or export their own overlapping top', () => {
    expect(MAP_CSS).not.toMatch(/\.mapPlacesDock\s*\{[^}]*top:/);
    expect(MAP_CSS).not.toMatch(/\.mapActionsDock\s*\{[^}]*top:/);
    const coarse = coarseBlock();
    expect(coarse).not.toMatch(/\.mapPlacesDock\s*\{[^}]*top:/);
    expect(coarse).not.toMatch(/\.mapActionsDock\s*\{[^}]*top:/);
  });

  it('keeps the coarse stack below nav + fullscreen (196px) and on-canvas', () => {
    const coarse = coarseBlock();
    const top = pxOf(coarse, 'mapRightStack', 'top');
    expect(top).toBeGreaterThanOrEqual(206);
    expect(top + 2 * 44 + 10 + 44).toBeLessThanOrEqual(380);
  });

  it('lays the stack as a bottom row on landscape phones (390px viewport)', () => {
    const start = MAP_CSS.indexOf(
      '@media (pointer: coarse) and (orientation: landscape) and (max-height: 30em)',
    );
    expect(start).toBeGreaterThan(-1);
    const block = MAP_CSS.slice(start, start + 1800);
    expect(block).toMatch(/\.mapRightStack\s*\{[^}]*top:\s*auto/);
    expect(block).toMatch(/\.mapRightStack\s*\{[^}]*bottom:\s*56px/);
    expect(block).toMatch(/\.mapRightStack\s*\{[^}]*flex-direction:\s*row/);
  });
});
