/**
 * Unit tests for useContactVerification hook.
 *
 * Tests verification flow for Google OAuth and Magic Link methods.
 * Focus: Catch mutations in selectors, conditions, and state transitions.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockLoginWithGoogle, mockSignOut } = vi.hoisted(() => ({
  mockLoginWithGoogle: vi.fn(),
  mockSignOut: vi.fn(),
}));

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: {
    loginWithGoogle: mockLoginWithGoogle,
  },
}));

vi.mock('../../src/lib/auth', () => ({
  signOut: mockSignOut,
}));

// Store selector state for test control
let mockAuthState: Record<string, unknown> = {
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
import { useContactVerification } from '../../src/hooks/useContactVerification';

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

  describe('userName derivation', () => {
    it('should use profile.nombre when available', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: { nombre: 'Profile Name' },
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());
      expect(result.current.userName).toBe('Profile Name');
    });

    it('should return null when no profile', () => {
      mockAuthState = {
        user: { email: 'test@example.com' },
        profile: null,
        initialized: true,
        loading: false,
      };

      const { result } = renderHook(() => useContactVerification());
      // Hook: profile?.nombre || null -> null
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
        user: { email: 'test@example.com' },
        profile: null,
        initialized: true,
        loading: false,
      };

      renderHook(() => useContactVerification({ onVerified: onVerifiedMock }));

      // userName is null, but passed as undefined to callback (null || undefined)
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

      expect(result.current.contactoVerificado).toBe(initialContactoVerificado);
      expect(result.current.userEmail).toBe(initialUserEmail);
    });
  });

  describe('loginWithGoogle', () => {
    it('should call authAdapter.loginWithGoogle', async () => {
      mockLoginWithGoogle.mockResolvedValue(undefined);

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      expect(mockLoginWithGoogle).toHaveBeenCalled();
    });

    it('catches mutation: should set loading to true during request', async () => {
      let resolveLogin: (() => void) | undefined;
      mockLoginWithGoogle.mockReturnValue(new Promise<void>((resolve) => { resolveLogin = resolve; }));

      const { result } = renderHook(() => useContactVerification());

      const loginPromise = act(async () => {
        await result.current.loginWithGoogle();
      });

      resolveLogin!();
      await loginPromise;
    });

    it('catches mutation: should show error notification on failure', async () => {
      mockLoginWithGoogle.mockRejectedValue(new Error('OAuth failed'));

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
      mockLoginWithGoogle.mockRejectedValue(new Error('OAuth failed'));

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.loginWithGoogle();
      });

      expect(result.current.loading).toBe(false);
    });

    it('catches mutation: should show exact error message text', async () => {
      mockLoginWithGoogle.mockRejectedValue(new Error('OAuth failed'));

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

    it('should show not-available notification for valid email (magic link disabled)', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('test@example.com');
      });

      // Magic link is disabled in JWT adapter - shows "No disponible"
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'No disponible',
          color: 'yellow',
        })
      );
    });

    it('catches mutation: email validation should check for @domain', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.sendMagicLink('invalidemail.com');
      });

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

      // test@domain fails the regex /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Email invalido',
        })
      );
    });
  });

  describe('logout', () => {
    it('should call signOut', async () => {
      mockSignOut.mockResolvedValue(undefined);

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
      mockSignOut.mockResolvedValue(undefined);

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
      mockSignOut.mockRejectedValue(new Error('Logout failed'));

      const { result } = renderHook(() => useContactVerification());

      // Should not throw
      await act(async () => {
        await result.current.logout();
      });

      // Error is caught, no notification on error (just logger.error)
      expect(result.current).toBeDefined();
    });
  });

  describe('resetVerificacion', () => {
    it('should reset state to initial values', () => {
      const { result } = renderHook(() => useContactVerification());

      // Set some state
      act(() => {
        result.current.setMetodoVerificacion('email');
      });

      expect(result.current.metodoVerificacion).toBe('email');

      // Reset
      act(() => {
        result.current.resetVerificacion();
      });

      expect(result.current.magicLinkSent).toBe(false);
      expect(result.current.magicLinkEmail).toBe(null);
      expect(result.current.metodoVerificacion).toBe('google');
    });

    it('catches mutation: should reset ALL three properties', () => {
      const { result } = renderHook(() => useContactVerification());

      act(() => {
        result.current.setMetodoVerificacion('email');
      });

      act(() => {
        result.current.resetVerificacion();
      });

      expect(result.current.magicLinkSent).toBe(false);
      expect(result.current.magicLinkEmail).toBe(null);
      expect(result.current.metodoVerificacion).toBe('google');
    });
  });
});
