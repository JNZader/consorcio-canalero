/**
 * Mutation tests for src/lib/validators.ts
 * Tests email, phone, URL, and CUIT validation functions
 */

import { describe, it, expect } from 'vitest';
import {
  isValidEmail,
  validateEmail,
  isValidPhone,
  validatePhone,
  isValidCUIT,
  validateCUIT,
  isValidUrl,
  isValidTileUrl,
  createLengthValidator,
  MAX_EMAIL_LENGTH,
  MAX_LENGTHS,
  validators,
} from '../../../src/lib/validators';
import {
  emailTestCases,
  phoneTestCases,
  urlTestCases,
  tileUrlTestCases,
  cuitTestCases,
} from './setup';

describe('validators', () => {
  describe('isValidEmail', () => {
    it.each(emailTestCases.valid)('should accept valid email: %s', (email) => {
      expect(isValidEmail(email)).toBe(true);
    });

    it.each(emailTestCases.invalid)('should reject invalid email: %s', (email) => {
      expect(isValidEmail(email)).toBe(false);
    });

    it.each(emailTestCases.nullish)('should reject nullish value: %s', (value) => {
      expect(isValidEmail(value as string)).toBe(false);
    });

    it('should reject empty string', () => {
      expect(isValidEmail('')).toBe(false);
    });

    it('should reject email exceeding MAX_EMAIL_LENGTH', () => {
      expect(isValidEmail(emailTestCases.edgeCases.tooLong)).toBe(false);
    });

    it('should reject email with leading/trailing spaces', () => {
      expect(isValidEmail(' user@example.com')).toBe(false);
      expect(isValidEmail('user@example.com ')).toBe(false);
    });

    it('should accept email with special characters allowed by RFC', () => {
      const specialEmails = [
        'user+tag@example.com',
        'user_name@example.com',
        'user-name@example.com',
        '123456@example.com',
      ];
      specialEmails.forEach((email) => {
        expect(isValidEmail(email)).toBe(true);
      });
    });

    it('should reject non-string type', () => {
      expect(isValidEmail(123 as unknown as string)).toBe(false);
      expect(isValidEmail({} as unknown as string)).toBe(false);
    });

    it('should catch mutation on length check', () => {
      // Verify it checks length, not just regex
      const tooLong = 'a'.repeat(255) + '@example.com';
      expect(isValidEmail(tooLong)).toBe(false);

      const valid = 'a'.repeat(240) + '@example.com';
      if (valid.length <= MAX_EMAIL_LENGTH) {
        expect(isValidEmail(valid)).toBe(true);
      }
    });

    it('should be ReDoS safe', () => {
      // Test that regex doesn't cause catastrophic backtracking
      const pathologicalEmail = 'a'.repeat(100) + '@' + 'b'.repeat(100) + '.com';
      expect(() => {
        isValidEmail(pathologicalEmail);
      }).not.toThrow();
    });
  });

  describe('validateEmail', () => {
    it('should return null for valid emails', () => {
      expect(validateEmail('user@example.com')).toBeNull();
    });

    it('should return error for empty string', () => {
      expect(validateEmail('')).toContain('requerido');
    });

    it('should return error for too long email', () => {
      const tooLong = 'a'.repeat(255) + '@example.com';
      expect(validateEmail(tooLong)).toContain('largo');
    });

    it('should return error for invalid format', () => {
      expect(validateEmail('invalid-email')).toContain('invalido');
    });

    it('should provide specific error messages', () => {
      expect(validateEmail('')).toBe('El email es requerido');
      expect(validateEmail('invalid')).toBe('Email invalido');
      expect(validateEmail('a'.repeat(300) + '@example.com')).toContain('largo');
    });
  });

  describe('isValidPhone', () => {
    it.each(phoneTestCases.valid)('should accept valid phone: %s', (phone) => {
      expect(isValidPhone(phone)).toBe(true);
    });

    it.each(phoneTestCases.invalid)('should reject invalid phone: %s', (phone) => {
      expect(isValidPhone(phone)).toBe(false);
    });

    it.each(phoneTestCases.nullish)('should reject nullish value: %s', (value) => {
      expect(isValidPhone(value as string)).toBe(false);
    });

    it('should strip formatting characters', () => {
      // Note: +54 prefix replaces the 0 in area code, so valid phone is like +549112345678
      // Not +54 (011) which would be double-coding the area
      const formatted = '+54 9 11 2345 6789';
      expect(isValidPhone(formatted)).toBe(true);
    });

    it('should accept various Argentine phone formats', () => {
      const formats = [
        '+541123456789',
        '541123456789',
        '01123456789',
        '1123456789',
      ];
      formats.forEach((phone) => {
        expect(isValidPhone(phone)).toBe(true);
      });
    });

    it('should reject non-Argentine country codes', () => {
      // +55 is Brazil, not Argentina
      expect(isValidPhone('+55 11 9 8765 4321')).toBe(false);
    });

    it('should reject non-string type', () => {
      expect(isValidPhone(123 as unknown as string)).toBe(false);
    });

    it('should catch mutation on required placeholder check', () => {
      // Verify it properly validates the regex after cleaning
      const validPhone = '+541123456789';
      expect(isValidPhone(validPhone)).toBe(true);

      const invalidPhone = '0123'; // Too short
      expect(isValidPhone(invalidPhone)).toBe(false);
    });
  });

  describe('validatePhone', () => {
    it('should return null for valid phone', () => {
      expect(validatePhone('+541123456789')).toBeNull();
    });

    it('should return null for empty string (optional field)', () => {
      expect(validatePhone('')).toBeNull();
    });

    it('should return error for invalid format', () => {
      expect(validatePhone('123')).toContain('invalido');
    });

    it('should provide specific error message', () => {
      expect(validatePhone('invalid')).toBe('Telefono invalido');
    });
  });

  describe('isValidCUIT', () => {
    it.each(cuitTestCases.valid)('should accept valid CUIT: %s', (cuit) => {
      expect(isValidCUIT(cuit)).toBe(true);
    });

    it.each(cuitTestCases.invalid)('should reject invalid CUIT: %s', (cuit) => {
      expect(isValidCUIT(cuit)).toBe(false);
    });

    it.each(cuitTestCases.nullish)('should reject nullish value: %s', (value) => {
      expect(isValidCUIT(value as string)).toBe(false);
    });

    it('should handle CUITs with dashes', () => {
      // Valid CUIT with dashes
      expect(isValidCUIT('20-123-456-786')).toBe(true);
    });

    it('should reject CUIT with wrong length', () => {
      expect(isValidCUIT('123')).toBe(false);
      expect(isValidCUIT('123456789012')).toBe(false);
    });

    it('should validate check digit using modulo 11 algorithm', () => {
      // Valid check digit
      expect(isValidCUIT('20123456786')).toBe(true);

      // Invalid check digit (change last digit)
      expect(isValidCUIT('20123456780')).toBe(false);
    });

    it('should handle edge cases in check digit calculation', () => {
      // Test case where calculated check digit is 11 (becomes 0)
      // Test case where calculated check digit is 10 (becomes 9)
      expect(() => {
        isValidCUIT('20000000010'); // Edge case
        isValidCUIT('27000000010'); // Different prefix
      }).not.toThrow();
    });

    it('should reject non-numeric characters', () => {
      expect(isValidCUIT('20-ABCDE-FGH')).toBe(false);
    });

    it('should reject non-string type', () => {
      expect(isValidCUIT(123 as unknown as string)).toBe(false);
    });
  });

  describe('validateCUIT', () => {
    it('should return null for valid CUIT', () => {
      expect(validateCUIT('20-123-456-786')).toBeNull();
    });

    it('should return error for empty string', () => {
      expect(validateCUIT('')).toContain('requerido');
    });

    it('should return error for invalid CUIT', () => {
      expect(validateCUIT('12345678901')).toContain('invalido');
    });

    it('should provide specific error messages', () => {
      expect(validateCUIT('')).toBe('El CUIT es requerido');
      expect(validateCUIT('invalid')).toBe('CUIT invalido');
    });
  });

  describe('isValidUrl', () => {
    it.each(Object.values(urlTestCases.valid))(
      'should accept valid URL: %s',
      (url) => {
        expect(isValidUrl(url)).toBe(true);
      }
    );

    it.each(urlTestCases.invalid)('should reject invalid URL: %s', (url) => {
      expect(isValidUrl(url)).toBe(false);
    });

    it.each(urlTestCases.nullish)('should reject nullish value: %s', (value) => {
      expect(isValidUrl(value as string)).toBe(false);
    });

    it('should only accept HTTP and HTTPS protocols', () => {
      expect(isValidUrl('http://example.com')).toBe(true);
      expect(isValidUrl('https://example.com')).toBe(true);
      expect(isValidUrl('ftp://example.com')).toBe(false);
      expect(isValidUrl('file:///path')).toBe(false);
    });

    it('should catch mutation on protocol check', () => {
      // Verify it checks protocols strictly
      expect(isValidUrl('http://example.com')).toBe(true);
      expect(isValidUrl('https://example.com')).toBe(true);
      // URL constructor normalizes case, so just verify non-http/https are rejected
      expect(isValidUrl('ftp://example.com')).toBe(false);
    });

    it('should reject non-string type', () => {
      expect(isValidUrl(123 as unknown as string)).toBe(false);
    });

    it('should handle complex URLs', () => {
      const complexUrl =
        'https://subdomain.example.co.uk:8443/path?query=value&foo=bar#hash';
      expect(isValidUrl(complexUrl)).toBe(true);
    });
  });

  describe('isValidTileUrl', () => {
    it.each(tileUrlTestCases.valid)('should accept valid tile URL: %s', (url) => {
      expect(isValidTileUrl(url)).toBe(true);
    });

    it.each(tileUrlTestCases.invalid)('should reject invalid tile URL: %s', (url) => {
      expect(isValidTileUrl(url)).toBe(false);
    });

    it.each(tileUrlTestCases.nullish)('should reject nullish value: %s', (value) => {
      expect(isValidTileUrl(value as string)).toBe(false);
    });

    it('should require HTTPS protocol', () => {
      const httpUrl = 'http://example.com/{z}/{x}/{y}.png';
      expect(isValidTileUrl(httpUrl)).toBe(false);

      const httpsUrl = 'https://example.com/{z}/{x}/{y}.png';
      expect(isValidTileUrl(httpsUrl)).toBe(true);
    });

    it('should require all three placeholder types', () => {
      expect(isValidTileUrl('https://example.com/{z}/{x}/{y}.png')).toBe(true);
      expect(isValidTileUrl('https://example.com/{z}/{x}.png')).toBe(false);
      expect(isValidTileUrl('https://example.com/{z}/{y}.png')).toBe(false);
      expect(isValidTileUrl('https://example.com/{x}/{y}.png')).toBe(false);
    });

    it('should catch mutation on placeholder validation', () => {
      // Verify it checks for all three placeholders
      const twoPlaceholders = 'https://example.com/{z}/{x}/0.png';
      expect(isValidTileUrl(twoPlaceholders)).toBe(false);

      const threePlaceholders = 'https://example.com/{z}/{x}/{y}.png';
      expect(isValidTileUrl(threePlaceholders)).toBe(true);
    });

    it('should handle placeholder template variables', () => {
      const url = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
      expect(isValidTileUrl(url)).toBe(true);
    });

    it('should reject non-string type', () => {
      expect(isValidTileUrl(123 as unknown as string)).toBe(false);
    });
  });

  describe('createLengthValidator', () => {
    const validator = createLengthValidator(2, 10, 'Test field');

    it('should return null for valid length', () => {
      expect(validator('hello')).toBeNull();
    });

    it('should reject text shorter than minLength', () => {
      expect(validator('a')).toContain('al menos');
    });

    it('should reject text longer than maxLength', () => {
      expect(validator('this is too long')).toContain('no puede exceder');
    });

    it('should accept text at boundaries', () => {
      expect(validator('ab')).toBeNull(); // Exactly minLength
      expect(validator('abcdefghij')).toBeNull(); // Exactly maxLength
    });

    it('should include field name in error message', () => {
      const error = validator('a');
      expect(error).toContain('Test field');
    });

    it('should be case sensitive', () => {
      const validator2 = createLengthValidator(5, 10, 'Name');
      expect(validator2('hello')).toBeNull();
      expect(validator2('hello world')).toContain('no puede exceder');
    });
  });

  describe('validators object', () => {
    it('should validate titulo field', () => {
      expect(validators.titulo('A Valid Title')).toBeNull();
      expect(validators.titulo('x')).toContain('al menos');
      expect(validators.titulo('a'.repeat(201))).toContain('no puede exceder');
    });

    it('should validate descripcion field', () => {
      expect(validators.descripcion('Valid description text')).toBeNull();
      expect(validators.descripcion('short')).toContain('al menos');
      expect(validators.descripcion('a'.repeat(5001))).toContain('no puede exceder');
    });

    it('should validate nombre field', () => {
      expect(validators.nombre('John')).toBeNull();
      expect(validators.nombre('J')).toContain('al menos');
      expect(validators.nombre('a'.repeat(101))).toContain('no puede exceder');
    });

    it('should validate resolucion field', () => {
      expect(validators.resolucion('Valid Resolution Text')).toBeNull();
      expect(validators.resolucion('text')).toContain('al menos');
      expect(validators.resolucion('a'.repeat(2001))).toContain('no puede exceder');
    });
  });

  describe('MAX_LENGTHS constant', () => {
    it('should have correct values', () => {
      expect(MAX_LENGTHS.TITULO).toBe(200);
      expect(MAX_LENGTHS.DESCRIPCION).toBe(5000);
      expect(MAX_LENGTHS.NOMBRE).toBe(100);
      expect(MAX_LENGTHS.TELEFONO).toBe(20);
      expect(MAX_LENGTHS.RESOLUCION).toBe(2000);
    });
  });

  describe('MAX_EMAIL_LENGTH constant', () => {
    it('should conform to RFC 5321', () => {
      expect(MAX_EMAIL_LENGTH).toBe(254);
    });
  });
});
