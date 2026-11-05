import { describe, expect, it } from 'vitest';
import { notificationColor, semanticColor } from '../../src/lib/semanticColors';

function channel(hex: string, offset: number): number {
  const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function contrast(foreground: string, background: string): number {
  const luma = (hex: string) =>
    0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5);
  const lighter = Math.max(luma(foreground), luma(background));
  const darker = Math.min(luma(foreground), luma(background));
  return (lighter + 0.05) / (darker + 0.05);
}

describe('semantic colors', () => {
  it('maps legacy toast colors onto the palette', () => {
    expect(semanticColor).toEqual({
      info: 'institucional',
      success: 'exito',
      warning: 'orange',
      danger: 'alerta',
    });
    expect(notificationColor('green')).toBe('exito');
    expect(notificationColor('teal')).toBe('exito');
    expect(notificationColor('red')).toBe('alerta');
    expect(notificationColor('blue')).toBe('institucional');
    expect(notificationColor('cyan')).toBe('institucional');
    expect(notificationColor('yellow')).toBe('orange');
    expect(notificationColor('orange')).toBe('orange');
    expect(notificationColor('exito')).toBe('exito');
    expect(notificationColor('gray')).toBe('gray');
  });

  it('keeps small text on the surfaces it actually sits on at AA', () => {
    expect(contrast('#4b5563', '#ffffff')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#4b5563', '#f8f9fa')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#4b5563', '#f1f3f5')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#a3a3a3', '#1A1B1E')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#a3a3a3', '#25262b')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#a3a3a3', '#373A40')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#e9ecef', '#082d21')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#7f2516', '#fde0db')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#124521', '#c8ebd0')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#fef2f0', '#1A1B1E')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#e9f7ec', '#1A1B1E')).toBeGreaterThanOrEqual(4.5);
    expect(contrast('#ffffff', '#16654a')).toBeGreaterThanOrEqual(4.5);
  });
});
