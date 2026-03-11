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
// @ts-nocheck
function stryNS_9fa48() {
  var g = typeof globalThis === 'object' && globalThis && globalThis.Math === Math && globalThis || new Function("return this")();
  var ns = g.__stryker__ || (g.__stryker__ = {});
  if (ns.activeMutant === undefined && g.process && g.process.env && g.process.env.__STRYKER_ACTIVE_MUTANT__) {
    ns.activeMutant = g.process.env.__STRYKER_ACTIVE_MUTANT__;
  }
  function retrieveNS() {
    return ns;
  }
  stryNS_9fa48 = retrieveNS;
  return retrieveNS();
}
stryNS_9fa48();
function stryCov_9fa48() {
  var ns = stryNS_9fa48();
  var cov = ns.mutantCoverage || (ns.mutantCoverage = {
    static: {},
    perTest: {}
  });
  function cover() {
    var c = cov.static;
    if (ns.currentTestId) {
      c = cov.perTest[ns.currentTestId] = cov.perTest[ns.currentTestId] || {};
    }
    var a = arguments;
    for (var i = 0; i < a.length; i++) {
      c[a[i]] = (c[a[i]] || 0) + 1;
    }
  }
  stryCov_9fa48 = cover;
  cover.apply(null, arguments);
}
function stryMutAct_9fa48(id) {
  var ns = stryNS_9fa48();
  function isActive(id) {
    if (ns.activeMutant === id) {
      if (ns.hitCount !== void 0 && ++ns.hitCount > ns.hitLimit) {
        throw new Error('Stryker: Hit count limit reached (' + ns.hitCount + ')');
      }
      return true;
    }
    return false;
  }
  stryMutAct_9fa48 = isActive;
  return isActive(id);
}
import type { Session, User } from '@supabase/supabase-js';
import { useCallback, useEffect, useMemo } from 'react';
import { useShallow } from 'zustand/shallow';
import { signInWithEmail, signInWithGoogle, signOut, signUpWithEmail, type AuthResult } from '../lib/auth';
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
  if (stryMutAct_9fa48("0")) {
    {}
  } else {
    stryCov_9fa48("0");
    const {
      autoInitialize = stryMutAct_9fa48("1") ? false : (stryCov_9fa48("1"), true)
    } = options;

    // Get state from Zustand store using a single shallow selector
    const {
      user,
      session,
      profile,
      loading,
      initialized,
      error,
      initialize: storeInitialize,
      reset: storeReset
    } = useAuthStore(useShallow(stryMutAct_9fa48("2") ? () => undefined : (stryCov_9fa48("2"), state => stryMutAct_9fa48("3") ? {} : (stryCov_9fa48("3"), {
      user: state.user,
      session: state.session,
      profile: state.profile,
      loading: state.loading,
      initialized: state.initialized,
      error: state.error,
      initialize: state.initialize,
      reset: state.reset
    }))));

    // Auto-initialize on mount
    useEffect(() => {
      if (stryMutAct_9fa48("4")) {
        {}
      } else {
        stryCov_9fa48("4");
        if (stryMutAct_9fa48("7") ? autoInitialize || !initialized : stryMutAct_9fa48("6") ? false : stryMutAct_9fa48("5") ? true : (stryCov_9fa48("5", "6", "7"), autoInitialize && (stryMutAct_9fa48("8") ? initialized : (stryCov_9fa48("8"), !initialized)))) {
          if (stryMutAct_9fa48("9")) {
            {}
          } else {
            stryCov_9fa48("9");
            storeInitialize();
          }
        }
      }
    }, stryMutAct_9fa48("10") ? [] : (stryCov_9fa48("10"), [autoInitialize, initialized, storeInitialize]));

    // Derived state
    const isLoading = stryMutAct_9fa48("13") ? loading && !initialized : stryMutAct_9fa48("12") ? false : stryMutAct_9fa48("11") ? true : (stryCov_9fa48("11", "12", "13"), loading || (stryMutAct_9fa48("14") ? initialized : (stryCov_9fa48("14"), !initialized)));
    const isAuthenticated = stryMutAct_9fa48("17") ? !!user && !loading || initialized : stryMutAct_9fa48("16") ? false : stryMutAct_9fa48("15") ? true : (stryCov_9fa48("15", "16", "17"), (stryMutAct_9fa48("19") ? !!user || !loading : stryMutAct_9fa48("18") ? true : (stryCov_9fa48("18", "19"), (stryMutAct_9fa48("20") ? !user : (stryCov_9fa48("20"), !(stryMutAct_9fa48("21") ? user : (stryCov_9fa48("21"), !user)))) && (stryMutAct_9fa48("22") ? loading : (stryCov_9fa48("22"), !loading)))) && initialized);
    const role: UserRole | null = stryMutAct_9fa48("25") ? profile?.rol as UserRole && null : stryMutAct_9fa48("24") ? false : stryMutAct_9fa48("23") ? true : (stryCov_9fa48("23", "24", "25"), profile?.rol as UserRole || null);

    // Role checking utilities - memoized to prevent unnecessary re-renders
    const hasRole = useCallback((roles: UserRole | UserRole[]): boolean => {
      if (stryMutAct_9fa48("26")) {
        {}
      } else {
        stryCov_9fa48("26");
        if (stryMutAct_9fa48("29") ? !isAuthenticated && !role : stryMutAct_9fa48("28") ? false : stryMutAct_9fa48("27") ? true : (stryCov_9fa48("27", "28", "29"), (stryMutAct_9fa48("30") ? isAuthenticated : (stryCov_9fa48("30"), !isAuthenticated)) || (stryMutAct_9fa48("31") ? role : (stryCov_9fa48("31"), !role)))) return stryMutAct_9fa48("32") ? true : (stryCov_9fa48("32"), false);
        const rolesArray = Array.isArray(roles) ? roles : stryMutAct_9fa48("33") ? [] : (stryCov_9fa48("33"), [roles]);
        return rolesArray.includes(role);
      }
    }, stryMutAct_9fa48("34") ? [] : (stryCov_9fa48("34"), [isAuthenticated, role]));
    const isAdmin = useMemo(stryMutAct_9fa48("35") ? () => undefined : (stryCov_9fa48("35"), () => hasRole(stryMutAct_9fa48("36") ? "" : (stryCov_9fa48("36"), 'admin'))), stryMutAct_9fa48("37") ? [] : (stryCov_9fa48("37"), [hasRole]));
    const isOperador = useMemo(stryMutAct_9fa48("38") ? () => undefined : (stryCov_9fa48("38"), () => hasRole(stryMutAct_9fa48("39") ? "" : (stryCov_9fa48("39"), 'operador'))), stryMutAct_9fa48("40") ? [] : (stryCov_9fa48("40"), [hasRole]));
    const isStaff = useMemo(stryMutAct_9fa48("41") ? () => undefined : (stryCov_9fa48("41"), () => hasRole(stryMutAct_9fa48("42") ? [] : (stryCov_9fa48("42"), [stryMutAct_9fa48("43") ? "" : (stryCov_9fa48("43"), 'admin'), stryMutAct_9fa48("44") ? "" : (stryCov_9fa48("44"), 'operador')]))), stryMutAct_9fa48("45") ? [] : (stryCov_9fa48("45"), [hasRole]));
    const isCiudadano = useMemo(stryMutAct_9fa48("46") ? () => undefined : (stryCov_9fa48("46"), () => hasRole(stryMutAct_9fa48("47") ? "" : (stryCov_9fa48("47"), 'ciudadano'))), stryMutAct_9fa48("48") ? [] : (stryCov_9fa48("48"), [hasRole]));
    const canAccess = useCallback((allowedRoles: UserRole[]): boolean => {
      if (stryMutAct_9fa48("49")) {
        {}
      } else {
        stryCov_9fa48("49");
        if (stryMutAct_9fa48("52") ? false : stryMutAct_9fa48("51") ? true : stryMutAct_9fa48("50") ? isAuthenticated : (stryCov_9fa48("50", "51", "52"), !isAuthenticated)) return stryMutAct_9fa48("53") ? true : (stryCov_9fa48("53"), false);
        if (stryMutAct_9fa48("56") ? allowedRoles.length !== 0 : stryMutAct_9fa48("55") ? false : stryMutAct_9fa48("54") ? true : (stryCov_9fa48("54", "55", "56"), allowedRoles.length === 0)) return stryMutAct_9fa48("57") ? false : (stryCov_9fa48("57"), true); // No role restriction
        return hasRole(allowedRoles);
      }
    }, stryMutAct_9fa48("58") ? [] : (stryCov_9fa48("58"), [isAuthenticated, hasRole]));

    // Actions - stable references using useCallback
    const login = useCallback(async (email: string, password: string): Promise<AuthResult> => {
      if (stryMutAct_9fa48("59")) {
        {}
      } else {
        stryCov_9fa48("59");
        return signInWithEmail(email, password);
      }
    }, stryMutAct_9fa48("60") ? ["Stryker was here"] : (stryCov_9fa48("60"), []));
    const loginWithGoogle = useCallback(async (): Promise<AuthResult> => {
      if (stryMutAct_9fa48("61")) {
        {}
      } else {
        stryCov_9fa48("61");
        return signInWithGoogle();
      }
    }, stryMutAct_9fa48("62") ? ["Stryker was here"] : (stryCov_9fa48("62"), []));
    const register = useCallback(async (email: string, password: string, nombre?: string): Promise<AuthResult> => {
      if (stryMutAct_9fa48("63")) {
        {}
      } else {
        stryCov_9fa48("63");
        return signUpWithEmail(email, password, nombre);
      }
    }, stryMutAct_9fa48("64") ? ["Stryker was here"] : (stryCov_9fa48("64"), []));
    const logout = useCallback(async (): Promise<AuthResult> => {
      if (stryMutAct_9fa48("65")) {
        {}
      } else {
        stryCov_9fa48("65");
        return signOut();
      }
    }, stryMutAct_9fa48("66") ? ["Stryker was here"] : (stryCov_9fa48("66"), []));
    const initialize = useCallback(async (): Promise<void> => {
      if (stryMutAct_9fa48("67")) {
        {}
      } else {
        stryCov_9fa48("67");
        return storeInitialize();
      }
    }, stryMutAct_9fa48("68") ? [] : (stryCov_9fa48("68"), [storeInitialize]));
    const reset = useCallback((): void => {
      if (stryMutAct_9fa48("69")) {
        {}
      } else {
        stryCov_9fa48("69");
        storeReset();
      }
    }, stryMutAct_9fa48("70") ? [] : (stryCov_9fa48("70"), [storeReset]));
    return stryMutAct_9fa48("71") ? {} : (stryCov_9fa48("71"), {
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
      canAccess
    });
  }
}

// Re-export UserRole type for convenience
export type { UserRole } from '../stores/authStore';

// Default export for convenience
export default useAuth;