/**
 * Unit tests for src/lib/formatters.ts
 *
 * Assertions pin es-AR + the exact Intl options the production helpers use.
 * Loose toBeDefined / length checks left mutants (empty locale, swapped
 * month format, emptied includeTime block) alive.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  formatDate,
  formatDateForInput,
  formatHectares,
  formatNumber,
  formatPercentage,
  formatRelativeTime,
  formatDateCustom,
  formatDateTime,
} from '../../src/lib/formatters';

const SAMPLE = new Date(2024, 0, 15, 10, 30, 0);

function localeDate(date: Date, options: Intl.DateTimeFormatOptions): string {
  return date.toLocaleDateString('es-AR', options);
}

function spyLocaleDateString() {
  return vi.spyOn(Date.prototype, 'toLocaleDateString');
}

function spyLocaleString() {
  return vi.spyOn(Date.prototype, 'toLocaleString');
}

function spyNumberLocaleString() {
  return vi.spyOn(Number.prototype, 'toLocaleString');
}

describe('formatters', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('formatDate', () => {
    it('formats a Date with medium month (default)', () => {
      expect(formatDate(SAMPLE)).toBe(
        localeDate(SAMPLE, { year: 'numeric', month: 'short', day: 'numeric' }),
      );
    });

    it('formats a date string the same as the equivalent Date', () => {
      const iso = SAMPLE.toISOString();
      expect(formatDate(iso)).toBe(formatDate(new Date(iso)));
    });

    it('returns fallback for invalid date string', () => {
      expect(formatDate('invalid-date')).toBe('-');
    });

    it('returns fallback for null and undefined', () => {
      expect(formatDate(null)).toBe('-');
      expect(formatDate(undefined)).toBe('-');
    });

    it('uses a custom fallback', () => {
      expect(formatDate(null, { fallback: 'N/A' })).toBe('N/A');
    });

    it('distinguishes short, medium, and long month formats', () => {
      const short = formatDate(SAMPLE, { format: 'short' });
      const medium = formatDate(SAMPLE, { format: 'medium' });
      const long = formatDate(SAMPLE, { format: 'long' });
      expect(short).toBe(
        localeDate(SAMPLE, { year: 'numeric', month: '2-digit', day: 'numeric' }),
      );
      expect(medium).toBe(
        localeDate(SAMPLE, { year: 'numeric', month: 'short', day: 'numeric' }),
      );
      expect(long).toBe(
        localeDate(SAMPLE, { year: 'numeric', month: 'long', day: 'numeric' }),
      );
      expect(short).not.toBe(medium);
      expect(medium).not.toBe(long);
      expect(long).toMatch(/enero/i);
    });

    it('passes es-AR and the medium month options to Intl', () => {
      const spy = spyLocaleDateString();
      formatDate(SAMPLE);
      expect(spy).toHaveBeenCalledWith(
        'es-AR',
        expect.objectContaining({
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        }),
      );
      expect(spy.mock.calls[0]?.[1]).not.toHaveProperty('hour');
    });

    it('passes 2-digit month for short and long month for long', () => {
      const spy = spyLocaleDateString();
      formatDate(SAMPLE, { format: 'short' });
      formatDate(SAMPLE, { format: 'long' });
      expect(spy).toHaveBeenNthCalledWith(
        1,
        'es-AR',
        expect.objectContaining({ month: '2-digit' }),
      );
      expect(spy).toHaveBeenNthCalledWith(
        2,
        'es-AR',
        expect.objectContaining({ month: 'long' }),
      );
    });

    it('adds hour and minute when includeTime is true', () => {
      const withTime = formatDate(SAMPLE, { includeTime: true });
      const withoutTime = formatDate(SAMPLE);
      expect(withTime).toBe(
        localeDate(SAMPLE, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        }),
      );
      expect(withTime).not.toBe(withoutTime);
      const spy = spyLocaleDateString();
      formatDate(SAMPLE, { includeTime: true });
      expect(spy).toHaveBeenCalledWith(
        'es-AR',
        expect.objectContaining({ hour: '2-digit', minute: '2-digit' }),
      );
    });

    it('returns fallback when getTime throws', () => {
      const exploding = {
        getTime(): number {
          throw new Error('boom');
        },
      } as unknown as Date;
      expect(formatDate(exploding)).toBe('-');
      expect(formatDate(exploding, { fallback: 'N/A' })).toBe('N/A');
    });
  });

  describe('formatDateForInput', () => {
    it('formats a Date to YYYY-MM-DD', () => {
      expect(formatDateForInput(new Date('2024-01-15T00:00:00.000Z'))).toBe('2024-01-15');
    });

    it('formats a date string to YYYY-MM-DD', () => {
      expect(formatDateForInput('2024-06-20T10:30:00Z')).toBe('2024-06-20');
    });

    it('returns empty string for null, undefined, and invalid dates', () => {
      expect(formatDateForInput(null)).toBe('');
      expect(formatDateForInput(undefined)).toBe('');
      expect(formatDateForInput('invalid')).toBe('');
    });

    it('returns empty string when getTime throws', () => {
      const exploding = {
        getTime(): number {
          throw new Error('boom');
        },
      } as unknown as Date;
      expect(formatDateForInput(exploding)).toBe('');
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

    it('returns "Ahora mismo" under one minute', () => {
      expect(formatRelativeTime('2024-01-15T12:00:00Z')).toBe('Ahora mismo');
      expect(formatRelativeTime('2024-01-15T11:59:01Z')).toBe('Ahora mismo');
    });

    it('formats one minute vs many minutes', () => {
      expect(formatRelativeTime('2024-01-15T11:59:00Z')).toBe('Hace 1 minuto');
      expect(formatRelativeTime('2024-01-15T11:55:00Z')).toBe('Hace 5 minutos');
    });

    it('formats one hour vs many hours', () => {
      expect(formatRelativeTime('2024-01-15T11:00:00Z')).toBe('Hace 1 hora');
      expect(formatRelativeTime('2024-01-15T09:00:00Z')).toBe('Hace 3 horas');
    });

    it('formats one day vs many days', () => {
      expect(formatRelativeTime('2024-01-14T12:00:00Z')).toBe('Hace 1 dia');
      expect(formatRelativeTime('2024-01-12T12:00:00Z')).toBe('Hace 3 dias');
    });

    it('falls back to medium date after six days', () => {
      const older = new Date('2024-01-01T12:00:00Z');
      expect(formatRelativeTime(older)).toBe(formatDate(older, { format: 'medium' }));
    });

    it('uses formatDate at exactly seven days, not the day phrase', () => {
      const exactlySeven = new Date('2024-01-08T12:00:00Z');
      expect(formatRelativeTime(exactlySeven)).toBe(
        formatDate(exactlySeven, { format: 'medium' }),
      );
      expect(formatRelativeTime(exactlySeven)).not.toMatch(/Hace 7 dias/);
    });

    it('returns "-" for null, undefined, and invalid dates', () => {
      expect(formatRelativeTime(null)).toBe('-');
      expect(formatRelativeTime(undefined)).toBe('-');
      expect(formatRelativeTime('invalid')).toBe('-');
    });

    it('returns "-" when getTime throws', () => {
      const exploding = {
        getTime(): number {
          throw new Error('boom');
        },
      } as unknown as Date;
      expect(formatRelativeTime(exploding)).toBe('-');
    });
  });

  describe('formatNumber', () => {
    it('asks Intl for es-AR with matching fraction digits', () => {
      const spy = spyNumberLocaleString();
      formatNumber(1234.5, 2);
      expect(spy).toHaveBeenCalledWith('es-AR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    });

    it('formats integers with es-AR grouping', () => {
      expect(formatNumber(1234567)).toBe(
        (1234567).toLocaleString('es-AR', {
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        }),
      );
    });

    it('keeps the requested number of decimals', () => {
      expect(formatNumber(1234.5678, 2)).toBe(
        (1234.5678).toLocaleString('es-AR', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }),
      );
      expect(formatNumber(1234.5678, 0)).not.toBe(formatNumber(1234.5678, 2));
    });

    it('formats zero as 0', () => {
      expect(formatNumber(0)).toBe('0');
    });

    it('returns "-" for null and undefined', () => {
      expect(formatNumber(null)).toBe('-');
      expect(formatNumber(undefined)).toBe('-');
    });
  });

  describe('formatHectares', () => {
    it('appends a space and ha to the formatted number', () => {
      expect(formatHectares(1234)).toBe(`${formatNumber(1234)} ha`);
    });

    it('formats zero hectares', () => {
      expect(formatHectares(0)).toBe('0 ha');
    });

    it('returns "-" for null and undefined', () => {
      expect(formatHectares(null)).toBe('-');
      expect(formatHectares(undefined)).toBe('-');
    });
  });

  describe('formatPercentage', () => {
    it('uses one decimal by default and a percent suffix', () => {
      expect(formatPercentage(50)).toBe(`${formatNumber(50, 1)}%`);
    });

    it('honours an explicit decimal count', () => {
      expect(formatPercentage(33.333, 2)).toBe(`${formatNumber(33.333, 2)}%`);
      expect(formatPercentage(33.333, 2)).toContain('33,33');
    });

    it('formats zero and 100', () => {
      expect(formatPercentage(0)).toBe(`${formatNumber(0, 1)}%`);
      expect(formatPercentage(100)).toBe(`${formatNumber(100, 1)}%`);
    });

    it('returns "-" for null and undefined', () => {
      expect(formatPercentage(null)).toBe('-');
      expect(formatPercentage(undefined)).toBe('-');
    });
  });

  describe('formatDateCustom', () => {
    const longOpts: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    };

    it('forwards options to es-AR', () => {
      expect(formatDateCustom(SAMPLE, longOpts)).toBe(localeDate(SAMPLE, longOpts));
      expect(formatDateCustom(SAMPLE, longOpts)).toMatch(/enero/i);
    });

    it('formats a Date object', () => {
      const opts: Intl.DateTimeFormatOptions = {
        year: '2-digit',
        month: '2-digit',
        day: '2-digit',
      };
      expect(formatDateCustom(SAMPLE, opts)).toBe(localeDate(SAMPLE, opts));
    });

    it('returns fallback for null, undefined, and invalid dates', () => {
      expect(formatDateCustom(null, { year: 'numeric' })).toBe('-');
      expect(formatDateCustom(undefined, { year: 'numeric' })).toBe('-');
      expect(formatDateCustom('invalid', { year: 'numeric' })).toBe('-');
    });

    it('uses a custom fallback', () => {
      expect(formatDateCustom(null, { year: 'numeric' }, 'N/A')).toBe('N/A');
    });

    it('returns fallback when getTime throws', () => {
      const exploding = {
        getTime(): number {
          throw new Error('boom');
        },
      } as unknown as Date;
      expect(formatDateCustom(exploding, longOpts)).toBe('-');
    });
  });

  describe('formatDateTime', () => {
    it('formats with es-AR toLocaleString', () => {
      const spy = spyLocaleString();
      expect(formatDateTime(SAMPLE)).toBe(SAMPLE.toLocaleString('es-AR'));
      expect(spy).toHaveBeenCalledWith('es-AR');
    });

    it('formats a date string the same as the equivalent Date', () => {
      const iso = SAMPLE.toISOString();
      expect(formatDateTime(iso)).toBe(formatDateTime(new Date(iso)));
    });

    it('returns fallback for null, undefined, and invalid dates', () => {
      expect(formatDateTime(null)).toBe('-');
      expect(formatDateTime(undefined)).toBe('-');
      expect(formatDateTime('invalid-date')).toBe('-');
    });

    it('uses a custom fallback', () => {
      expect(formatDateTime(null, 'Sin fecha')).toBe('Sin fecha');
    });

    it('returns fallback when getTime throws', () => {
      const exploding = {
        getTime(): number {
          throw new Error('boom');
        },
      } as unknown as Date;
      expect(formatDateTime(exploding)).toBe('-');
    });
  });
});
