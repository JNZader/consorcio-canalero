import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuth } from '../../src/hooks/useAuth';

const mocks = vi.hoisted(() => ({
  signInWithEmailMock: vi.fn(),
  signInWithGoogleMock: vi.fn(),
  signUpWithEmailMock: vi.fn(),
  signOutMock: vi.fn(),
  initializeMock: vi.fn(),
  resetMock: vi.fn(),
  storeState: {} as Record<string, unknown>,
}));

vi.mock('zustand/shallow', () => ({
  useShallow: (selector: (state: unknown) => unknown) => selector,
}));

vi.mock('../../src/lib/auth', () => ({
  signInWithEmail: mocks.signInWithEmailMock,
  signInWithGoogle: mocks.signInWithGoogleMock,
  signUpWithEmail: mocks.signUpWithEmailMock,
  signOut: mocks.signOutMock,
}));

vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: (selector: (state: Record<string, unknown>) => unknown) => selector(mocks.storeState),
}));

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mocks.storeState = {
      user: null,
      session: null,
      profile: null,
      loading: false,
      initialized: true,
      error: null,
      initialize: mocks.initializeMock,
      reset: mocks.resetMock,
    };

    mocks.initializeMock.mockResolvedValue(undefined);
    mocks.signInWithEmailMock.mockResolvedValue({ success: true });
    mocks.signInWithGoogleMock.mockResolvedValue({ success: true });
    mocks.signUpWithEmailMock.mockResolvedValue({ success: true });
    mocks.signOutMock.mockResolvedValue({ success: true });
  });

  // ============================================
  // INITIALIZATION
  // ============================================

  describe('Initialization', () => {
    it('auto-initializes store when not initialized', () => {
      mocks.storeState.initialized = false;

      renderHook(() => useAuth());

      expect(mocks.initializeMock).toHaveBeenCalledTimes(1);
    });

    it('catches mutation: should not auto-initialize when autoInitialize is false', () => {
      mocks.storeState.initialized = false;

      renderHook(() => useAuth({ autoInitialize: false }));

      expect(mocks.initializeMock).not.toHaveBeenCalled();
    });

    it('should not initialize if already initialized', () => {
      mocks.storeState.initialized = true;

      renderHook(() => useAuth());

      expect(mocks.initializeMock).not.toHaveBeenCalled();
    });

    it('catches mutation: should only initialize once on mount', () => {
      mocks.storeState.initialized = false;

      const { rerender } = renderHook(() => useAuth());

      expect(mocks.initializeMock).toHaveBeenCalledTimes(1);

      // Rerender with same props
      rerender();

      expect(mocks.initializeMock).toHaveBeenCalledTimes(1);
    });
  });

  // ============================================
  // INITIAL STATE
  // ============================================

  describe('Initial state when not authenticated', () => {
    it('should return null user when not authenticated', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.user).toBeNull();
    });

    it('should return isAuthenticated as false when user is null', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isAuthenticated).toBe(false);
    });

    it('catches mutation: should set isLoading based on loading state', () => {
      mocks.storeState.loading = true;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isLoading).toBe(true);
    });

    it('should return null role when not authenticated', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.role).toBeNull();
    });

    it('should expose all role utilities', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current).toHaveProperty('hasRole');
      expect(result.current).toHaveProperty('isAdmin');
      expect(result.current).toHaveProperty('isOperador');
      expect(result.current).toHaveProperty('isStaff');
      expect(result.current).toHaveProperty('isCiudadano');
      expect(result.current).toHaveProperty('canAccess');
    });
  });

  // ============================================
  // AUTHENTICATION STATE
  // ============================================

  describe('Authentication state computation', () => {
    it('computes authentication and role helpers from store state', () => {
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.profile = { rol: 'admin' };
      mocks.storeState.initialized = true;
      mocks.storeState.loading = false;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.role).toBe('admin');
    });

    it('catches mutation: should not be authenticated when loading', () => {
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.loading = true;
      mocks.storeState.initialized = true;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isAuthenticated).toBe(false);
    });

    it('catches mutation: should not be authenticated when not initialized', () => {
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.loading = false;
      mocks.storeState.initialized = false;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isAuthenticated).toBe(false);
    });
  });

  // ============================================
  // ROLE CHECKING
  // ============================================

  describe('Role checking utilities', () => {
    beforeEach(() => {
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.profile = { rol: 'admin' };
      mocks.storeState.initialized = true;
      mocks.storeState.loading = false;
    });

    it('should check single role', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.hasRole('admin')).toBe(true);
    });

    it('should check multiple roles', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.hasRole(['admin', 'operador'])).toBe(true);
      expect(result.current.hasRole(['operador', 'ciudadano'])).toBe(false);
    });

    it('catches mutation: should return false for hasRole when not authenticated', () => {
      mocks.storeState.user = null;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.hasRole('admin')).toBe(false);
    });

    it('should compute isAdmin role utility', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isAdmin).toBe(true);
    });

    it('should compute isOperador role utility', () => {
      mocks.storeState.profile = { rol: 'operador' };

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isOperador).toBe(true);
      expect(result.current.isAdmin).toBe(false);
    });

    it('should compute isStaff role utility', () => {
      mocks.storeState.profile = { rol: 'admin' };

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isStaff).toBe(true);
    });

    it('should compute isCiudadano role utility', () => {
      mocks.storeState.profile = { rol: 'ciudadano' };

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isCiudadano).toBe(true);
      expect(result.current.isStaff).toBe(false);
    });

    it('catches mutation: canAccess should return true for empty allowed roles', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.canAccess([])).toBe(true);
    });

    it('should check access with canAccess', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.canAccess(['admin'])).toBe(true);
      expect(result.current.canAccess(['operador'])).toBe(false);
    });

    it('catches mutation: canAccess should return false when not authenticated', () => {
      mocks.storeState.user = null;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.canAccess(['admin'])).toBe(false);
    });

    // ── Mutation killers for isLoading / isAuthenticated / canAccess ──

    it('kills mutation: isLoading is true when loading=false but initialized=false (|| not &&)', () => {
      // isLoading = loading || !initialized
      // If mutated to &&: loading(false) && !initialized(true) = false (WRONG, should be true)
      mocks.storeState.loading = false;
      mocks.storeState.initialized = false;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isLoading).toBe(true);
    });

    it('kills mutation: isLoading is false when loading=false and initialized=true', () => {
      mocks.storeState.loading = false;
      mocks.storeState.initialized = true;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isLoading).toBe(false);
    });

    it('kills mutation: isAuthenticated requires ALL three conditions (!!user && !loading && initialized)', () => {
      // Test each condition independently to kill && → || mutations

      // user present, not loading, initialized → true
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.loading = false;
      mocks.storeState.initialized = true;
      const { result: r1 } = renderHook(() => useAuth({ autoInitialize: false }));
      expect(r1.current.isAuthenticated).toBe(true);

      // user null → false (even if not loading and initialized)
      mocks.storeState.user = null;
      mocks.storeState.loading = false;
      mocks.storeState.initialized = true;
      const { result: r2 } = renderHook(() => useAuth({ autoInitialize: false }));
      expect(r2.current.isAuthenticated).toBe(false);

      // loading true → false (even with user and initialized)
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.loading = true;
      mocks.storeState.initialized = true;
      const { result: r3 } = renderHook(() => useAuth({ autoInitialize: false }));
      expect(r3.current.isAuthenticated).toBe(false);

      // not initialized → false (even with user and not loading)
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.loading = false;
      mocks.storeState.initialized = false;
      const { result: r4 } = renderHook(() => useAuth({ autoInitialize: false }));
      expect(r4.current.isAuthenticated).toBe(false);
    });

    it('kills mutation: canAccess with empty roles returns true ONLY when authenticated', () => {
      // canAccess([]): allowedRoles.length === 0 → return true
      // Must be authenticated first, then empty roles = unrestricted
      mocks.storeState.user = { id: 'u-1' };
      mocks.storeState.profile = { rol: 'ciudadano' };
      mocks.storeState.initialized = true;
      mocks.storeState.loading = false;

      const { result: r1 } = renderHook(() => useAuth({ autoInitialize: false }));
      expect(r1.current.canAccess([])).toBe(true);

      // Not authenticated + empty roles → still false
      mocks.storeState.user = null;
      const { result: r2 } = renderHook(() => useAuth({ autoInitialize: false }));
      expect(r2.current.canAccess([])).toBe(false);
    });
  });

  // ============================================
  // AUTH ACTIONS
  // ============================================

  describe('Authentication actions', () => {
    it('forwards auth actions to auth library and store actions', async () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      await act(async () => {
        await result.current.login('admin@example.com', 'secret');
        await result.current.loginWithGoogle();
        await result.current.register('new@example.com', 'secret', 'Nuevo Usuario');
        await result.current.logout();
        await result.current.initialize();
        result.current.reset();
      });

      expect(mocks.signInWithEmailMock).toHaveBeenCalledWith('admin@example.com', 'secret');
      expect(mocks.signInWithGoogleMock).toHaveBeenCalledTimes(1);
      expect(mocks.signUpWithEmailMock).toHaveBeenCalledWith(
        'new@example.com',
        'secret',
        'Nuevo Usuario'
      );
      expect(mocks.signOutMock).toHaveBeenCalledTimes(1);
      expect(mocks.initializeMock).toHaveBeenCalledTimes(1);
      expect(mocks.resetMock).toHaveBeenCalledTimes(1);
    });

    it('should call login with correct parameters', async () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      await act(async () => {
        await result.current.login('test@example.com', 'password123');
      });

      expect(mocks.signInWithEmailMock).toHaveBeenCalledWith('test@example.com', 'password123');
    });

    it('should call logout', async () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      await act(async () => {
        await result.current.logout();
      });

      expect(mocks.signOutMock).toHaveBeenCalledTimes(1);
    });

    it('catches mutation: should call register with all parameters', async () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      await act(async () => {
        await result.current.register('new@example.com', 'secret123', 'Full Name');
      });

      expect(mocks.signUpWithEmailMock).toHaveBeenCalledWith(
        'new@example.com',
        'secret123',
        'Full Name'
      );
    });

    it('should expose action functions', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(typeof result.current.login).toBe('function');
      expect(typeof result.current.loginWithGoogle).toBe('function');
      expect(typeof result.current.register).toBe('function');
      expect(typeof result.current.logout).toBe('function');
      expect(typeof result.current.initialize).toBe('function');
      expect(typeof result.current.reset).toBe('function');
    });
  });

  // ============================================
  // ERROR STATE
  // ============================================

  describe('Error state', () => {
    it('should expose error from store', () => {
      mocks.storeState.error = 'Login failed';

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.error).toBe('Login failed');
    });

    it('should expose null error when no error', () => {
      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.error).toBeNull();
    });
  });

  // ============================================
  // STATE CONSISTENCY
  // ============================================

  describe('State consistency', () => {
    it('should expose user from store', () => {
      mocks.storeState.user = { id: 'u-1', email: 'test@example.com' };

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.user).toEqual({ id: 'u-1', email: 'test@example.com' });
    });

    it('should expose session from store', () => {
      mocks.storeState.session = { access_token: 'token' };

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.session).toEqual({ access_token: 'token' });
    });

    it('should expose profile from store', () => {
      mocks.storeState.profile = { id: 'p-1', nombre: 'Test User', rol: 'admin' };

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.profile).toEqual({ id: 'p-1', nombre: 'Test User', rol: 'admin' });
    });

    it('catches mutation: isInitialized should reflect store state', () => {
      mocks.storeState.initialized = true;

      const { result } = renderHook(() => useAuth({ autoInitialize: false }));

      expect(result.current.isInitialized).toBe(true);
    });
  });
});
