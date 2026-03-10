/**
 * Tests for notification helpers
 * Coverage target: 100%
 */
// @ts-nocheck


import { describe, it, expect, beforeEach, vi } from 'vitest';
import * as notificationModule from '../../src/lib/notifications';
import { notifications } from '@mantine/notifications';

// Mock mantine notifications
vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

describe('notifications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('showSuccess', () => {
    it('should call notifications.show with success color', () => {
      notificationModule.showSuccess('Success', 'Operation completed');

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Success',
        message: 'Operation completed',
        color: 'green',
      });
    });

    it('should pass title and message correctly', () => {
      notificationModule.showSuccess('Guardado', 'Los datos se guardaron');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Guardado',
          message: 'Los datos se guardaron',
        })
      );
    });

    it('should always use green color', () => {
      notificationModule.showSuccess('Test', 'Message');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          color: 'green',
        })
      );
    });

    it('should handle empty strings', () => {
      notificationModule.showSuccess('', '');

      expect(notifications.show).toHaveBeenCalledWith({
        title: '',
        message: '',
        color: 'green',
      });
    });

    it('should handle long messages', () => {
      const longMessage = 'A'.repeat(1000);
      notificationModule.showSuccess('Title', longMessage);

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: longMessage,
        })
      );
    });
  });

  describe('showError', () => {
    it('should call notifications.show with error color', () => {
      notificationModule.showError('Error', 'Something went wrong');

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Error',
        message: 'Something went wrong',
        color: 'red',
      });
    });

    it('should always use red color', () => {
      notificationModule.showError('Error Title', 'Error message');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          color: 'red',
        })
      );
    });

    it('should pass title and message correctly', () => {
      notificationModule.showError('Error de validación', 'El campo es requerido');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error de validación',
          message: 'El campo es requerido',
        })
      );
    });
  });

  describe('showWarning', () => {
    it('should call notifications.show with warning color', () => {
      notificationModule.showWarning('Warning', 'Please check');

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Warning',
        message: 'Please check',
        color: 'orange',
      });
    });

    it('should always use orange color', () => {
      notificationModule.showWarning('Atención', 'Acción requerida');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          color: 'orange',
        })
      );
    });
  });

  describe('showInfo', () => {
    it('should call notifications.show with info color', () => {
      notificationModule.showInfo('Info', 'Process completed');

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Info',
        message: 'Process completed',
        color: 'blue',
      });
    });

    it('should always use blue color', () => {
      notificationModule.showInfo('Información', 'Proceso completo');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          color: 'blue',
        })
      );
    });
  });

  describe('showNotification', () => {
    it('should call notifications.show with custom color', () => {
      notificationModule.showNotification('Title', 'Message', 'yellow');

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Title',
        message: 'Message',
        color: 'yellow',
      });
    });

    it('should support all color options', () => {
      const colors: Array<'green' | 'red' | 'orange' | 'blue' | 'yellow' | 'gray'> = [
        'green',
        'red',
        'orange',
        'blue',
        'yellow',
        'gray',
      ];

      colors.forEach((color) => {
        vi.clearAllMocks();
        notificationModule.showNotification('Title', 'Message', color);

        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            color,
          })
        );
      });
    });

    it('should pass all parameters correctly', () => {
      notificationModule.showNotification('Custom Title', 'Custom Message', 'gray');

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Custom Title',
        message: 'Custom Message',
        color: 'gray',
      });
    });
  });

  describe('showErrorFromException', () => {
    it('should extract message from Error object', () => {
      const error = new Error('Test error message');
      notificationModule.showErrorFromException('Error Title', error);

      expect(notifications.show).toHaveBeenCalledWith({
        title: 'Error Title',
        message: 'Test error message',
        color: 'red',
      });
    });

    it('should use fallback for non-Error objects', () => {
      notificationModule.showErrorFromException('Error', 'String error');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Error desconocido',
        })
      );
    });

    it('should use fallback for undefined error', () => {
      notificationModule.showErrorFromException('Error', undefined);

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Error desconocido',
        })
      );
    });

    it('should use custom fallback when provided', () => {
      notificationModule.showErrorFromException('Error', 'unknown', 'Custom fallback');

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Custom fallback',
        })
      );
    });

    it('should always use red color', () => {
      const error = new Error('Any error');
      notificationModule.showErrorFromException('Title', error);

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          color: 'red',
        })
      );
    });

    it('should extract message from Error with special characters', () => {
      const error = new Error('Error with special chars: @#$%^&*()');
      notificationModule.showErrorFromException('Title', error);

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Error with special chars: @#$%^&*()',
        })
      );
    });

    it('should handle Error with empty message', () => {
      const error = new Error('');
      notificationModule.showErrorFromException('Title', error);

      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          message: '',
        })
      );
    });
  });

  describe('notification exports', () => {
    it('should export all notification functions', () => {
      expect(typeof notificationModule.showSuccess).toBe('function');
      expect(typeof notificationModule.showError).toBe('function');
      expect(typeof notificationModule.showWarning).toBe('function');
      expect(typeof notificationModule.showInfo).toBe('function');
      expect(typeof notificationModule.showNotification).toBe('function');
      expect(typeof notificationModule.showErrorFromException).toBe('function');
    });
  });
});
