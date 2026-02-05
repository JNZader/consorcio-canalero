/**
 * Shared verification components.
 * Used for contact verification in public forms (denuncias, sugerencias).
 *
 * Supports:
 * - Google OAuth (1-click for Gmail users)
 * - Magic Link (any email address)
 */

export { ContactVerificationSection } from './ContactVerificationSection';
export type { ContactVerificationSectionProps } from './ContactVerificationSection';
export { isVerificationMethod } from './types';
export type { VerificationFormErrors, VerificationMethod } from './types';
