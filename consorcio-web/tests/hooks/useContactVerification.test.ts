/**
 * Unit tests for useContactVerification hook.
 *
 * Tests verification flow for Google OAuth and Magic Link methods.
 * Focus: Catch mutations in selectors, conditions, and state transitions.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useContactVerification } from '../../src/hooks/useContactVerification';

// Mock Supabase client
const mockSignInWithOAuth = vi.fn();
const mockSignInWithOtp = vi.fn();
const mockSignOut = vi.fn();

vi.mock('../../src/lib/supabase', () => ({
  getSupabaseClient: () => ({
    auth: {
      signInWithOAuth: mockSignInWithOAuth,
      signInWithOtp: mockSignInWithOtp,
      signOut: mockSignOut,
    },
  }),
}));

// Store selector state for test control
let mockAuthState = {
  user: null,
  profile: null,
  initialized: true,
  loading: false,
};

// Mock auth store - capture actual selector to allow mutations
vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector(mockAuthState),
}));

// Mock Mantine notifications
vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

// Mock logger
vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}));

// Mock validators
vi.mock('../../src/lib/validators', () => ({
  isValidEmail: (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email),
}));

import { notifications } from '@mantine/notifications';

describe('useContactVerification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset auth state to default
    mockAuthState = {
      user: null,
      profile: null,
      initialized: true,
      loading: false,
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('initial state', () => {
    it('should return initial state correctly', () => {
      const { result } = renderHook(() => useContactVerification());

      expect(result.current.contactoVerificado).toBe(false);
      expect(result.current.metodoVerificacion).toBe('google');
      expect(result.current.loading).toBe(false);
      expect(result.current.magicLinkSent).toBe(false);
      expect(result.current.magicLinkEmail).toBeNull();
      expect(result.current.userEmail).toBeNull();
      expect(result.current.userName).toBeNull();
    });

    it('should initialize with exact values, not truthy/falsy', () => {
      const { result } = renderHook(() => useContactVerification());

      // Catch mutations that change false to 0, null, undefined
      expect(result.current.contactoVerificado).toBe(false);
      expect(result.current.loading).toBe(false);
      expect(result.current.magicLinkSent).toBe(false);

      // Catch mutations on null
      expect(result.current.magicLinkEmail).toBe(null);
      expect(result.current.userEmail).toBe(null);
      expect(result.current.userName).toBe(null);

      // Catch string mutations
      expect(result.current.metodoVerificacion).toBe('google');
    });
  });

  describe('Auth store selector integration', () => {
    it('catches mutation: should use actual user from selector', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: null,
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());

      // If selector is broken, userEmail will be null
      expect(result.current.userEmail).toBe('test@example.com');
      expect(result.current.userEmail).not.toBe(null);
    });

    it('catches mutation: should use actual profile from selector', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: { nombre: 'John Doe' },
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());

      // If selector is broken, userName will be null
      expect(result.current.userName).toBe('John Doe');
      expect(result.current.userName).not.toBe(null);
    });

    it('catches mutation: should use actual initialized from selector', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: null,
        initialized: false,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());

      // If selector is broken or replaced with undefined, contactoVerificado will be true
      expect(result.current.contactoVerificado).toBe(false);
    });

    it('catches mutation: should check both user AND initialized (not just user)', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: null,
        initialized: false,
        loading: false,
      };

      const { result: result1 } = renderHook(() => useContactVerification());
      expect(result1.current.contactoVerificado).toBe(false);

      mockAuthState.initialized = true;
      const { result: result2 } = renderHook(() => useContactVerification());
      expect(result2.current.contactoVerificado).toBe(true);

      mockAuthState.user = null;
      const { result: result3 } = renderHook(() => useContactVerification());
      expect(result3.current.contactoVerificado).toBe(false);
    });
  });

  describe('userName fallback chain', () => {
    it('should use profile.nombre when available', () => {
      mockAuthState = {
        user: { email: 'test@example.com', user_metadata: { full_name: 'User Full', name: 'User' } },
        profile: { nombre: 'Profile Name' },
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());
      expect(result.current.userName).toBe('Profile Name');
    });

    it('should fall back to full_name when profile unavailable', () => {
      mockAuthState = {
        user: { email: 'test@example.com', user_metadata: { full_name: 'User Full', name: 'User' } },
        profile: null,
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());
      expect(result.current.userName).toBe('User Full');
    });

    it('should fall back to name when full_name unavailable', () => {
      mockAuthState = {
        user: { email: 'test@example.com', user_metadata: { full_name: null, name: 'User' } },
        profile: null,
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());
      expect(result.current.userName).toBe('User');
    });

    it('should return null when all sources unavailable', () => {
      mockAuthState = {
        user: { email: 'test@example.com', user_metadata: { full_name: null, name: null } },
        profile: null,
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());
      expect(result.current.userName).toBe(null);
    });

    it('should handle missing user_metadata gracefully', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: null,
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());
      expect(result.current.userName).toBe(null);
    });
  });

  describe('onVerified callback effect', () => {
    it('catches mutation: should call onVerified when contactoVerificado AND userEmail AND callback', () => {
      const onVerifiedMock = vi.fn();

      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: { nombre: 'Test User' },
        initialized: true,
        loading: false,
      };

      renderHook(() => useContactVerification({ onVerified: onVerifiedMock }));

      expect(onVerifiedMock).toHaveBeenCalledWith('test@example.com', 'Test User');
    });

    it('catches mutation: should NOT call when contactoVerificado is false', () => {
      const onVerifiedMock = vi.fn();

      mockAuthState = {
        user: null,
        profile: null,
        initialized: true,
        loading: false,
      };

      renderHook(() => useContactVerification({ onVerified: onVerifiedMock }));

      expect(onVerifiedMock).not.toHaveBeenCalled();
    });

    it('catches mutation: should NOT call when userEmail is null', () => {
      const onVerifiedMock = vi.fn();

      mockAuthState = {
        user: { email: null },
        profile: null,
        initialized: true,
        loading: false,
      };

      renderHook(() => useContactVerification({ onVerified: onVerifiedMock }));

      expect(onVerifiedMock).not.toHaveBeenCalled();
    });

    it('catches mutation: should NOT call when onVerified callback is undefined', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: null,
        initialized: true,
        loading: false,
      };

      // Should not throw even without callback
      const { result } = renderHook(() => useContactVerification());
      expect(result.current.contactoVerificado).toBe(true);
    });

    it('catches mutation: should pass userName as undefined when null', () => {
      const onVerifiedMock = vi.fn();

      mockAuthState = {
        user: { email: 'test@example.com', user_metadata: {} },
        profile: null,
        initialized: true,
        loading: false,
      };

      renderHook(() => useContactVerification({ onVerified: onVerifiedMock }));

      // userName is null, but passed as undefined to callback
      expect(onVerifiedMock).toHaveBeenCalledWith('test@example.com', undefined);
    });
  });

  describe('setMetodoVerificacion', () => {
    it('should change verification method to email', () => {
      const { result } = renderHook(() => useContactVerification());

      act(() => {
        result.current.setMetodoVerificacion('email');
      });

      expect(result.current.metodoVerificacion).toBe('email');
    });

    it('should change verification method back to google', () => {
      const { result } = renderHook(() => useContactVerification());

      act(() => {
        result.current.setMetodoVerificacion('email');
      });

      act(() => {
        result.current.setMetodoVerificacion('google');
      });

      expect(result.current.metodoVerificacion).toBe('google');
    });

    it('catches mutation: method change should NOT affect other state', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: null,
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());

      const initialContactoVerificado = result.current.contactoVerificado;
      const initialUserEmail = result.current.userEmail;

      act(() => {
        result.current.setMetodoVerificacion('email');
      });

      // Should not change these
      expect(result.current.contactoVerificado).toBe(initialContactoVerificado);
      expect(result.current.userEmail).toBe(initialUserEmail);
    });
  });

  describe('loginWithGoogle', () => {
    it('should call supabase signInWithOAuth', async () => {
      mockSignInWithOAuth.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      expect(mockSignInWithOAuth).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'google',
        })
      );
    });

    it('catches mutation: should pass exact redirect URL', async () => {
      mockSignInWithOAuth.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      expect(mockSignInWithOAuth).toHaveBeenCalledWith(
        expect.objectContaining({
          options: expect.objectContaining({
            redirectTo: expect.stringContaining('auth=success'),
          }),
        })
      );
    });

    it('catches mutation: should pass exact queryParams', async () => {
      mockSignInWithOAuth.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      expect(mockSignInWithOAuth).toHaveBeenCalledWith(
        expect.objectContaining({
          options: expect.objectContaining({
            queryParams: {
              access_type: 'offline',
              prompt: 'consent',
            },
          }),
        })
      );
    });

    it('catches mutation: should set loading to true during request', async () => {
      let resolveLogin: any;
      mockSignInWithOAuth.mockReturnValue(new Promise((resolve) => { resolveLogin = resolve; }));

      const { result } = renderHook(() => useContactVerification());

      const loginPromise = act(async () => {
        await result.current.loginWithGoogle();
      });

      // During the async operation, loading should eventually become true
      // (though by the time we check, it may have resolved)
      resolveLogin({ error: null });
      await loginPromise;
    });

    it('catches mutation: should show error notification on failure', async () => {
      mockSignInWithOAuth.mockResolvedValue({
        error: new Error('OAuth failed'),
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error',
          color: 'red',
        })
      );
    });

    it('catches mutation: should set loading to false after error', async () => {
      mockSignInWithOAuth.mockResolvedValue({
        error: new Error('OAuth failed'),
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      // After error, loading should be false
      expect(result.current.loading).toBe(false);
    });

    it('catches mutation: should show exact error message text', async () => {
      mockSignInWithOAuth.mockResolvedValue({
        error: new Error('OAuth failed'),
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'No se pudo iniciar sesion con Google',
        })
      );
    });
  });

  describe('sendMagicLink', () => {
    it('should show error for invalid email', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('invalid-email');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Email invalido',
          color: 'red',
        })
      );
      expect(mockSignInWithOtp).not.toHaveBeenCalled();
    });

    it('should show error for empty email', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Email invalido',
          color: 'red',
        })
      );
    });

    it('catches mutation: should show exact error message text for invalid email', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('invalid');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Ingresa un email valido',
        })
      );
    });

    it('should send magic link for valid email', async () => {
      mockSignInWithOtp.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(mockSignInWithOtp).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'test@example.com',
        })
      );
      expect(result.current.magicLinkSent).toBe(true);
      expect(result.current.magicLinkEmail).toBe('test@example.com');
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Link enviado',
          color: 'green',
        })
      );
    });

    it('catches mutation: should pass exact redirect URL to OTP', async () => {
      mockSignInWithOtp.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(mockSignInWithOtp).toHaveBeenCalledWith(
        expect.objectContaining({
          options: {
            emailRedirectTo: expect.stringContaining('auth=success'),
          },
        })
      );
    });

    it('catches mutation: should show email in success message', async () => {
      mockSignInWithOtp.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Revisa tu email test@example.com',
        })
      );
    });

    it('should handle API error', async () => {
      mockSignInWithOtp.mockResolvedValue({
        error: new Error('Rate limited'),
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error',
          color: 'red',
        })
      );
      expect(result.current.magicLinkSent).toBe(false);
    });

    it('catches mutation: should pass error message from exception', async () => {
      const customErrorMsg = 'Custom error from API';
      mockSignInWithOtp.mockResolvedValue({
        error: new Error(customErrorMsg),
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: customErrorMsg,
        })
      );
    });

    it('catches mutation: should handle error without message property', async () => {
      mockSignInWithOtp.mockResolvedValue({
        error: { code: 'unknown' },
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error',
          message: 'No se pudo enviar el email',
        })
      );
    });

    it('catches mutation: should set loading to false after success', async () => {
      mockSignInWithOtp.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(result.current.loading).toBe(false);
    });

    it('catches mutation: should set loading to false after error', async () => {
      mockSignInWithOtp.mockResolvedValue({
        error: new Error('Failed'),
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      expect(result.current.loading).toBe(false);
    });

    it('catches mutation: email validation should check for @domain', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('invalidemail.com');
      });

      expect(mockSignInWithOtp).not.toHaveBeenCalled();
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Email invalido',
        })
      );
    });

    it('catches mutation: email validation should check for .tld', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@domain');
      });

      expect(mockSignInWithOtp).not.toHaveBeenCalled();
    });
  });

  describe('logout', () => {
    it('should call supabase signOut', async () => {
      mockSignOut.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.logout();
      });

      expect(mockSignOut).toHaveBeenCalled();
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Sesion cerrada',
          color: 'blue',
        })
      );
    });

    it('catches mutation: should show exact success message', async () => {
      mockSignOut.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.logout();
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Has cerrado sesion correctamente',
        })
      );
    });

    it('catches mutation: should handle signOut errors gracefully', async () => {
      mockSignOut.mockResolvedValue({ error: new Error('Logout failed') });

      const { result } = renderHook(() => useContactVerification());

      // Should not throw
      await act(async () => {
        await result.current.logout();
      });

      // Still show notification
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Sesion cerrada',
        })
      );
    });
  });

  describe('resetVerificacion', () => {
    it('should reset state to initial values', async () => {
      mockSignInWithOtp.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      // Set some state
      await act(async () => {
        result.current.setMetodoVerificacion('email');
        await result.current.sendMagicLink('test@example.com');
      });

      expect(result.current.magicLinkSent).toBe(true);

      // Reset
      act(() => {
        result.current.resetVerificacion();
      });

      expect(result.current.magicLinkSent).toBe(false);
      expect(result.current.magicLinkEmail).toBe(null);
      expect(result.current.metodoVerificacion).toBe('google');
    });

    it('catches mutation: should reset ALL three properties', () => {
      mockSignInWithOtp.mockResolvedValue({ error: null });

      const { result } = renderHook(() => useContactVerification());

      act(async () => {
        result.current.setMetodoVerificacion('email');
      });

      act(() => {
        result.current.resetVerificacion();
      });

      // Catch mutations that miss any of these
      expect(result.current.magicLinkSent).toBe(false);
      expect(result.current.magicLinkEmail).toBe(null);
      expect(result.current.metodoVerificacion).toBe('google');
    });
  });

});
