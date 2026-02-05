/**
 * Shared types for verification components.
 * Used by Google OAuth and Magic Link verification flows.
 */

export type VerificationMethod = 'google' | 'email';

export interface VerificationFormErrors {
  contacto_email?: string;
}

/**
 * Type guard to check if a value is a valid verification method.
 */
export function isVerificationMethod(value: string): value is VerificationMethod {
  return value === 'google' || value === 'email';
}
