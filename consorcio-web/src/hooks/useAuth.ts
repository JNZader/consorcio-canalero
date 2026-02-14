/**
 * Unified authentication hook for React components.
 *
 * This hook provides a clean React interface for authentication,
 * wrapping the Zustand authStore with convenient utilities for:
 * - Auth state access (user, session, profile, loading states)
 * - Login/logout operations
 * - Role checking utilities
 * - Auto-initialization of auth state
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { user, isAuthenticated, isLoading, login, logout, isAdmin } = useAuth();
 *
 *   if (isLoading) return <Spinner />;
 *   if (!isAuthenticated) return <LoginPrompt />;
 *
 *   return (
 *     <div>
 *       <p>Welcome, {user?.email}</p>
 *       {isAdmin && <AdminPanel />}
 *       <button onClick={logout}>Logout</button>
 *     </div>
 *   );
 * }
 * ```
 */

import type { Session, User } from '@supabase/supabase-js';
import { useCallback, useEffect, useMemo } from 'react';
import { useShallow } from 'zustand/shallow';
import {
  signInWithEmail,
  signInWithGoogle,
  signOut,
  signUpWithEmail,
  type AuthResult,
} from '../lib/auth';
import type { Usuario } from '../lib/supabase';
import { useAuthStore, type UserRole } from '../stores/authStore';

/**
 * Auth state returned by useAuth hook
 */
export interface UseAuthState {
  /** Supabase user object */
  user: User | null;
  /** Supabase session object */
  session: Session | null;
  /** User profile from database */
  profile: Usuario | null;
  /** Whether auth is currently loading */
  isLoading: boolean;
  /** Whether the store has been initialized */
  isInitialized: boolean;
  /** Whether user is authenticated (has user, not loading, initialized) */
  isAuthenticated: boolean;
  /** Current user role */
  role: UserRole | null;
  /** Any auth error message */
  error: string | null;
}

/**
 * Auth actions returned by useAuth hook
 */
export interface UseAuthActions {
  /** Sign in with email and password */
  login: (email: string, password: string) => Promise<AuthResult>;
  /** Sign in with Google OAuth */
  loginWithGoogle: () => Promise<AuthResult>;
  /** Register a new user */
  register: (email: string, password: string, nombre?: string) => Promise<AuthResult>;
  /** Sign out the current user */
  logout: () => Promise<AuthResult>;
  /** Manually initialize auth (usually automatic) */
  initialize: () => Promise<void>;
  /** Reset auth state */
  reset: () => void;
}

/**
 * Role checking utilities returned by useAuth hook
 */
export interface UseAuthRoleUtils {
  /** Check if user has any of the specified roles */
  hasRole: (roles: UserRole | UserRole[]) => boolean;
  /** Check if user is an admin */
  isAdmin: boolean;
  /** Check if user is an operator */
  isOperador: boolean;
  /** Check if user is an admin or operator */
  isStaff: boolean;
  /** Check if user is a citizen (ciudadano) */
  isCiudadano: boolean;
  /** Check if user can access based on allowed roles */
  canAccess: (allowedRoles: UserRole[]) => boolean;
}

/**
 * Complete return type of useAuth hook
 */
export type UseAuthReturn = UseAuthState & UseAuthActions & UseAuthRoleUtils;

/**
 * Options for useAuth hook
 */
export interface UseAuthOptions {
  /**
   * Whether to automatically initialize auth on mount.
   * @default true
   */
  autoInitialize?: boolean;
}

/**
 * Unified authentication hook.
 *
 * Provides access to auth state, login/logout functions, and role checking utilities.
 * Automatically initializes auth state on mount (can be disabled).
 *
 * @param options - Hook configuration options
 * @returns Auth state, actions, and role utilities
 */
export function useAuth(options: UseAuthOptions = {}): UseAuthReturn {
  const { autoInitialize = true } = options;

  // Get state from Zustand store using a single shallow selector
  const {
    user, session, profile, loading, initialized, error,
    initialize: storeInitialize, reset: storeReset
  } = useAuthStore(
    useShallow((state) => ({
      user: state.user,
      session: state.session,
      profile: state.profile,
      loading: state.loading,
      initialized: state.initialized,
      error: state.error,
      initialize: state.initialize,
      reset: state.reset,
    }))
  );

  // Auto-initialize on mount
  useEffect(() => {
    if (autoInitialize && !initialized) {
      storeInitialize();
    }
  }, [autoInitialize, initialized, storeInitialize]);

  // Derived state
  const isLoading = loading || !initialized;
  const isAuthenticated = !!user && !loading && initialized;
  const role: UserRole | null = (profile?.rol as UserRole) || null;

  // Role checking utilities - memoized to prevent unnecessary re-renders
  const hasRole = useCallback(
    (roles: UserRole | UserRole[]): boolean => {
      if (!isAuthenticated || !role) return false;
      const rolesArray = Array.isArray(roles) ? roles : [roles];
      return rolesArray.includes(role);
    },
    [isAuthenticated, role]
  );

  const isAdmin = useMemo(() => hasRole('admin'), [hasRole]);
  const isOperador = useMemo(() => hasRole('operador'), [hasRole]);
  const isStaff = useMemo(() => hasRole(['admin', 'operador']), [hasRole]);
  const isCiudadano = useMemo(() => hasRole('ciudadano'), [hasRole]);

  const canAccess = useCallback(
    (allowedRoles: UserRole[]): boolean => {
      if (!isAuthenticated) return false;
      if (allowedRoles.length === 0) return true; // No role restriction
      return hasRole(allowedRoles);
    },
    [isAuthenticated, hasRole]
  );

  // Actions - stable references using useCallback
  const login = useCallback(async (email: string, password: string): Promise<AuthResult> => {
    return signInWithEmail(email, password);
  }, []);

  const loginWithGoogle = useCallback(async (): Promise<AuthResult> => {
    return signInWithGoogle();
  }, []);

  const register = useCallback(
    async (email: string, password: string, nombre?: string): Promise<AuthResult> => {
      return signUpWithEmail(email, password, nombre);
    },
    []
  );

  const logout = useCallback(async (): Promise<AuthResult> => {
    return signOut();
  }, []);

  const initialize = useCallback(async (): Promise<void> => {
    return storeInitialize();
  }, [storeInitialize]);

  const reset = useCallback((): void => {
    storeReset();
  }, [storeReset]);

  return {
    // State
    user,
    session,
    profile,
    isLoading,
    isInitialized: initialized,
    isAuthenticated,
    role,
    error,

    // Actions
    login,
    loginWithGoogle,
    register,
    logout,
    initialize,
    reset,

    // Role utilities
    hasRole,
    isAdmin,
    isOperador,
    isStaff,
    isCiudadano,
    canAccess,
  };
}

// Re-export UserRole type for convenience
export type { UserRole } from '../stores/authStore';

// Default export for convenience
export default useAuth;
