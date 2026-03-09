import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  mockAuth,
  mockClient,
  resetStoreMock,
} = vi.hoisted(() => {
  const auth = {
    signInWithPassword: vi.fn(),
    signUp: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(),
    resetPasswordForEmail: vi.fn(),
    updateUser: vi.fn(),
  };

  const client = {
    auth,
    from: vi.fn(),
  };

  return {
    mockAuth: auth,
    mockClient: client,
    resetStoreMock: vi.fn(),
  };
});

vi.mock('../../src/lib/supabase', () => ({
  getSupabaseClient: () => mockClient,
}));

vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: Object.assign(
    () => ({ user: null, session: null, profile: null, loading: false, error: null }),
    { getState: () => ({ reset: resetStoreMock }) }
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

const authError = (message: string) =>
  ({ message, status: 400, name: 'AuthError' }) as unknown as Error;

describe('auth library', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('location', { origin: 'http://localhost:5173' });
    mockAuth.signInWithPassword.mockResolvedValue({
      data: { user: { id: 'u1' }, session: { access_token: 't' } },
      error: null,
    });
    mockAuth.signUp.mockResolvedValue({
      data: { user: { id: 'u1' }, session: { access_token: 't' } },
      error: null,
    });
    mockAuth.signInWithOAuth.mockResolvedValue({ data: {}, error: null });
    mockAuth.signOut.mockResolvedValue({ error: null });
    mockAuth.resetPasswordForEmail.mockResolvedValue({ error: null });
    mockAuth.updateUser.mockResolvedValue({ error: null });
  });

  it('translates sign-in auth errors', async () => {
    mockAuth.signInWithPassword.mockResolvedValueOnce({
      data: { user: null, session: null },
      error: authError('Invalid login credentials'),
    });
    await expect(signInWithEmail('mail@test.com', 'bad')).resolves.toEqual({
      success: false,
      error: 'Email o contrasena incorrectos',
    });
  });

  it('marks sign-up confirmation when session is missing', async () => {
    mockAuth.signUp.mockResolvedValueOnce({
      data: { user: { id: 'u1' }, session: null },
      error: null,
    });
    const result = await signUpWithEmail('mail@test.com', 'ok-password', 'Nombre');
    expect(result.success).toBe(true);
    expect(result.needsEmailConfirmation).toBe(true);
  });

  it('calls google oauth with callback redirect', async () => {
    await signInWithGoogle();
    expect(mockAuth.signInWithOAuth).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'google',
        options: expect.objectContaining({ redirectTo: 'http://localhost:5173/auth/callback' }),
      })
    );
  });

  it('signOut clears local state and returns success', async () => {
    const removeItemSpy = vi.spyOn(localStorage, 'removeItem');
    const result = await signOut();
    expect(result.success).toBe(true);
    expect(resetStoreMock).toHaveBeenCalled();
    expect(removeItemSpy).toHaveBeenCalledWith('cc-auth-storage');
  });

  it('role helpers evaluate admin permissions', async () => {
    const queryBuilder = {
      select: vi.fn().mockReturnThis(),
      eq: vi.fn().mockReturnThis(),
      single: vi.fn().mockResolvedValue({ data: { rol: 'admin' }, error: null }),
    };
    mockClient.from.mockReturnValue(queryBuilder);

    await expect(getUserRole('u1')).resolves.toBe('admin');
    await expect(hasRole('u1', ['admin'])).resolves.toBe(true);
    await expect(isAdmin('u1')).resolves.toBe(true);
    await expect(isOperadorOrAdmin('u1')).resolves.toBe(true);
  });

  it('translates reset and update password errors', async () => {
    mockAuth.resetPasswordForEmail.mockResolvedValueOnce({
      error: authError('Email rate limit exceeded'),
    });
    mockAuth.updateUser.mockResolvedValueOnce({
      error: authError('New password should be different from the old password'),
    });

    await expect(resetPassword('mail@test.com')).resolves.toEqual({
      success: false,
      error: 'Demasiados intentos. Intenta de nuevo mas tarde',
    });
    await expect(updatePassword('new-secret')).resolves.toEqual({
      success: false,
      error: 'La nueva contrasena debe ser diferente a la anterior',
    });
  });
});
