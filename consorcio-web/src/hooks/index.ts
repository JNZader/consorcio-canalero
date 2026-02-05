/**
 * Hooks barrel file for centralized exports.
 */

export {
  useAuth,
  type UseAuthState,
  type UseAuthActions,
  type UseAuthRoleUtils,
  type UseAuthReturn,
  type UseAuthOptions,
  type UserRole,
} from './useAuth';

export {
  useContactVerification,
  type VerificationMethod,
  type UseContactVerificationOptions,
  type ContactVerificationState,
  type ContactVerificationActions,
  type UseContactVerificationReturn,
} from './useContactVerification';
