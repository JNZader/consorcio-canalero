/**
 * Auth module — singleton auth adapter instance.
 *
 * Import { authAdapter } from this module to get the current auth provider.
 * Currently uses JWTAuthAdapter for FastAPI backend.
 */

export { JWTAuthAdapter } from './jwt-adapter';
export type {
  AuthAdapter,
  AuthSession,
  AuthStateChangeCallback,
  AuthUser,
  LoginCredentials,
  RegisterCredentials,
} from './types';

import { JWTAuthAdapter } from './jwt-adapter';
import type { AuthAdapter } from './types';

/** Singleton auth adapter instance */
export const authAdapter: AuthAdapter = new JWTAuthAdapter();
