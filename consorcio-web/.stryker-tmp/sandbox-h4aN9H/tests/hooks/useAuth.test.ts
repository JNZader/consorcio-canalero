// @ts-nocheck
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

  it('auto-initializes store when not initialized', () => {
    mocks.storeState.initialized = false;

    renderHook(() => useAuth());

    expect(mocks.initializeMock).toHaveBeenCalledTimes(1);
  });

  it('computes authentication and role helpers from store state', () => {
    mocks.storeState.user = { id: 'u-1' };
    mocks.storeState.profile = { rol: 'admin' };
    mocks.storeState.initialized = true;
    mocks.storeState.loading = false;

    const { result } = renderHook(() => useAuth({ autoInitialize: false }));

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.role).toBe('admin');
    expect(result.current.isAdmin).toBe(true);
    expect(result.current.isStaff).toBe(true);
    expect(result.current.isCiudadano).toBe(false);
    expect(result.current.hasRole(['admin', 'operador'])).toBe(true);
    expect(result.current.canAccess([])).toBe(true);
    expect(result.current.canAccess(['operador'])).toBe(false);
    expect(mocks.initializeMock).not.toHaveBeenCalled();
  });

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
});
