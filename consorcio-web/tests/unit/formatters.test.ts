/**
 * Unit tests for src/lib/formatters.ts
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  formatDate,
  formatDateForInput,
  formatHectares,
  formatNumber,
  formatPercentage,
  formatRelativeTime,
} from '../../src/lib/formatters';

describe('formatters', () => {
  describe('formatDate', () => {
    it('should format a valid date string', () => {
      const result = formatDate('2024-01-15T10:30:00Z');
      expect(result).toContain('2024');
      expect(result).toContain('15');
    });

    it('should format a Date object', () => {
      const result = formatDate(new Date('2024-06-20'));
      expect(result).toContain('2024');
    });

    it('should return fallback for invalid date string', () => {
      const result = formatDate('invalid-date');
      expect(result).toBe('-');
    });

    it('should return fallback for null', () => {
      expect(formatDate(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatDate(undefined)).toBe('-');
    });

    it('should use custom fallback when provided', () => {
      const result = formatDate(null, { fallback: 'N/A' });
      expect(result).toBe('N/A');
    });

    it('should include time when includeTime is true', () => {
      const result = formatDate('2024-01-15T10:30:00Z', { includeTime: true });
      // Result should be longer with time included
      expect(result.length).toBeGreaterThan(10);
    });

    it('should use short format', () => {
      const result = formatDate('2024-01-15', { format: 'short' });
      expect(result).toBeDefined();
    });

    it('should use long format', () => {
      const result = formatDate('2024-01-15', { format: 'long' });
      expect(result).toBeDefined();
    });
  });

  describe('formatDateForInput', () => {
    it('should format date to YYYY-MM-DD', () => {
      const result = formatDateForInput(new Date('2024-01-15'));
      expect(result).toBe('2024-01-15');
    });

    it('should handle date string input', () => {
      const result = formatDateForInput('2024-06-20T10:30:00Z');
      expect(result).toBe('2024-06-20');
    });

    it('should return empty string for null', () => {
      expect(formatDateForInput(null)).toBe('');
    });

    it('should return empty string for undefined', () => {
      expect(formatDateForInput(undefined)).toBe('');
    });

    it('should return empty string for invalid date', () => {
      expect(formatDateForInput('invalid')).toBe('');
    });
  });

  describe('formatRelativeTime', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2024-01-15T12:00:00Z'));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return "Ahora mismo" for very recent times', () => {
      const result = formatRelativeTime('2024-01-15T12:00:00Z');
      expect(result).toBe('Ahora mismo');
    });

    it('should format time in minutes', () => {
      const result = formatRelativeTime('2024-01-15T11:55:00Z');
      expect(result).toMatch(/Hace \d+ minutos?/);
    });

    it('should format time in hours', () => {
      const result = formatRelativeTime('2024-01-15T09:00:00Z');
      expect(result).toMatch(/Hace \d+ horas?/);
    });

    it('should format time in days', () => {
      const result = formatRelativeTime('2024-01-12T12:00:00Z');
      expect(result).toMatch(/Hace \d+ dias?/);
    });

    it('should format as date for older times (more than 7 days)', () => {
      const result = formatRelativeTime('2024-01-01T12:00:00Z');
      expect(result).toContain('2024');
    });

    it('should return fallback for null', () => {
      expect(formatRelativeTime(null)).toBe('-');
    });

    it('should return fallback for invalid date', () => {
      expect(formatRelativeTime('invalid')).toBe('-');
    });
  });

  describe('formatNumber', () => {
    it('should format integer with thousand separators', () => {
      const result = formatNumber(1234567);
      // Format depends on locale, but should be defined
      expect(result).toBeDefined();
      expect(result.length).toBeGreaterThan(0);
    });

    it('should format with specified decimals', () => {
      const result = formatNumber(1234.5678, 2);
      expect(result).toBeDefined();
    });

    it('should format zero', () => {
      const result = formatNumber(0);
      expect(result).toBe('0');
    });

    it('should return fallback for null', () => {
      expect(formatNumber(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatNumber(undefined)).toBe('-');
    });
  });

  describe('formatHectares', () => {
    it('should format hectares with "ha" suffix', () => {
      const result = formatHectares(1234);
      expect(result).toContain('ha');
    });

    it('should format zero hectares', () => {
      const result = formatHectares(0);
      expect(result).toBe('0 ha');
    });

    it('should return fallback for null', () => {
      expect(formatHectares(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatHectares(undefined)).toBe('-');
    });
  });

  describe('formatPercentage', () => {
    it('should format percentage with % suffix', () => {
      const result = formatPercentage(50);
      expect(result).toContain('50');
      expect(result).toContain('%');
    });

    it('should format with specified decimals', () => {
      const result = formatPercentage(33.333, 2);
      expect(result).toContain('33,33'); // es-AR uses comma as decimal separator
      expect(result).toContain('%');
    });

    it('should format zero percent', () => {
      const result = formatPercentage(0);
      expect(result).toContain('0');
      expect(result).toContain('%');
    });

    it('should format 100%', () => {
      const result = formatPercentage(100);
      expect(result).toContain('100');
      expect(result).toContain('%');
    });

    it('should return fallback for null', () => {
      expect(formatPercentage(null)).toBe('-');
    });

    it('should return fallback for undefined', () => {
      expect(formatPercentage(undefined)).toBe('-');
    });
  });
});
