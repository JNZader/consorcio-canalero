/**
 * Unit tests for useContactVerification hook.
 *
 * Tests verification flow for email and WhatsApp methods.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useContactVerification } from '../../src/hooks/useContactVerification';

// Mock the API modules
vi.mock('../../src/lib/api', () => ({
  publicApi: {
    sendVerificationCode: vi.fn(),
    verifyCode: vi.fn(),
  },
  whatsappApi: {
    sendVerification: vi.fn(),
    checkStatus: vi.fn(),
  },
}));

// Mock Mantine notifications
vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

import { notifications } from '@mantine/notifications';
import { publicApi, whatsappApi } from '../../src/lib/api';

describe('useContactVerification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('initial state', () => {
    it('should return initial state correctly', () => {
      const { result } = renderHook(() => useContactVerification());

      expect(result.current.contactoVerificado).toBe(false);
      expect(result.current.metodoVerificacion).toBe('whatsapp');
      expect(result.current.enviandoCodigo).toBe(false);
      expect(result.current.verificandoCodigo).toBe(false);
      expect(result.current.codigoEnviado).toBe(false);
      expect(result.current.tiempoRestante).toBe(0);
      expect(result.current.whatsappVerificationId).toBeNull();
      expect(result.current.esperandoWhatsapp).toBe(false);
    });
  });

  describe('formatTiempo', () => {
    it('should format time correctly', () => {
      const { result } = renderHook(() => useContactVerification());

      expect(result.current.formatTiempo(0)).toBe('0:00');
      expect(result.current.formatTiempo(30)).toBe('0:30');
      expect(result.current.formatTiempo(60)).toBe('1:00');
      expect(result.current.formatTiempo(90)).toBe('1:30');
      expect(result.current.formatTiempo(300)).toBe('5:00');
      expect(result.current.formatTiempo(125)).toBe('2:05');
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

    it('should reset related states when changing method', () => {
      const { result } = renderHook(() => useContactVerification());

      // Simulate some state being set
      act(() => {
        result.current.setMetodoVerificacion('email');
      });

      act(() => {
        result.current.setMetodoVerificacion('whatsapp');
      });

      expect(result.current.codigoEnviado).toBe(false);
      expect(result.current.esperandoWhatsapp).toBe(false);
      expect(result.current.whatsappVerificationId).toBeNull();
      expect(result.current.tiempoRestante).toBe(0);
    });
  });

  describe('enviarCodigoEmail', () => {
    it('should show error for invalid email', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarCodigoEmail('invalid-email');
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
        await result.current.enviarCodigoEmail('');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Email invalido',
          color: 'red',
        })
      );
    });

    it('should send verification code for valid email', async () => {
      vi.mocked(publicApi.sendVerificationCode).mockResolvedValue({
        message: 'Code sent',
        expires_in: 300,
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarCodigoEmail('test@example.com');
      });

      expect(publicApi.sendVerificationCode).toHaveBeenCalledWith('test@example.com');
      expect(result.current.codigoEnviado).toBe(true);
      expect(result.current.tiempoRestante).toBe(300);
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Codigo enviado',
          color: 'green',
        })
      );
    });

    it('should handle API error', async () => {
      vi.mocked(publicApi.sendVerificationCode).mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarCodigoEmail('test@example.com');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error',
          color: 'red',
        })
      );
      expect(result.current.codigoEnviado).toBe(false);
    });

    it('should respect external validation function', async () => {
      const { result } = renderHook(() => useContactVerification());
      const validateEmail = vi.fn().mockReturnValue(false);

      await act(async () => {
        await result.current.enviarCodigoEmail('test@example.com', validateEmail);
      });

      expect(validateEmail).toHaveBeenCalled();
      expect(publicApi.sendVerificationCode).not.toHaveBeenCalled();
    });
  });

  describe('verificarCodigo', () => {
    it('should not verify if code is less than 6 digits', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.verificarCodigo('test@example.com', '12345');
      });

      expect(publicApi.verifyCode).not.toHaveBeenCalled();
    });

    it('should verify valid code', async () => {
      vi.mocked(publicApi.verifyCode).mockResolvedValue({ verified: true, token: 'test-token' });

      const onVerified = vi.fn();
      const { result } = renderHook(() => useContactVerification({ onVerified }));

      await act(async () => {
        await result.current.verificarCodigo('test@example.com', '123456');
      });

      expect(publicApi.verifyCode).toHaveBeenCalledWith('test@example.com', '123456');
      expect(result.current.contactoVerificado).toBe(true);
      expect(onVerified).toHaveBeenCalled();
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Email verificado',
          color: 'green',
        })
      );
    });

    it('should handle invalid code', async () => {
      vi.mocked(publicApi.verifyCode).mockRejectedValue(new Error('Invalid code'));

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.verificarCodigo('test@example.com', '000000');
      });

      expect(result.current.contactoVerificado).toBe(false);
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Codigo invalido',
          color: 'red',
        })
      );
    });
  });

  describe('enviarVerificacionWhatsapp', () => {
    it('should show error for invalid phone number', async () => {
      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarVerificacionWhatsapp('123');
      });

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Numero invalido',
          color: 'red',
        })
      );
    });

    it('should send WhatsApp verification for valid phone', async () => {
      vi.mocked(whatsappApi.sendVerification).mockResolvedValue({
        verification_id: 'test-id-123',
        expires_in: 300,
        message: 'Verification sent',
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarVerificacionWhatsapp('5493512345678');
      });

      expect(whatsappApi.sendVerification).toHaveBeenCalled();
      expect(result.current.whatsappVerificationId).toBe('test-id-123');
      expect(result.current.esperandoWhatsapp).toBe(true);
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Verificacion enviada',
          color: 'green',
        })
      );
    });

    it('should use provided report data', async () => {
      vi.mocked(whatsappApi.sendVerification).mockResolvedValue({
        verification_id: 'test-id-456',
        expires_in: 300,
        message: 'Verification sent',
      });

      const reportData = {
        tipo: 'alcantarilla_tapada',
        descripcion: 'Test description',
        latitud: -32.5,
        longitud: -62.5,
      };

      const { result } = renderHook(() => useContactVerification({ reportData }));

      await act(async () => {
        await result.current.enviarVerificacionWhatsapp('5493512345678');
      });

      expect(whatsappApi.sendVerification).toHaveBeenCalledWith({
        phone: '5493512345678',
        report_data: reportData,
      });
    });
  });

  describe('cancelarVerificacionWhatsapp', () => {
    it('should cancel pending WhatsApp verification', async () => {
      vi.mocked(whatsappApi.sendVerification).mockResolvedValue({
        verification_id: 'test-id-789',
        expires_in: 300,
        message: 'Verification sent',
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarVerificacionWhatsapp('5493512345678');
      });

      expect(result.current.esperandoWhatsapp).toBe(true);

      act(() => {
        result.current.cancelarVerificacionWhatsapp();
      });

      expect(result.current.esperandoWhatsapp).toBe(false);
      expect(result.current.whatsappVerificationId).toBeNull();
    });
  });

  describe('resetVerificacion', () => {
    it('should reset all state to initial values', async () => {
      vi.mocked(publicApi.sendVerificationCode).mockResolvedValue({
        message: 'Code sent',
        expires_in: 300,
      });

      const { result } = renderHook(() => useContactVerification());

      // Set some state
      await act(async () => {
        result.current.setMetodoVerificacion('email');
        await result.current.enviarCodigoEmail('test@example.com');
      });

      expect(result.current.codigoEnviado).toBe(true);

      // Reset
      act(() => {
        result.current.resetVerificacion();
      });

      expect(result.current.contactoVerificado).toBe(false);
      expect(result.current.metodoVerificacion).toBe('whatsapp');
      expect(result.current.enviandoCodigo).toBe(false);
      expect(result.current.verificandoCodigo).toBe(false);
      expect(result.current.codigoEnviado).toBe(false);
      expect(result.current.tiempoRestante).toBe(0);
      expect(result.current.whatsappVerificationId).toBeNull();
      expect(result.current.esperandoWhatsapp).toBe(false);
    });
  });

  describe('setContactoVerificado', () => {
    it('should allow manual setting of verification status', () => {
      const { result } = renderHook(() => useContactVerification());

      act(() => {
        result.current.setContactoVerificado(true);
      });

      expect(result.current.contactoVerificado).toBe(true);

      act(() => {
        result.current.setContactoVerificado(false);
      });

      expect(result.current.contactoVerificado).toBe(false);
    });
  });

  describe('timer functionality', () => {
    it('should decrement timer over time', async () => {
      vi.mocked(publicApi.sendVerificationCode).mockResolvedValue({
        message: 'Code sent',
        expires_in: 60,
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarCodigoEmail('test@example.com');
      });

      expect(result.current.tiempoRestante).toBe(60);

      // Advance time by 10 seconds
      act(() => {
        vi.advanceTimersByTime(10000);
      });

      expect(result.current.tiempoRestante).toBe(50);
    });

    it('should stop at zero', async () => {
      vi.mocked(publicApi.sendVerificationCode).mockResolvedValue({
        message: 'Code sent',
        expires_in: 3,
      });

      const { result } = renderHook(() => useContactVerification());

      await act(async () => {
        await result.current.enviarCodigoEmail('test@example.com');
      });

      // Advance time past expiration
      act(() => {
        vi.advanceTimersByTime(5000);
      });

      expect(result.current.tiempoRestante).toBe(0);
    });
  });
});
