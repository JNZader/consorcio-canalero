/**
 * Zustand store for authentication state management.
 *
 * ARCHITECTURE NOTE:
 * This store uses module-level singletons to prevent race conditions
 * when multiple components try to initialize auth simultaneously.
 * The initialization promise and auth listener registration are
 * tracked at the module level, not the store level.
 */

import type { Session, User } from '@supabase/supabase-js';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { clearAuthTokenCache } from '../lib/api';
import { logger } from '../lib/logger';
import { parseUsuario, safeGetUserRole } from '../lib/typeGuards';
import { type Usuario, getSupabaseClient } from '../lib/supabase';

export type UserRole = 'ciudadano' | 'operador' | 'admin';

interface AuthState {
  user: User | null;
  session: Session | null;
  profile: Usuario | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
  _hasHydrated: boolean;
}

interface AuthActions {
  setUser: (user: User | null) => void;
  setSession: (session: Session | null) => void;
  setProfile: (profile: Usuario | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setInitialized: (initialized: boolean) => void;
  setHasHydrated: (hydrated: boolean) => void;
  reset: () => void;
  initialize: () => Promise<void>;
  loadProfile: (userId: string) => Promise<Usuario | null>;
  syncProfile: (user: User) => Promise<Usuario | null>;
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

      loadProfile: async (userId: string): Promise<Usuario | null> => {
        try {
          const { data, error } = await getSupabaseClient()
            .from('perfiles')
            .select('*')
            .eq('id', userId)
            .single();

          if (error) {
            logger.error('Error al cargar perfil:', error);
            return null;
          }

          // Validate API response at runtime
          const profile = parseUsuario(data);
          if (!profile) {
            logger.error('Invalid profile data from API:', data);
            return null;
          }

          return profile;
        } catch (err) {
          logger.error('Error al cargar perfil:', err);
          return null;
        }
      },

      syncProfile: async (user: User): Promise<Usuario | null> => {
        const { loadProfile } = get();
        try {
          let profile = await loadProfile(user.id);

          if (!profile) {
            const newProfile: Usuario = {
              id: user.id,
              email: user.email || '',
              nombre: user.user_metadata?.full_name || user.user_metadata?.name || '',
              rol: 'ciudadano',
            };

            const { data, error } = await getSupabaseClient()
              .from('perfiles')
              .insert(newProfile)
              .select()
              .single();

            if (error) {
              if (error.code === '23505') {
                profile = await loadProfile(user.id);
              } else {
                logger.error('Error al crear perfil:', error);
                return null;
              }
            } else {
              // Validate API response at runtime
              profile = parseUsuario(data);
              if (!profile) {
                logger.error('Invalid profile data after creation:', data);
                return null;
              }
            }
          }

          return profile;
        } catch (err) {
          logger.error('Error al sincronizar perfil:', err);
          return null;
        }
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
          const { syncProfile } = get();
          set({ loading: true });

          try {
            const { data: { session }, error } = await getSupabaseClient().auth.getSession();

            if (error) throw error;

            if (session?.user) {
              const profile = await syncProfile(session.user);
              set({
                user: session.user,
                session,
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

              const { data: { subscription } } = getSupabaseClient().auth.onAuthStateChange(
                async (event, newSession) => {
                  const currentState = get();

                  if (event === 'SIGNED_IN' && newSession?.user) {
                    const profile = await currentState.syncProfile(newSession.user);
                    set({
                      user: newSession.user,
                      session: newSession,
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
                    set({ session: newSession });
                  }
                }
              );

              authListenerUnsubscribe = subscription.unsubscribe;
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
