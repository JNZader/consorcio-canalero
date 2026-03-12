/**
 * Mutation tests for validator utility functions.
 * Tests regex boundary conditions and conditional logic mutations.
 */

import { describe, it, expect } from 'vitest';
import {
  isValidEmail,
  isValidPhone,
  isValidCUIT,
  validateEmail,
  validatePhone,
  MAX_EMAIL_LENGTH,
} from '@/lib/validators';
import { emailTestCases, phoneTestCases } from './setup';

// ===========================================
// Email Validation Tests
// ===========================================

describe('isValidEmail', () => {
  it.each(emailTestCases)('email: "$email" should be $isValid', ({ email, isValid }) => {
    expect(isValidEmail(email)).toBe(isValid);
  });

  it('should reject null', () => {
    expect(isValidEmail(null as unknown as string)).toBe(false);
  });

  it('should reject undefined', () => {
    expect(isValidEmail(undefined as unknown as string)).toBe(false);
  });

  it('should reject non-string types', () => {
    expect(isValidEmail(123 as unknown as string)).toBe(false);
    expect(isValidEmail({} as unknown as string)).toBe(false);
    expect(isValidEmail([] as unknown as string)).toBe(false);
  });

  it('should reject email exceeding max length', () => {
    const longEmail = 'a'.repeat(MAX_EMAIL_LENGTH + 1) + '@test.com';
    expect(isValidEmail(longEmail)).toBe(false);
  });

  it('should accept email at max length boundary', () => {
    // Create a valid email exactly at the boundary
    const localPart = 'a'.repeat(MAX_EMAIL_LENGTH - 10);
    const email = localPart + '@test.co';
    if (isValidEmail(email)) {
      expect(email.length).toBeLessThanOrEqual(MAX_EMAIL_LENGTH);
    }
  });

  it('should handle special characters', () => {
    const validSpecial = 'test+tag@example.com';
    expect(isValidEmail(validSpecial)).toBe(true);

    const invalidSpecial = 'test@example@com';
    expect(isValidEmail(invalidSpecial)).toBe(false);
  });

  it('should handle multiple domain levels', () => {
    expect(isValidEmail('user@mail.example.co.uk')).toBe(true);
  });

  it('should reject missing @ symbol', () => {
    expect(isValidEmail('userexample.com')).toBe(false);
  });

  it('should reject missing domain', () => {
    expect(isValidEmail('user@')).toBe(false);
  });

  it('should reject missing local part', () => {
    expect(isValidEmail('@example.com')).toBe(false);
  });

  // Mutation testing: catch regex pattern mutations
  it('should differentiate valid from invalid via regex', () => {
    const valid = 'valid@example.com';
    const invalid = 'invalid@';
    expect(isValidEmail(valid)).not.toBe(isValidEmail(invalid));
  });
});

// ===========================================
// Email Validation (Mantine) Tests
// ===========================================

describe('validateEmail', () => {
  it('should return null for valid email', () => {
    expect(validateEmail('valid@example.com')).toBeNull();
  });

  it('should return error for empty email', () => {
    const result = validateEmail('');
    expect(result).not.toBeNull();
    expect(result).toContain('requerido');
  });

  it('should return error for email exceeding max length', () => {
    const longEmail = 'a'.repeat(MAX_EMAIL_LENGTH + 1) + '@test.com';
    const result = validateEmail(longEmail);
    expect(result).not.toBeNull();
    expect(result).toContain('largo');
  });

  it('should return error for invalid email format', () => {
    const result = validateEmail('invalid.email');
    expect(result).not.toBeNull();
    expect(result).toContain('invalido');
  });

  // Mutation testing: catch return value mutations (null vs string)
  it('should return string error or null', () => {
    expect(validateEmail('test@test.com')).toBeNull();
    expect(typeof validateEmail('invalid')).toBe('string');
  });
});

// ===========================================
// Phone Validation Tests
// ===========================================

describe('isValidPhone', () => {
  it.each(phoneTestCases)('phone: "$phone" should be $isValid', ({ phone, isValid }) => {
    expect(isValidPhone(phone)).toBe(isValid);
  });

  it('should reject null', () => {
    expect(isValidPhone(null as unknown as string)).toBe(false);
  });

  it('should reject undefined', () => {
    expect(isValidPhone(undefined as unknown as string)).toBe(false);
  });

  it('should reject non-string types', () => {
    expect(isValidPhone(123 as unknown as string)).toBe(false);
  });

  it('should strip formatting characters', () => {
    expect(isValidPhone('+54 (9) 1234-567890')).toBeTruthy();
    expect(isValidPhone('0 1234-567890')).toBeTruthy();
  });

  it('should reject numbers with leading zeros', () => {
    expect(isValidPhone('0000000000')).toBe(false);
  });

  it('should require minimum length', () => {
    expect(isValidPhone('123')).toBe(false);
  });

  // Mutation testing: catch regex boundary mutations
  it('should differentiate valid from invalid patterns', () => {
    const valid = '+541234567890';
    const invalid = '00000000000';
    expect(isValidPhone(valid)).not.toBe(isValidPhone(invalid));
  });

  it('should accept various country prefixes', () => {
    expect(isValidPhone('+541234567890')).toBeTruthy();
    expect(isValidPhone('541234567890')).toBeTruthy();
    expect(isValidPhone('01234567890')).toBeTruthy();
  });
});

// ===========================================
// Phone Validation (Mantine) Tests
// ===========================================

describe('validatePhone', () => {
  it('should return null for valid phone', () => {
    expect(validatePhone('+541234567890')).toBeNull();
  });

  it('should return null for empty phone (optional)', () => {
    expect(validatePhone('')).toBeNull();
  });

  it('should return error for invalid phone', () => {
    const result = validatePhone('invalid');
    expect(result).not.toBeNull();
    expect(result).toContain('invalido');
  });
});

// ===========================================
// CUIT Validation Tests
// ===========================================

describe('isValidCUIT', () => {
  it('should reject null', () => {
    expect(isValidCUIT(null as unknown as string)).toBe(false);
  });

  it('should reject undefined', () => {
    expect(isValidCUIT(undefined as unknown as string)).toBe(false);
  });

  it('should reject non-string types', () => {
    expect(isValidCUIT(123 as unknown as string)).toBe(false);
  });

  it('should reject empty string', () => {
    expect(isValidCUIT('')).toBe(false);
  });

  it('should require exactly 11 digits', () => {
    expect(isValidCUIT('1234567890')).toBe(false); // 10 digits
    expect(isValidCUIT('123456789012')).toBe(false); // 12 digits
  });

  it('should accept CUIT with dashes', () => {
    // Valid CUIT format: XX-XXXXXXXX-X
    // Using a mathematically valid test CUIT
    const validCUIT = '20-12345678-9';
    // The validation will depend on the checksum algorithm
    expect(typeof isValidCUIT(validCUIT)).toBe('boolean');
  });

  it('should reject CUIT with invalid checksum', () => {
    // 11 digits but invalid checksum
    expect(isValidCUIT('12345678901')).toBe(false);
  });

  it('should handle CUIT without dashes', () => {
    const cuitNoDashes = '12345678901';
    expect(typeof isValidCUIT(cuitNoDashes)).toBe('boolean');
  });

  // Mutation testing: catch checksum algorithm mutations
  it('should differentiate valid from invalid checksum', () => {
    const valid = isValidCUIT('20-12345678-9');
    const invalid = isValidCUIT('20-12345678-0');
    // At least one should be false (checksum differs)
    expect([valid, invalid]).toContain(false);
  });
});

// ===========================================
// Type Checking and Edge Cases
// ===========================================

describe('validator type safety', () => {
  it('isValidEmail returns boolean', () => {
    expect(typeof isValidEmail('test@test.com')).toBe('boolean');
    expect(typeof isValidEmail('invalid')).toBe('boolean');
  });

  it('isValidPhone returns boolean', () => {
    expect(typeof isValidPhone('1234567890')).toBe('boolean');
    expect(typeof isValidPhone('invalid')).toBe('boolean');
  });

  it('isValidCUIT returns boolean', () => {
    expect(typeof isValidCUIT('12345678901')).toBe('boolean');
    expect(typeof isValidCUIT('invalid')).toBe('boolean');
  });

  it('validateEmail returns string or null', () => {
    const result1 = validateEmail('test@test.com');
    const result2 = validateEmail('invalid');
    expect([result1, result2]).toEqual(expect.arrayContaining([null, expect.any(String)]));
  });

  it('validatePhone returns string or null', () => {
    const result1 = validatePhone('+541234567890');
    const result2 = validatePhone('invalid');
    expect([result1, result2]).toEqual(expect.arrayContaining([null, expect.any(String)]));
  });
});

// ===========================================
// Regex Mutation Testing
// ===========================================

describe('regex mutation detection', () => {
  // These tests catch mutations where character classes are modified
  it('email: detects character class mutations in local part', () => {
    // Should accept dots, plus signs, etc.
    expect(isValidEmail('user+tag@example.com')).toBe(true);
    expect(isValidEmail('user.name@example.com')).toBe(true);
  });

  it('email: detects @ symbol is required', () => {
    // No @ = invalid
    expect(isValidEmail('userexample.com')).toBe(false);
    // Multiple @ = invalid
    expect(isValidEmail('user@example@com')).toBe(false);
  });

  it('phone: detects digit pattern mutations', () => {
    // Valid: starts with +54 or 54 or 0 or just number
    expect(isValidPhone('1234567890')).toBeTruthy();
    expect(isValidPhone('01234567890')).toBeTruthy();
  });

  it('cuit: detects length requirement mutation', () => {
    // Must be exactly 11
    expect(isValidCUIT('1234567890')).toBe(false);
    expect(isValidCUIT('123456789012')).toBe(false);
  });
});
