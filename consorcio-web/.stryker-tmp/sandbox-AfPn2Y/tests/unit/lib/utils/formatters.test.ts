/**
 * Mutation tests for formatter utility functions.
 * Tests boundary conditions, parameter handling, and edge cases
 * to catch arithmetic, conditional, and return value mutations.
 */
// @ts-nocheck


import { describe, it, expect } from 'vitest';
import { formatDate, formatDateForInput, formatRelativeTime } from '@/lib/formatters';
import {
  dateVariations,
  commonStrings,
  currencyTestCases,
  truncateTestCases,
} from './setup';

// ===========================================
// formatDate Tests
// ===========================================

describe('formatDate', () => {
  it('should format valid date strings correctly', () => {
    const result = formatDate('2026-03-09T10:00:00Z', { format: 'medium' });
    expect(result).toContain('2026');
    expect(result).toContain('9');
  });

  it('should handle Date objects', () => {
    const date = new Date('2026-03-09T10:00:00Z');
    const result = formatDate(date);
    expect(result).toContain('2026');
    expect(typeof result).toBe('string');
  });

  it('should return fallback for null/undefined', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate(undefined)).toBe('-');
    expect(formatDate(null, { fallback: 'N/A' })).toBe('N/A');
  });

  it('should return fallback for empty string', () => {
    expect(formatDate('')).toBe('-');
  });

  it('should return fallback for invalid date', () => {
    expect(formatDate('invalid-date')).toBe('-');
    expect(formatDate(new Date('invalid'))).toBe('-');
  });

  it('should include time when requested', () => {
    const date = new Date('2026-03-09T14:30:00Z');
    const result = formatDate(date, { includeTime: true });
    // Should contain time component (format may vary by locale)
    expect(result.length).toBeGreaterThan(10);
  });

  it('should not include time by default', () => {
    const date = new Date('2026-03-09T14:30:00Z');
    const result = formatDate(date, { includeTime: false });
    // Should be shorter than with time
    expect(result.length).toBeLessThanOrEqual(20);
  });

  it('should handle different format options', () => {
    const date = new Date('2026-03-09T10:00:00Z');
    const short = formatDate(date, { format: 'short' });
    const long = formatDate(date, { format: 'long' });

    // Both should be valid strings
    expect(typeof short).toBe('string');
    expect(typeof long).toBe('string');
    expect(short.length).toBeGreaterThan(0);
    expect(long.length).toBeGreaterThan(0);
  });

  describe.each(Object.entries(dateVariations))('date variation: %s', (key, date) => {
    it(`should format ${key} without throwing`, () => {
      expect(() => formatDate(date)).not.toThrow();
    });
  });
});

// ===========================================
// formatDateForInput Tests
// ===========================================

describe('formatDateForInput', () => {
  it('should format date to YYYY-MM-DD', () => {
    const date = new Date('2026-03-09T10:00:00Z');
    const result = formatDateForInput(date);
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(result).toContain('2026');
  });

  it('should handle string date input', () => {
    const result = formatDateForInput('2026-03-09T10:00:00Z');
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('should return empty string for null/undefined', () => {
    expect(formatDateForInput(null)).toBe('');
    expect(formatDateForInput(undefined)).toBe('');
  });

  it('should return empty string for invalid date', () => {
    expect(formatDateForInput('invalid')).toBe('');
    expect(formatDateForInput(new Date('invalid'))).toBe('');
  });

  it('should handle edge case dates (epoch, far future)', () => {
    const epoch = new Date('1970-01-01T00:00:00Z');
    expect(formatDateForInput(epoch)).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    const future = new Date('2099-12-31T23:59:59Z');
    expect(formatDateForInput(future)).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

// ===========================================
// formatRelativeTime Tests
// ===========================================

describe('formatRelativeTime', () => {
  it('should return dash for null/undefined', () => {
    expect(formatRelativeTime(null)).toBe('-');
    expect(formatRelativeTime(undefined)).toBe('-');
  });

  it('should return dash for empty string', () => {
    expect(formatRelativeTime('')).toBe('-');
  });

  it('should handle valid dates without throwing', () => {
    const now = new Date();
    expect(() => formatRelativeTime(now)).not.toThrow();
    const result = formatRelativeTime(now);
    expect(typeof result).toBe('string');
  });

  it('should handle past dates', () => {
    const pastDate = new Date();
    pastDate.setHours(pastDate.getHours() - 2);
    expect(() => formatRelativeTime(pastDate)).not.toThrow();
  });

  it('should handle invalid dates', () => {
    expect(formatRelativeTime('not-a-date')).toBe('-');
  });
});

// ===========================================
// Edge Case Parametrized Tests
// ===========================================

describe('format functions - edge cases', () => {
  describe.each(commonStrings)('with common string: "%s"', (str) => {
    it('should not throw on formatDate with string input', () => {
      expect(() => formatDate(str)).not.toThrow();
    });

    it('should not throw on formatDateForInput with string input', () => {
      expect(() => formatDateForInput(str)).not.toThrow();
    });

    it('should not throw on formatRelativeTime with string input', () => {
      expect(() => formatRelativeTime(str)).not.toThrow();
    });
  });
});

// ===========================================
// Return Value Consistency Tests
// ===========================================

describe('format functions - return value consistency', () => {
  it('formatDate always returns a string', () => {
    const testValues = [
      null,
      undefined,
      '',
      'invalid',
      new Date(),
      '2026-03-09T10:00:00Z',
    ];
    testValues.forEach((val) => {
      expect(typeof formatDate(val)).toBe('string');
    });
  });

  it('formatDateForInput always returns a string', () => {
    const testValues = [
      null,
      undefined,
      '',
      'invalid',
      new Date(),
      '2026-03-09T10:00:00Z',
    ];
    testValues.forEach((val) => {
      expect(typeof formatDateForInput(val)).toBe('string');
    });
  });

  it('formatRelativeTime always returns a string', () => {
    const testValues = [
      null,
      undefined,
      '',
      'invalid',
      new Date(),
      '2026-03-09T10:00:00Z',
    ];
    testValues.forEach((val) => {
      expect(typeof formatRelativeTime(val)).toBe('string');
    });
  });
});

// ===========================================
// Default Value Tests
// ===========================================

describe('default option values', () => {
  it('formatDate defaults includeTime to false', () => {
    const date = new Date('2026-03-09T14:30:00Z');
    const explicit = formatDate(date, { includeTime: false });
    const implicit = formatDate(date);
    expect(explicit).toBe(implicit);
  });

  it('formatDate defaults format to medium', () => {
    const date = new Date('2026-03-09T10:00:00Z');
    const explicit = formatDate(date, { format: 'medium' });
    const implicit = formatDate(date);
    expect(explicit).toBe(implicit);
  });

  it('formatDate defaults fallback to dash', () => {
    expect(formatDate(null)).toBe('-');
  });
});
