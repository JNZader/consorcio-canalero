/**
 * Unit tests for useContactVerification hook.
 *
 * Tests verification flow for Google OAuth and Magic Link methods.
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

// Mock auth store
vi.mock('../../src/stores/authStore', () => ({
  useAuthStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      user: null,
      profile: null,
      initialized: true,
      loading: false,
    }),
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

    it('should show error notification on failure', async () => {
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
      expect(result.current.magicLinkEmail).toBeNull();
      expect(result.current.metodoVerificacion).toBe('google');
    });
  });
});
