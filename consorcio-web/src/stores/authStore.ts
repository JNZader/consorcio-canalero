/**
 * Zustand store for authentication state management.
 *
 * ARCHITECTURE NOTE:
 * This store uses module-level singletons to prevent race conditions
 * when multiple components try to initialize auth simultaneously.
 * The initialization promise and auth listener registration are
 * tracked at the module level, not the store level.
 *
 * Auth is now backed by the JWT adapter (src/lib/auth/jwt-adapter.ts).
 */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { clearAuthTokenCache } from '../lib/api';
import { type AuthUser, authAdapter } from '../lib/auth/index';
import { logger } from '../lib/logger';
import { safeGetUserRole } from '../lib/typeGuards';
import type { Usuario } from '../types';

export type UserRole = 'ciudadano' | 'operador' | 'admin';

/**
 * Lightweight user object stored in the auth state.
 * Replaces the former Supabase User type.
 */
export interface StoreUser {
  id: string;
  email: string;
}

interface AuthState {
  user: StoreUser | null;
  session: { access_token: string } | null;
  profile: Usuario | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
  _hasHydrated: boolean;
}

interface AuthActions {
  setUser: (user: StoreUser | null) => void;
  setSession: (session: { access_token: string } | null) => void;
  setProfile: (profile: Usuario | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setInitialized: (initialized: boolean) => void;
  setHasHydrated: (hydrated: boolean) => void;
  reset: () => void;
  initialize: () => Promise<void>;
}

const initialState: AuthState = {
  user: null,
  session: null,
  profile: null,
  loading: true,
  error: null,
  initialized: false,
  _hasHydrated: false,
};

// ============================================
// MODULE-LEVEL SINGLETONS
// These prevent race conditions when multiple
// React islands call initialize() simultaneously
// ============================================

/** Promise that resolves when initialization is complete */
let initializationPromise: Promise<void> | null = null;

/** Tracks if auth state change listener is registered */
let authListenerRegistered = false;

/** Unsubscribe function for auth listener (for cleanup if needed) */
let authListenerUnsubscribe: (() => void) | null = null;

const inMemoryAuthStorage = {
  getItem: (_name: string) => null,
  setItem: (_name: string, _value: string) => undefined,
  removeItem: (_name: string) => undefined,
};

const authStorage = createJSONStorage(() => {
  if (typeof window === 'undefined') {
    return inMemoryAuthStorage;
  }

  const storage = window.localStorage;

  if (typeof storage?.setItem !== 'function') {
    return inMemoryAuthStorage;
  }

  return storage;
});

/** Map AuthUser from JWT adapter to the store's Usuario type */
function mapAuthUserToProfile(authUser: AuthUser): Usuario {
  return {
    id: authUser.id,
    email: authUser.email,
    nombre: [authUser.nombre, authUser.apellido].filter(Boolean).join(' ') || undefined,
    telefono: authUser.telefono || undefined,
    rol: authUser.role,
  };
}

/** Map AuthUser to the lightweight StoreUser */
function mapAuthUserToStoreUser(authUser: AuthUser): StoreUser {
  return {
    id: authUser.id,
    email: authUser.email,
  };
}

export const useAuthStore = create<AuthState & AuthActions>()(
  persist(
    (set, get) => ({
      ...initialState,

      setUser: (user) => set({ user }),
      setSession: (session) => set({ session }),
      setProfile: (profile) => set({ profile }),
      setLoading: (loading) => set({ loading }),
      setError: (error) => set({ error }),
      setInitialized: (initialized) => set({ initialized }),
      setHasHydrated: (hydrated) => set({ _hasHydrated: hydrated }),

      reset: () => {
        clearAuthTokenCache();
        set({ ...initialState, loading: false, initialized: true, _hasHydrated: true });
      },

      initialize: async () => {
        // If already initialized, return immediately
        const { initialized } = get();
        if (initialized) return;

        // If initialization is in progress, return the existing promise
        // This prevents multiple parallel initializations from different React islands
        if (initializationPromise) {
          return initializationPromise;
        }

        // Create the initialization promise
        initializationPromise = (async () => {
          set({ loading: true });

          try {
            const session = await authAdapter.getSession();

            if (session?.user) {
              const profile = mapAuthUserToProfile(session.user);
              const storeUser = mapAuthUserToStoreUser(session.user);

              set({
                user: storeUser,
                session: { access_token: session.access_token },
                profile,
                loading: false,
                initialized: true,
                error: null,
              });
            } else {
              set({
                user: null,
                session: null,
                profile: null,
                loading: false,
                initialized: true,
                error: null,
              });
            }

            // Register auth state change listener only once globally
            if (!authListenerRegistered) {
              authListenerRegistered = true;

              authListenerUnsubscribe = authAdapter.onAuthStateChange(
                (event: string, newSession: { access_token: string; user: AuthUser } | null) => {
                  if (event === 'SIGNED_IN' && newSession?.user) {
                    const profile = mapAuthUserToProfile(newSession.user);
                    const storeUser = mapAuthUserToStoreUser(newSession.user);

                    set({
                      user: storeUser,
                      session: { access_token: newSession.access_token },
                      profile,
                      loading: false,
                      error: null,
                    });
                  } else if (event === 'SIGNED_OUT') {
                    clearAuthTokenCache();
                    set({
                      user: null,
                      session: null,
                      profile: null,
                      loading: false,
                      error: null,
                    });
                  } else if (event === 'TOKEN_REFRESHED' && newSession) {
                    clearAuthTokenCache(); // Clear cache so new token is fetched
                    set({ session: { access_token: newSession.access_token } });
                  }
                }
              );
            }
          } catch (err) {
            logger.error('Error al inicializar auth:', err);
            set({
              loading: false,
              initialized: true,
              error: 'Error al inicializar autenticacion',
            });
          } finally {
            // Clear the promise so future calls (after reset) can reinitialize
            initializationPromise = null;
          }
        })();

        return initializationPromise;
      },
    }),
    {
      name: 'cc-auth-storage',
      storage: authStorage,
      partialize: (state) => ({
        user: state.user ? { id: state.user.id, email: state.user.email } : null,
        profile: state.profile,
      }),
      onRehydrateStorage: () => (state) => {
        // Mark as hydrated when storage rehydration completes
        if (state) {
          state.setHasHydrated(true);
        }
      },
    }
  )
);

// ============================================
// SELECTORS
// ============================================

/** Check if user is authenticated (user exists, not loading, and initialized) */
export const selectIsAuthenticated = (state: AuthState) =>
  !!state.user && !state.loading && state.initialized;

/** Get user role from profile with runtime validation */
export const selectUserRole = (state: AuthState): UserRole | null =>
  safeGetUserRole(state.profile?.rol);

/** Check if user can access based on allowed roles */
export const selectCanAccess = (state: AuthState, allowedRoles: UserRole[]) => {
  const role = selectUserRole(state);
  return role !== null && allowedRoles.includes(role);
};

// ============================================
// HOOK SELECTORS
// ============================================

/**
 * Hook to check if user is authenticated.
 * Returns true only when:
 * - User exists in state
 * - Loading is complete
 * - Store is initialized
 */
export function useIsAuthenticated() {
  return useAuthStore((state) => !!state.user && !state.loading && state.initialized);
}

/**
 * Hook to check if auth is still loading/initializing.
 * Use this to show loading states in UI.
 */
export function useAuthLoading() {
  return useAuthStore((state) => state.loading || !state.initialized);
}

/** Hook to get user role with runtime validation */
export function useUserRole(): UserRole | null {
  return useAuthStore((state) => safeGetUserRole(state.profile?.rol));
}

/** Hook to check if user can access based on roles */
export function useCanAccess(allowedRoles: UserRole[]): boolean {
  const role = useUserRole();
  const isAuthenticated = useIsAuthenticated();
  return isAuthenticated && role !== null && allowedRoles.includes(role);
}

// ============================================
// CLEANUP (for testing or hot reload)
// ============================================

/** Cleanup auth listener - useful for testing or HMR */
export function cleanupAuthListener() {
  if (authListenerUnsubscribe) {
    authListenerUnsubscribe();
    authListenerUnsubscribe = null;
    authListenerRegistered = false;
  }
}
