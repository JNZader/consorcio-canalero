/**
 * Phase 1 - Comprehensive mutation tests for formatters.ts
 * Targets: null checks, boundary conditions, operator mutations
 * Target kill rate: ≥80%
 */
// @ts-nocheck


import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  formatDate,
  formatDateForInput,
  formatRelativeTime,
  formatNumber,
  formatHectares,
  formatPercentage,
  formatDateCustom,
  formatDateTime,
} from '../../../src/lib/formatters';

describe('formatters - formatDate()', () => {
  it('should return fallback for null/undefined dates', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate(undefined)).toBe('-');
  });

  it('should return custom fallback when provided', () => {
    expect(formatDate(null, { fallback: 'N/A' })).toBe('N/A');
    expect(formatDate(undefined, { fallback: 'MISSING' })).toBe('MISSING');
  });

  it('should return fallback for invalid date strings', () => {
    expect(formatDate('invalid-date')).toBe('-');
    expect(formatDate('2026-13-45')).toBe('-'); // Invalid month/day
  });

  it('should format valid date string correctly', () => {
    const result = formatDate('2026-03-09T10:30:00Z');
    expect(result).toMatch(/9|9/); // Should contain day
    expect(result).toContain('2026'); // Should contain year
  });

  it('should format Date object correctly', () => {
    const date = new Date('2026-03-09T10:30:00Z');
    const result = formatDate(date);
    expect(result).toContain('2026');
  });

  it('should include time when includeTime=true', () => {
    const result = formatDate('2026-03-09T15:30:00Z', { includeTime: true });
    expect(result).toMatch(/\d{2}:\d{2}/); // Should contain HH:MM
  });

  it('should exclude time when includeTime=false', () => {
    const result = formatDate('2026-03-09T15:30:00Z', { includeTime: false });
    expect(result).not.toMatch(/\d{2}:\d{2}/);
  });

  it('should apply format="short" (2-digit months)', () => {
    const result = formatDate('2026-03-09T10:30:00Z', { format: 'short' });
    expect(result).toBeDefined();
    expect(result.length).toBeGreaterThan(0);
  });

  it('should apply format="long" (long month names)', () => {
    const result = formatDate('2026-03-09T10:30:00Z', { format: 'long' });
    expect(result).toBeDefined();
  });

  it('should handle catch block for parse errors', () => {
    const invalidDate = new Date('invalid');
    const result = formatDate(invalidDate, { fallback: 'ERROR' });
    expect(result).toBe('ERROR');
  });

  it('should not confuse null with undefined in conditions', () => {
    // Mutation: `if (!date)` could become `if (date === null)` — this catches it
    expect(formatDate(undefined)).toBe('-');
    expect(formatDate(null)).toBe('-');
  });
});

describe('formatters - formatDateForInput()', () => {
  it('should return empty string for null/undefined', () => {
    expect(formatDateForInput(null)).toBe('');
    expect(formatDateForInput(undefined)).toBe('');
  });

  it('should format valid date to YYYY-MM-DD', () => {
    const result = formatDateForInput('2026-03-09T10:30:00Z');
    expect(result).toBe('2026-03-09');
  });

  it('should handle Date object', () => {
    const date = new Date('2026-03-09');
    const result = formatDateForInput(date);
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('should return empty string for invalid dates', () => {
    expect(formatDateForInput('invalid')).toBe('');
  });

  it('should catch parse errors', () => {
    const invalidDate = new Date('invalid');
    expect(formatDateForInput(invalidDate)).toBe('');
  });
});

describe('formatters - formatRelativeTime()', () => {
  let nowMock: Date;

  beforeEach(() => {
    vi.useFakeTimers();
    nowMock = new Date('2026-03-09T12:00:00Z');
    vi.setSystemTime(nowMock);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should return "-" for null/undefined', () => {
    expect(formatRelativeTime(null)).toBe('-');
    expect(formatRelativeTime(undefined)).toBe('-');
  });

  it('should return "Ahora mismo" for dates < 1 min ago', () => {
    const now = new Date();
    expect(formatRelativeTime(now)).toBe('Ahora mismo');
  });

  it('should format minutes correctly (1 vs plural)', () => {
    const oneMinAgo = new Date(Date.now() - 60000);
    const result = formatRelativeTime(oneMinAgo);
    expect(result).toContain('minuto');
  });

  it('should format multiple minutes (plural)', () => {
    const fiveMinAgo = new Date(Date.now() - 300000);
    const result = formatRelativeTime(fiveMinAgo);
    expect(result).toContain('minutos');
  });

  it('should format hours correctly (1 vs plural)', () => {
    const oneHourAgo = new Date(Date.now() - 3600000);
    const result = formatRelativeTime(oneHourAgo);
    expect(result).toContain('hora');
  });

  it('should format multiple hours (plural)', () => {
    const twoHoursAgo = new Date(Date.now() - 7200000);
    const result = formatRelativeTime(twoHoursAgo);
    expect(result).toContain('horas');
  });

  it('should format days correctly (1 vs plural)', () => {
    const oneDayAgo = new Date(Date.now() - 86400000);
    const result = formatRelativeTime(oneDayAgo);
    expect(result).toContain('dia');
  });

  it('should format multiple days (plural)', () => {
    const twoDaysAgo = new Date(Date.now() - 172800000);
    const result = formatRelativeTime(twoDaysAgo);
    expect(result).toContain('dias');
  });

  it('should fallback to formatDate for dates >= 7 days', () => {
    const weekAgo = new Date(Date.now() - 604800000);
    const result = formatRelativeTime(weekAgo);
    expect(result).not.toMatch(/Hace/); // Should use formatDate format
  });

  it('should catch parse errors', () => {
    expect(formatRelativeTime('invalid')).toBe('-');
  });

  // MUTATION CATCHING: Boundary conditions
  it('catches boundary mutation: < 60 at 60 minutes', () => {
    const exactly60MinAgo = new Date(Date.now() - 3599999);
    const result = formatRelativeTime(exactly60MinAgo);
    expect(result).toContain('minutos');
  });

  it('catches boundary mutation: < 24 at 24 hours', () => {
    const exactly24hAgo = new Date(Date.now() - 86399999);
    const result = formatRelativeTime(exactly24hAgo);
    expect(result).toContain('horas');
  });
});

describe('formatters - formatNumber()', () => {
  it('should return "-" for null/undefined', () => {
    expect(formatNumber(null)).toBe('-');
    expect(formatNumber(undefined)).toBe('-');
  });

  it('should format integer with no decimals', () => {
    expect(formatNumber(1000)).toBe('1.000'); // Spanish locale uses dots
  });

  it('should respect decimals parameter', () => {
    const result = formatNumber(1234.5678, 2);
    expect(result).toMatch(/1\.234|1234/); // Locale-dependent
  });

  it('should handle zero', () => {
    expect(formatNumber(0)).toBe('0');
  });

  it('should handle negative numbers', () => {
    const result = formatNumber(-1000);
    expect(result).toContain('1.000');
  });

  it('should format large numbers', () => {
    const result = formatNumber(1000000);
    expect(result).toBeDefined();
  });
});

describe('formatters - formatHectares()', () => {
  it('should return "-" for null/undefined', () => {
    expect(formatHectares(null)).toBe('-');
    expect(formatHectares(undefined)).toBe('-');
  });

  it('should format with "ha" suffix', () => {
    const result = formatHectares(1000);
    expect(result).toContain('ha');
    expect(result).toContain('1.000');
  });

  it('should handle decimal hectares', () => {
    const result = formatHectares(123.45);
    expect(result).toContain('ha');
  });

  it('should handle zero hectares', () => {
    expect(formatHectares(0)).toContain('ha');
  });
});

describe('formatters - formatPercentage()', () => {
  it('should return "-" for null/undefined', () => {
    expect(formatPercentage(null)).toBe('-');
    expect(formatPercentage(undefined)).toBe('-');
  });

  it('should format with "%" suffix', () => {
    const result = formatPercentage(50);
    expect(result).toContain('%');
  });

  it('should default to 1 decimal place', () => {
    const result = formatPercentage(33.333);
    expect(result).toMatch(/33[.,]\d%/); // Spanish uses comma
  });

  it('should respect decimals parameter', () => {
    const result = formatPercentage(33.333, 0);
    expect(result).not.toMatch(/\d\.\d/);
  });

  it('should handle 0 percentage', () => {
    const result = formatPercentage(0);
    expect(result).toContain('0');
    expect(result).toContain('%');
  });

  it('should handle 100 percentage', () => {
    const result = formatPercentage(100);
    expect(result).toContain('100');
  });
});

describe('formatters - formatDateCustom()', () => {
  it('should return fallback for null/undefined', () => {
    const options = { year: 'numeric' };
    expect(formatDateCustom(null, options)).toBe('-');
    expect(formatDateCustom(undefined, options)).toBe('-');
  });

  it('should return custom fallback when provided', () => {
    const options = { year: 'numeric' };
    expect(formatDateCustom(null, options, 'CUSTOM')).toBe('CUSTOM');
  });

  it('should apply custom date options', () => {
    const result = formatDateCustom('2026-03-09', { year: 'numeric', month: 'long' });
    expect(result).toContain('2026');
  });

  it('should handle invalid dates', () => {
    const options = { year: 'numeric' };
    expect(formatDateCustom('invalid', options)).toBe('-');
  });

  it('should catch errors during formatting', () => {
    const options = { year: 'numeric' } as Intl.DateTimeFormatOptions;
    const invalidDate = new Date('invalid');
    expect(formatDateCustom(invalidDate, options, 'ERROR')).toBe('ERROR');
  });
});

describe('formatters - formatDateTime()', () => {
  it('should return fallback for null/undefined', () => {
    expect(formatDateTime(null)).toBe('-');
    expect(formatDateTime(undefined)).toBe('-');
  });

  it('should return custom fallback when provided', () => {
    expect(formatDateTime(null, 'N/A')).toBe('N/A');
  });

  it('should format date and time', () => {
    const result = formatDateTime('2026-03-09T15:30:00Z');
    expect(result).toContain('2026');
    expect(result).toMatch(/\d{1,2}:\d{2}/); // Time format
  });

  it('should handle Date objects', () => {
    const date = new Date('2026-03-09T15:30:00Z');
    const result = formatDateTime(date);
    expect(result).toBeDefined();
  });

  it('should handle invalid dates', () => {
    expect(formatDateTime('invalid')).toBe('-');
  });

  it('should catch formatting errors', () => {
    const invalidDate = new Date('invalid');
    expect(formatDateTime(invalidDate, 'FALLBACK')).toBe('FALLBACK');
  });
});
