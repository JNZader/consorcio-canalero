import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockAdapter,
  resetStoreMock,
  mockProfile,
} = vi.hoisted(() => {
  return {
    mockAdapter: {
      login: vi.fn(),
      register: vi.fn(),
      loginWithGoogle: vi.fn(),
      logout: vi.fn(),
      getAccessToken: vi.fn(),
      getSession: vi.fn(),
      onAuthStateChange: vi.fn(),
    },
    resetStoreMock: vi.fn(),
    mockProfile: { rol: 'admin' as string | null },
  };
});

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: mockAdapter,
}));

vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: Object.assign(
    () => ({ user: null, session: null, profile: null, loading: false, error: null }),
    { getState: () => ({ reset: resetStoreMock, profile: mockProfile }) }
  ),
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

import {
  getUserRole,
  hasRole,
  isAdmin,
  isOperadorOrAdmin,
  resetPassword,
  signInWithEmail,
  signInWithGoogle,
  signOut,
  signUpWithEmail,
  updatePassword,
} from '../../src/lib/auth';

describe('auth library', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('location', { origin: 'http://localhost:5173' });
    mockProfile.rol = 'admin';
    mockAdapter.login.mockResolvedValue({
      access_token: 't',
      user: { id: 'u1', email: 'mail@test.com' },
    });
    mockAdapter.register.mockResolvedValue({
      access_token: 't',
      user: { id: 'u1', email: 'mail@test.com' },
    });
    mockAdapter.loginWithGoogle.mockResolvedValue(undefined);
    mockAdapter.logout.mockResolvedValue(undefined);
    global.fetch = vi.fn();
  });

  it('translates sign-in auth errors', async () => {
    mockAdapter.login.mockRejectedValueOnce(new Error('Invalid login credentials'));
    await expect(signInWithEmail('mail@test.com', 'bad')).resolves.toEqual({
      success: false,
      error: 'Email o contrasena incorrectos',
    });
  });

  it('marks sign-up as success (JWT adapter auto-logs in)', async () => {
    const result = await signUpWithEmail('mail@test.com', 'ok-password', 'Nombre');
    expect(result.success).toBe(true);
  });

  it('calls google oauth via adapter', async () => {
    await signInWithGoogle();
    expect(mockAdapter.loginWithGoogle).toHaveBeenCalled();
  });

  it('signOut clears local state and returns success', async () => {
    const removeItemSpy = vi.spyOn(localStorage, 'removeItem');
    const result = await signOut();
    expect(result.success).toBe(true);
    expect(resetStoreMock).toHaveBeenCalled();
    expect(removeItemSpy).toHaveBeenCalledWith('cc-auth-storage');
  });

  it('role helpers evaluate admin permissions', async () => {
    mockProfile.rol = 'admin';

    await expect(getUserRole('u1')).resolves.toBe('admin');
    await expect(hasRole('u1', ['admin'])).resolves.toBe(true);
    await expect(isAdmin('u1')).resolves.toBe(true);
    await expect(isOperadorOrAdmin('u1')).resolves.toBe(true);
  });

  it('translates reset and update password errors', async () => {
    // resetPassword now calls fetch to /api/v2/auth/forgot-password
    // It always returns success (fastapi-users returns 202)
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Network error')
    );
    await expect(resetPassword('mail@test.com')).resolves.toEqual({
      success: false,
      error: 'Error al enviar el email de recuperacion.',
    });

    // updatePassword imports apiFetch dynamically, mock it
    vi.doMock('../../src/lib/api/core', () => ({
      apiFetch: vi.fn().mockRejectedValueOnce(new Error('Error al cambiar la contrasena.')),
    }));
    const result = await updatePassword('new-secret');
    expect(result.success).toBe(false);
  });
});
