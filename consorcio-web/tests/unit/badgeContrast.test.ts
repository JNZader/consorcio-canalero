import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function channel(hex: string, index: number) {
  return Number.parseInt(hex.slice(1 + index * 2, 3 + index * 2), 16);
}

function linear(value: number) {
  const s = value / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function contrast(hex: string, background: [number, number, number]) {
  const rgb = [0, 1, 2].map((index) => channel(hex, index));
  const mix = rgb.map((value, index) => value * 0.16 + background[index] * 0.84);
  const luminance = (color: number[]) =>
    0.2126 * linear(color[0]) + 0.7152 * linear(color[1]) + 0.0722 * linear(color[2]);
  const fg = luminance(rgb);
  const bg = luminance(mix);
  return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
}

describe('contraste de badges sobre el tint', () => {
  const theme = readFileSync('src/lib/theme.ts', 'utf8');

  it('éxito y alerta en claro superan 4.5 y el naranja de aviso no se aclara', () => {
    expect(theme).toContain("'#14532d'");
    expect(theme).toContain("'#9f1239'");
    expect(theme).toContain("'#9a3412'");
    expect(contrast('#14532d', [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#9f1239', [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#9a3412', [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#0d4d38', [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#7bc2ac', [20, 32, 27])).toBeGreaterThanOrEqual(4.5);
  });
});
