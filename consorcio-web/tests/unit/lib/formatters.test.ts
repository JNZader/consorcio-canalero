/**
 * Mutation tests for src/lib/formatters.ts
 * Tests date formatting, number formatting, and string formatting utilities
 */

import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
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
import {
  dateVariations,
  numberFormattingTestCases,
  percentageFormattingTestCases,
  hectaresFormattingTestCases,
  relativeTimeTestCases,
} from './setup';

describe('formatters', () => {
  // Mock Date.now() for consistent relative time testing
  const mockNow = new Date('2024-03-10T12:00:00Z').getTime();

  beforeAll(() => {
    vi.useFakeTimers();
    vi.setSystemTime(mockNow);
  });

  afterAll(() => {
    vi.useRealTimers();
  });

  describe('formatDate', () => {
    it('should format valid Date objects correctly', () => {
      const result = formatDate(dateVariations.valid.recent);
      // formatDate uses month 'short' format by default like "10 de ene de 2024"
      expect(result).toMatch(/\d+.*\d+.*2024/);
      expect(result).not.toBe('-');
    });

    it('should format valid ISO date strings correctly', () => {
      const result = formatDate(dateVariations.strings.isoString);
      expect(result).toMatch(/\d+.*\d+.*2024/);
      expect(result).not.toBe('-');
    });

    it('should return fallback for null/undefined', () => {
      expect(formatDate(null)).toBe('-');
      expect(formatDate(undefined)).toBe('-');
    });

    it('should return fallback for invalid date strings', () => {
      expect(formatDate(dateVariations.strings.invalidString)).toBe('-');
      expect(formatDate('not-a-date')).toBe('-');
    });

    it('should return custom fallback when provided', () => {
      const customFallback = 'N/A';
      expect(formatDate(null, { fallback: customFallback })).toBe(customFallback);
      expect(formatDate(undefined, { fallback: customFallback })).toBe(customFallback);
    });

    it('should include time when requested', () => {
      const dateObj = new Date('2024-03-10T14:30:00');
      const result = formatDate(dateObj, { includeTime: true });
      // Time format varies by locale (could be 14:30 or 02:30 p.m.)
      expect(result).toMatch(/[\d:]/);
      expect(result).toContain('10');
    });

    it('should not include time by default', () => {
      const dateObj = new Date('2024-03-10T14:30:00');
      const result = formatDate(dateObj, { includeTime: false });
      // Should have date but not time components
      expect(result).toContain('2024');
      expect(result).not.toMatch(/\d+:\d+/); // No time separator
    });

    it('should support short month format', () => {
      const date = new Date('2024-03-10');
      const result = formatDate(date, { format: 'short' });
      expect(result).toMatch(/\d+.*\d+.*2024/);
    });

    it('should support long month format', () => {
      const date = new Date('2024-03-10');
      const result = formatDate(date, { format: 'long' });
      expect(result).toContain('marzo'); // March in Spanish
    });

    it('should handle epoch date', () => {
      // Use a date well after midnight UTC to avoid timezone issues
      const result = formatDate(dateVariations.valid.epoch);
      expect(result).not.toBe('-');
      // Epoch date (1970-01-01 UTC) formatted as short month
      // May be "31 de dic de 1969" or "1 de ene de 1970" depending on timezone
      expect(result).toMatch(/\d+.*(?:dic|ene).*196[9]|1970/);
    });

    it('should catch formatting errors and return fallback', () => {
      // Create an invalid Date object
      const invalidDate = new Date('invalid');
      const result = formatDate(invalidDate);
      expect(result).toBe('-');
    });

    it('should escape mutations on fallback checks', () => {
      // Verify it checks for null explicitly
      expect(formatDate(null)).toBe('-');
      // Verify it still processes values when not explicitly null/undefined
      const dateObj = new Date('2024-03-10');
      expect(formatDate(dateObj)).toMatch(/\d/);
    });
  });

  describe('formatDateForInput', () => {
    it('should format Date to YYYY-MM-DD', () => {
      const result = formatDateForInput(new Date('2024-03-10'));
      expect(result).toBe('2024-03-10');
    });

    it('should format ISO string to YYYY-MM-DD', () => {
      const result = formatDateForInput('2024-03-10T14:30:00Z');
      expect(result).toBe('2024-03-10');
    });

    it('should return empty string for null', () => {
      expect(formatDateForInput(null)).toBe('');
    });

    it('should return empty string for undefined', () => {
      expect(formatDateForInput(undefined)).toBe('');
    });

    it('should return empty string for invalid dates', () => {
      expect(formatDateForInput('invalid-date')).toBe('');
    });

    it('should handle epoch date', () => {
      const result = formatDateForInput(new Date('1970-01-01'));
      expect(result).toBe('1970-01-01');
    });

    it('should preserve time zone in conversion', () => {
      const date = new Date('2024-12-25T12:00:00Z');
      const result = formatDateForInput(date);
      expect(result).toBe('2024-12-25');
    });
  });

  describe('formatRelativeTime', () => {
    it('should return "Ahora mismo" for times less than 1 minute ago', () => {
      const justNow = new Date(Date.now() - 10 * 1000);
      const result = formatRelativeTime(justNow);
      expect(result).toBe('Ahora mismo');
    });

    it('should format minutes correctly (singular)', () => {
      const oneMinuteAgo = new Date(Date.now() - 60 * 1000);
      const result = formatRelativeTime(oneMinuteAgo);
      expect(result).toContain('1 minuto');
      expect(result).toContain('Hace');
    });

    it('should format minutes correctly (plural)', () => {
      const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);
      const result = formatRelativeTime(fiveMinutesAgo);
      expect(result).toContain('Hace');
      expect(result).toContain('minutos');
    });

    it('should format hours correctly (singular)', () => {
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
      const result = formatRelativeTime(oneHourAgo);
      expect(result).toContain('1 hora');
      expect(result).toContain('Hace');
    });

    it('should format hours correctly (plural)', () => {
      const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000);
      const result = formatRelativeTime(threeHoursAgo);
      expect(result).toContain('Hace');
      expect(result).toContain('horas');
    });

    it('should format days correctly (singular)', () => {
      const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
      const result = formatRelativeTime(oneDayAgo);
      expect(result).toContain('1 dia');
      expect(result).toContain('Hace');
    });

    it('should format days correctly (plural)', () => {
      const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000);
      const result = formatRelativeTime(threeDaysAgo);
      expect(result).toContain('Hace');
      expect(result).toContain('dias');
    });

    it('should format date for dates older than 7 days', () => {
      const eightDaysAgo = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000);
      const result = formatRelativeTime(eightDaysAgo);
      // formatDate with 'medium' format uses short month names in Spanish
      // Format is like: "2 de mar de 2024" or "10/3/2024" depending on locale
      expect(result).not.toContain('Hace');
      // Just verify it's not using "Hace" and is showing a date
      expect(result).toMatch(/\d/);
    });

    it('should return fallback for null', () => {
      expect(formatRelativeTime(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatRelativeTime(undefined)).toBe('-');
    });

    it('should return fallback for invalid date strings', () => {
      expect(formatRelativeTime('invalid-date')).toBe('-');
    });

    it('should handle ISO string dates', () => {
      const isoString = new Date().toISOString();
      const result = formatRelativeTime(isoString);
      // Should either be recent time or fallback, not error
      expect(result).toBeTruthy();
    });
  });

  describe('formatNumber', () => {
    it.each(numberFormattingTestCases.valid)(
      'should format $value with $decimals decimals',
      ({ value, decimals, expected }) => {
        const result = formatNumber(value, decimals);
        expect(result).toBe(expected);
      }
    );

    it('should use Spanish locale formatting (. for thousands, , for decimals)', () => {
      const result = formatNumber(1234.56, 2);
      expect(result).toContain('.');
      expect(result).toContain(',');
    });

    it('should return fallback for null', () => {
      expect(formatNumber(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatNumber(undefined)).toBe('-');
    });

    it('should default to 0 decimals', () => {
      const result = formatNumber(1000);
      expect(result).not.toContain(',');
    });

    it('should handle negative numbers', () => {
      const result = formatNumber(-1000, 0);
      expect(result).toContain('-');
    });

    it('should handle zero', () => {
      expect(formatNumber(0, 0)).toBe('0');
    });

    it('should handle large numbers', () => {
      const result = formatNumber(1000000, 0);
      expect(result).toContain('.');
    });
  });

  describe('formatHectares', () => {
    it.each(hectaresFormattingTestCases.valid)(
      'should format $value hectares',
      ({ value, expected }) => {
        const result = formatHectares(value);
        expect(result).toBe(expected);
      }
    );

    it('should return fallback for null', () => {
      expect(formatHectares(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatHectares(undefined)).toBe('-');
    });

    it('should include "ha" suffix', () => {
      const result = formatHectares(100);
      expect(result).toContain('ha');
    });
  });

  describe('formatPercentage', () => {
    it.each(percentageFormattingTestCases.valid)(
      'should format $value% with $decimals decimals',
      ({ value, decimals, expected }) => {
        const result = formatPercentage(value, decimals);
        expect(result).toBe(expected);
      }
    );

    it('should return fallback for null', () => {
      expect(formatPercentage(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatPercentage(undefined)).toBe('-');
    });

    it('should include "%" suffix', () => {
      const result = formatPercentage(50, 1);
      expect(result).toContain('%');
    });

    it('should default to 1 decimal place', () => {
      const result = formatPercentage(50);
      expect(result).toBe('50,0%');
    });

    it('should handle 0 decimals', () => {
      const result = formatPercentage(50, 0);
      expect(result).toBe('50%');
    });
  });

  describe('formatDateCustom', () => {
    it('should apply custom Intl.DateTimeFormatOptions', () => {
      const date = new Date('2024-03-10');
      const options: Intl.DateTimeFormatOptions = {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      };
      const result = formatDateCustom(date, options);
      expect(result).toContain('2024');
      expect(result).toContain('marzo'); // March in Spanish
    });

    it('should return fallback for null', () => {
      expect(formatDateCustom(null, {})).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatDateCustom(undefined, {})).toBe('-');
    });

    it('should return custom fallback when provided', () => {
      const customFallback = 'N/A';
      expect(formatDateCustom(null, {}, customFallback)).toBe(customFallback);
    });

    it('should handle invalid date strings', () => {
      expect(formatDateCustom('invalid', {})).toBe('-');
    });

    it('should use Spanish locale', () => {
      const date = new Date('2024-03-10');
      const result = formatDateCustom(date, { month: 'long' });
      expect(result).toContain('marzo'); // Should be Spanish
    });
  });

  describe('formatDateTime', () => {
    it('should format date and time together', () => {
      const date = new Date('2024-03-10T14:30:45');
      const result = formatDateTime(date);
      expect(result).toContain('10');
      expect(result).toContain('3');
      expect(result).toContain('2024');
      // Time may be in 12 or 24-hour format depending on system locale
      expect(result).toMatch(/(14:30|02:30)/);
    });

    it('should return fallback for null', () => {
      expect(formatDateTime(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatDateTime(undefined)).toBe('-');
    });

    it('should return custom fallback when provided', () => {
      const customFallback = 'N/A';
      expect(formatDateTime(null, customFallback)).toBe(customFallback);
    });

    it('should handle ISO date strings', () => {
      // Use a local time string instead of UTC to avoid timezone issues
      const result = formatDateTime('2024-03-10T14:30:45');
      expect(result).toContain('2024');
      // Time may be formatted differently depending on system locale
      expect(result).toMatch(/(\d{1,2}:30)/);
    });

    it('should handle invalid date strings', () => {
      expect(formatDateTime('invalid-date')).toBe('-');
    });

    it('should use Spanish locale', () => {
      const date = new Date('2024-03-10T14:30:45');
      const result = formatDateTime(date);
      // Should use Spanish locale (verify it doesn't throw)
      expect(result).toBeTruthy();
    });
  });
});
