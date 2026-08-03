import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockLoginWithGoogle, mockSignOut, mockNotificationsShow, mockLoggerError } = vi.hoisted(() => ({
  mockLoginWithGoogle: vi.fn(),
  mockSignOut: vi.fn(),
  mockNotificationsShow: vi.fn(),
  mockLoggerError: vi.fn(),
}));

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: {
    loginWithGoogle: mockLoginWithGoogle,
  },
}));

vi.mock('../../src/lib/auth', () => ({
  signOut: mockSignOut,
}));

let mockAuthState: Record<string, unknown> = {
  user: null,
  profile: null,
  initialized: true,
  loading: false,
};

vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: (selector: (state: Record<string, unknown>) => unknown) => selector(mockAuthState),
}));

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: mockNotificationsShow,
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: mockLoggerError,
  },
}));

import { useContactVerification } from '../../src/hooks/useContactVerification';

function setAuthState(overrides: Partial<typeof mockAuthState>) {
  mockAuthState = {
    user: null,
    profile: null,
    initialized: true,
    loading: false,
    ...overrides,
  };
}

describe('useContactVerification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuthState({});
  });

  it('returns initial state when user is not authenticated', () => {
    const { result } = renderHook(() => useContactVerification());

    expect(result.current.contactoVerificado).toBe(false);
    expect(result.current.loading).toBe(false);
    expect(result.current.userEmail).toBeNull();
    expect(result.current.userName).toBeNull();
  });

  it('derives verified state and user info from auth store', () => {
    setAuthState({
      user: { email: 'test@example.com' },
      profile: { nombre: 'Test User' },
      initialized: true,
    });

    const { result } = renderHook(() => useContactVerification());

    expect(result.current.contactoVerificado).toBe(true);
    expect(result.current.userEmail).toBe('test@example.com');
    expect(result.current.userName).toBe('Test User');
  });

  it('requires both user and initialized to mark contact as verified', () => {
    setAuthState({ user: { email: 'test@example.com' }, initialized: false });
    const { result, rerender } = renderHook(() => useContactVerification());

    expect(result.current.contactoVerificado).toBe(false);

    setAuthState({ user: { email: 'test@example.com' }, initialized: true });
    rerender();
    expect(result.current.contactoVerificado).toBe(true);

    setAuthState({ user: null, initialized: true });
    rerender();
    expect(result.current.contactoVerificado).toBe(false);
  });

  it('calls onVerified with email and optional name', () => {
    const onVerified = vi.fn();
    setAuthState({
      user: { email: 'test@example.com' },
      profile: { nombre: 'Test User' },
      initialized: true,
    });

    renderHook(() => useContactVerification({ onVerified }));
    expect(onVerified).toHaveBeenCalledWith('test@example.com', 'Test User');

    vi.clearAllMocks();
    setAuthState({ user: { email: 'solo@example.com' }, profile: null, initialized: true });
    renderHook(() => useContactVerification({ onVerified }));
    expect(onVerified).toHaveBeenCalledWith('solo@example.com', undefined);
  });

  it('starts Google login successfully', async () => {
    mockLoginWithGoogle.mockResolvedValue(undefined);
    const { result } = renderHook(() => useContactVerification());

    await act(async () => {
      await result.current.loginWithGoogle();
    });

    expect(mockLoginWithGoogle).toHaveBeenCalledTimes(1);
    expect(mockNotificationsShow).not.toHaveBeenCalled();
  });

  it('shows an error notification when Google login fails', async () => {
    mockLoginWithGoogle.mockRejectedValue(new Error('OAuth failed'));
    const { result } = renderHook(() => useContactVerification());

    await act(async () => {
      await result.current.loginWithGoogle();
    });

    expect(mockLoggerError).toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(mockNotificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Error',
        message: 'No se pudo iniciar sesion con Google',
        color: 'red',
      })
    );
  });

  it('logs out and shows a success notification', async () => {
    mockSignOut.mockResolvedValue(undefined);
    const { result } = renderHook(() => useContactVerification());

    await act(async () => {
      await result.current.logout();
    });

    expect(mockSignOut).toHaveBeenCalledTimes(1);
    expect(mockNotificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Sesion cerrada',
        message: 'Has cerrado sesion correctamente',
        color: 'blue',
      })
    );
  });

  it('shows an accurate warning when only local signout is confirmed', async () => {
    mockSignOut.mockResolvedValue({
      success: true,
      warning: 'remote revocation unconfirmed',
    });
    const { result } = renderHook(() => useContactVerification());

    await act(async () => {
      await result.current.logout();
    });

    expect(mockNotificationsShow).toHaveBeenCalledWith({
      title: 'Sesión cerrada localmente',
      message: 'remote revocation unconfirmed',
      color: 'yellow',
    });
  });

  it('handles logout errors gracefully', async () => {
    mockSignOut.mockRejectedValue(new Error('Logout failed'));
    const { result } = renderHook(() => useContactVerification());

    await act(async () => {
      await result.current.logout();
    });

    expect(mockLoggerError).toHaveBeenCalled();
    expect(result.current.contactoVerificado).toBe(false);
  });
});
