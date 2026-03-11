/**
 * Tests for validators utility
 * Coverage target: 100% (all validation logic)
 */
// @ts-nocheck


import { describe, it, expect } from 'vitest';
import {
  MAX_EMAIL_LENGTH,
  isValidEmail,
  validateEmail,
  isValidPhone,
  validatePhone,
  isValidCUIT,
  validateCUIT,
  MAX_LENGTHS,
  createLengthValidator,
  validators,
  isValidUrl,
  isValidTileUrl,
} from '../../src/lib/validators';

describe('validators', () => {
  describe('email validation', () => {
    describe('isValidEmail', () => {
      it('should validate correct email addresses', () => {
        expect(isValidEmail('user@example.com')).toBe(true);
        expect(isValidEmail('john.doe@company.co.uk')).toBe(true);
        expect(isValidEmail('test+tag@domain.com')).toBe(true);
        expect(isValidEmail('user_name@example.org')).toBe(true);
      });

      it('should reject invalid email addresses', () => {
        expect(isValidEmail('notanemail')).toBe(false);
        expect(isValidEmail('user@')).toBe(false);
        expect(isValidEmail('@example.com')).toBe(false);
        expect(isValidEmail('user@.com')).toBe(false);
        expect(isValidEmail('user @example.com')).toBe(false);
      });

      it('should reject empty or falsy values', () => {
        expect(isValidEmail('')).toBe(false);
        expect(isValidEmail(null as any)).toBe(false);
        expect(isValidEmail(undefined as any)).toBe(false);
      });

      it('should reject emails exceeding max length', () => {
        const longEmail = `${'a'.repeat(250)}@example.com`;
        expect(isValidEmail(longEmail)).toBe(false);
      });

      it('should accept emails at max length boundary', () => {
        const maxEmail = `${'a'.repeat(240)}@example.com`;
        expect(isValidEmail(maxEmail)).toBe(true);
      });

      it('should reject non-string inputs', () => {
        expect(isValidEmail(123 as any)).toBe(false);
        expect(isValidEmail({} as any)).toBe(false);
      });
    });

    describe('validateEmail', () => {
      it('should return null for valid email', () => {
        expect(validateEmail('user@example.com')).toBeNull();
      });

      it('should return error for empty email', () => {
        expect(validateEmail('')).toBe('El email es requerido');
      });

      it('should return error for too long email', () => {
        const longEmail = `${'a'.repeat(250)}@example.com`;
        expect(validateEmail(longEmail)).toBe('Email demasiado largo');
      });

      it('should return error for invalid email format', () => {
        expect(validateEmail('notanemail')).toBe('Email invalido');
      });
    });
  });

  describe('phone validation', () => {
    describe('isValidPhone', () => {
      it('should validate Argentine phone numbers', () => {
        expect(isValidPhone('1123456789')).toBe(true);
        expect(isValidPhone('2214567890')).toBe(true);
        expect(isValidPhone('3412345678')).toBe(true);
      });

      it('should handle various formats', () => {
        expect(isValidPhone('+54 911 23456789')).toBe(true);
        expect(isValidPhone('+54-911-23456789')).toBe(true);
        expect(isValidPhone('(011) 2345-6789')).toBe(true);
        expect(isValidPhone('011 2345 6789')).toBe(true);
      });

      it('should handle 0 prefix for Argentina', () => {
        expect(isValidPhone('01123456789')).toBe(true);
        expect(isValidPhone('02214567890')).toBe(true);
      });

      it('should handle 54 country code', () => {
        expect(isValidPhone('541123456789')).toBe(true);
      });

      it('should reject invalid phone numbers', () => {
        expect(isValidPhone('123')).toBe(false);
        expect(isValidPhone('abc')).toBe(false);
        expect(isValidPhone('0')).toBe(false);
      });

      it('should reject empty or falsy values', () => {
        expect(isValidPhone('')).toBe(false);
        expect(isValidPhone(null as any)).toBe(false);
        expect(isValidPhone(undefined as any)).toBe(false);
      });

      it('should reject non-string inputs', () => {
        expect(isValidPhone(123 as any)).toBe(false);
      });
    });

    describe('validatePhone', () => {
      it('should return null for valid phone', () => {
        expect(validatePhone('1123456789')).toBeNull();
      });

      it('should return null for empty phone (optional field)', () => {
        expect(validatePhone('')).toBeNull();
      });

      it('should return error for invalid phone', () => {
        expect(validatePhone('abc')).toBe('Telefono invalido');
      });
    });
  });

  describe('CUIT validation', () => {
    describe('isValidCUIT', () => {
      it('should validate correct CUIT numbers', () => {
        // Valid CUIT examples (calculated with correct checksums)
        expect(isValidCUIT('20-12345678-6')).toBe(true);
        expect(isValidCUIT('20123456786')).toBe(true);
      });

      it('should handle CUIT with dashes', () => {
        expect(isValidCUIT('20-12345678-6')).toBe(true);
        expect(isValidCUIT('23-12345678-5')).toBe(true);
      });

      it('should reject CUIT without dashes', () => {
        expect(isValidCUIT('12345678')).toBe(false); // Too short
      });

      it('should reject invalid CUIT length', () => {
        expect(isValidCUIT('123')).toBe(false);
        expect(isValidCUIT('123456789012')).toBe(false);
      });

      it('should reject empty or falsy values', () => {
        expect(isValidCUIT('')).toBe(false);
        expect(isValidCUIT(null as any)).toBe(false);
        expect(isValidCUIT(undefined as any)).toBe(false);
      });

      it('should reject non-string inputs', () => {
        expect(isValidCUIT(123 as any)).toBe(false);
      });

      it('should validate check digit correctly', () => {
        // Verify checksum validation works
        expect(isValidCUIT('20123456786')).toBe(true);
        expect(isValidCUIT('20123456788')).toBe(false); // Wrong check digit
      });
    });

    describe('validateCUIT', () => {
      it('should return null for valid CUIT', () => {
        expect(validateCUIT('20-12345678-6')).toBeNull();
        expect(validateCUIT('23-12345678-5')).toBeNull();
      });

      it('should return error for empty CUIT', () => {
        expect(validateCUIT('')).toBe('El CUIT es requerido');
      });

      it('should return error for invalid CUIT', () => {
        expect(validateCUIT('123')).toBe('CUIT invalido');
      });
    });
  });

  describe('length validation', () => {
    describe('MAX_LENGTHS', () => {
      it('should have correct max length values', () => {
        expect(MAX_LENGTHS.TITULO).toBe(200);
        expect(MAX_LENGTHS.DESCRIPCION).toBe(5000);
        expect(MAX_LENGTHS.NOMBRE).toBe(100);
        expect(MAX_LENGTHS.TELEFONO).toBe(20);
        expect(MAX_LENGTHS.RESOLUCION).toBe(2000);
      });
    });

    describe('createLengthValidator', () => {
      const validator = createLengthValidator(5, 20, 'Test field');

      it('should accept strings within range', () => {
        expect(validator('hello')).toBeNull();
        expect(validator('test string')).toBeNull();
        expect(validator('a'.repeat(20))).toBeNull();
      });

      it('should reject strings too short', () => {
        expect(validator('abc')).toBe('Test field debe tener al menos 5 caracteres');
        expect(validator('')).toBe('Test field debe tener al menos 5 caracteres');
      });

      it('should reject strings too long', () => {
        expect(validator('a'.repeat(21))).toBe('Test field no puede exceder 20 caracteres');
      });

      it('should work with minimum length equals max length', () => {
        const validator2 = createLengthValidator(10, 10, 'Fixed field');
        expect(validator2('a'.repeat(10))).toBeNull();
        expect(validator2('a'.repeat(9))).not.toBeNull();
        expect(validator2('a'.repeat(11))).not.toBeNull();
      });
    });

    describe('validators object', () => {
      it('should validate titulo field', () => {
        expect(validators.titulo('ab')).not.toBeNull(); // Too short
        expect(validators.titulo('Valid Title')).toBeNull();
        expect(validators.titulo('a'.repeat(201))).not.toBeNull(); // Too long
      });

      it('should validate descripcion field', () => {
        expect(validators.descripcion('abc')).not.toBeNull(); // Too short
        expect(validators.descripcion('Valid Description')).toBeNull();
      });

      it('should validate nombre field', () => {
        expect(validators.nombre('a')).not.toBeNull(); // Too short
        expect(validators.nombre('John')).toBeNull();
        expect(validators.nombre('a'.repeat(101))).not.toBeNull(); // Too long
      });

      it('should validate resolucion field', () => {
        expect(validators.resolucion('abc')).not.toBeNull(); // Too short
        expect(validators.resolucion('Resolution 123')).toBeNull();
      });
    });
  });

  describe('URL validation', () => {
    describe('isValidUrl', () => {
      it('should validate HTTP URLs', () => {
        expect(isValidUrl('http://example.com')).toBe(true);
        expect(isValidUrl('http://example.com/path')).toBe(true);
      });

      it('should validate HTTPS URLs', () => {
        expect(isValidUrl('https://example.com')).toBe(true);
        expect(isValidUrl('https://sub.example.com/path?query=1')).toBe(true);
      });

      it('should reject non-HTTP protocols', () => {
        expect(isValidUrl('ftp://example.com')).toBe(false);
        expect(isValidUrl('file:///path/to/file')).toBe(false);
        expect(isValidUrl('javascript:alert("xss")')).toBe(false);
      });

      it('should reject invalid URLs', () => {
        expect(isValidUrl('not a url')).toBe(false);
        expect(isValidUrl('example.com')).toBe(false);
      });

      it('should reject empty or falsy values', () => {
        expect(isValidUrl('')).toBe(false);
        expect(isValidUrl(null as any)).toBe(false);
        expect(isValidUrl(undefined as any)).toBe(false);
      });

      it('should reject non-string inputs', () => {
        expect(isValidUrl(123 as any)).toBe(false);
      });
    });
  });

  describe('tile URL validation', () => {
    describe('isValidTileUrl', () => {
      it('should validate HTTPS tile URLs with placeholders', () => {
        expect(isValidTileUrl('https://tile.openstreetmap.org/{z}/{x}/{y}.png')).toBe(true);
        expect(
          isValidTileUrl('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}')
        ).toBe(true);
      });

      it('should require all three placeholders', () => {
        expect(isValidTileUrl('https://example.com/{z}/{x}')).toBe(false);
        expect(isValidTileUrl('https://example.com/{x}/{y}')).toBe(false);
        expect(isValidTileUrl('https://example.com/{z}/{y}')).toBe(false);
      });

      it('should require HTTPS protocol', () => {
        expect(isValidTileUrl('http://tile.openstreetmap.org/{z}/{x}/{y}.png')).toBe(false);
      });

      it('should reject invalid URLs', () => {
        expect(isValidTileUrl('not a url')).toBe(false);
      });

      it('should reject empty or falsy values', () => {
        expect(isValidTileUrl('')).toBe(false);
        expect(isValidTileUrl(null as any)).toBe(false);
        expect(isValidTileUrl(undefined as any)).toBe(false);
      });

      it('should reject non-string inputs', () => {
        expect(isValidTileUrl(123 as any)).toBe(false);
      });

      it('should handle URLs with query parameters', () => {
        expect(isValidTileUrl('https://example.com/tile/{z}/{x}/{y}.png?key=value')).toBe(true);
      });
    });
  });
});
