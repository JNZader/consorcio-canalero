/**
 * verification-types.test.ts
 * Unit tests for verification component types and guards
 */
// @ts-nocheck


import { describe, it, expect } from 'vitest';
import { isVerificationMethod } from '../../src/components/verification/types';

describe('verification/types', () => {
  describe('isVerificationMethod', () => {
    it('should return true for valid method "google"', () => {
      expect(isVerificationMethod('google')).toBe(true);
    });

    it('should return true for valid method "email"', () => {
      expect(isVerificationMethod('email')).toBe(true);
    });

    it('should return false for invalid method "sms"', () => {
      expect(isVerificationMethod('sms')).toBe(false);
    });

    it('should return false for empty string', () => {
      expect(isVerificationMethod('')).toBe(false);
    });

    it('should return false for null', () => {
      expect(isVerificationMethod(null as any)).toBe(false);
    });

    it('should return false for undefined', () => {
      expect(isVerificationMethod(undefined as any)).toBe(false);
    });

    it('should return false for uppercase variants', () => {
      expect(isVerificationMethod('GOOGLE')).toBe(false);
      expect(isVerificationMethod('EMAIL')).toBe(false);
    });

    it('should return false for partial matches', () => {
      expect(isVerificationMethod('goog')).toBe(false);
      expect(isVerificationMethod('mail')).toBe(false);
    });

    it('should return false for mixed case', () => {
      expect(isVerificationMethod('Google')).toBe(false);
      expect(isVerificationMethod('Email')).toBe(false);
    });

    it('should return false for numbers', () => {
      expect(isVerificationMethod('123')).toBe(false);
    });
  });
});
