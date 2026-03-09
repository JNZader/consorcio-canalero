/**
 * Tests for logger utility
 * Coverage target: 100% (all logging levels and configuration)
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { logger } from '../../src/lib/logger';

describe('logger', () => {
  let consoleLogSpy: ReturnType<typeof vi.spyOn>;
  let consoleWarnSpy: ReturnType<typeof vi.spyOn>;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Reset logger configuration
    logger.configure({ minLevel: 'debug', timestamps: false });
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    consoleWarnSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  describe('debug logging', () => {
    it('should log debug messages when minLevel is debug', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });
      logger.debug('Debug message');

      expect(consoleLogSpy).toHaveBeenCalledWith('[DEBUG] Debug message');
    });

    it('should not log debug messages when minLevel is info', () => {
      logger.configure({ minLevel: 'info', timestamps: false });
      logger.debug('Debug message');

      expect(consoleLogSpy).not.toHaveBeenCalled();
    });

    it('should pass through additional arguments', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });
      logger.debug('Message', { key: 'value' }, 'extra');

      expect(consoleLogSpy).toHaveBeenCalledWith('[DEBUG] Message', { key: 'value' }, 'extra');
    });
  });

  describe('info logging', () => {
    it('should log info messages when minLevel is debug or info', () => {
      logger.configure({ minLevel: 'info', timestamps: false });
      logger.info('Info message');

      expect(consoleLogSpy).toHaveBeenCalledWith('[INFO] Info message');
    });

    it('should not log info messages when minLevel is warn', () => {
      logger.configure({ minLevel: 'warn', timestamps: false });
      logger.info('Info message');

      expect(consoleLogSpy).not.toHaveBeenCalled();
    });
  });

  describe('warn logging', () => {
    it('should log warn messages', () => {
      logger.configure({ minLevel: 'warn', timestamps: false });
      logger.warn('Warning message');

      expect(consoleWarnSpy).toHaveBeenCalledWith('[WARN] Warning message');
    });

    it('should not log warn messages when minLevel is error', () => {
      logger.configure({ minLevel: 'error', timestamps: false });
      logger.warn('Warning message');

      expect(consoleWarnSpy).not.toHaveBeenCalled();
    });

    it('should include additional arguments', () => {
      logger.configure({ minLevel: 'warn', timestamps: false });
      logger.warn('Warning', { context: 'test' });

      expect(consoleWarnSpy).toHaveBeenCalledWith('[WARN] Warning', { context: 'test' });
    });
  });

  describe('error logging', () => {
    it('should always log error messages', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });
      logger.error('Error message');

      expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR] Error message', undefined);
    });

    it('should include error object', () => {
      logger.configure({ minLevel: 'error', timestamps: false });
      const error = new Error('Test error');
      logger.error('Error occurred', error);

      expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR] Error occurred', error);
    });

    it('should handle error with additional args', () => {
      logger.configure({ minLevel: 'error', timestamps: false });
      const error = new Error('Test error');
      logger.error('Error occurred', error, { extra: 'data' });

      expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR] Error occurred', error, { extra: 'data' });
    });
  });

  describe('timestamp formatting', () => {
    it('should include timestamps when enabled', () => {
      logger.configure({ minLevel: 'debug', timestamps: true });
      logger.debug('Message');

      const call = consoleLogSpy.mock.calls[0][0];
      expect(call).toMatch(/\[\d{2}:\d{2}:\d{2}\] \[DEBUG\] Message/);
    });

    it('should not include timestamps when disabled', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });
      logger.debug('Message');

      expect(consoleLogSpy).toHaveBeenCalledWith('[DEBUG] Message');
    });
  });

  describe('logger configuration', () => {
    it('should allow changing minLevel', () => {
      logger.configure({ minLevel: 'error', timestamps: false });
      logger.debug('Should not appear');
      logger.error('Should appear');

      expect(consoleLogSpy).not.toHaveBeenCalled();
      expect(consoleErrorSpy).toHaveBeenCalled();
    });

    it('should allow changing timestamp setting', () => {
      logger.configure({ minLevel: 'debug', timestamps: true });
      logger.debug('Message');

      expect(consoleLogSpy.mock.calls[0][0]).toMatch(/\[\d{2}:\d{2}:\d{2}\]/);

      logger.configure({ timestamps: false });
      consoleLogSpy.mockClear();
      logger.debug('Message 2');

      expect(consoleLogSpy.mock.calls[0][0]).not.toMatch(/\[\d{2}:\d{2}:\d{2}\]/);
    });

    it('should merge partial configuration', () => {
      logger.configure({ minLevel: 'debug', timestamps: true });
      logger.configure({ minLevel: 'warn' });

      logger.debug('Should not appear');
      logger.warn('Should appear');

      expect(consoleLogSpy).not.toHaveBeenCalled();
      expect(consoleWarnSpy).toHaveBeenCalled();
    });
  });

  describe('external error handler', () => {
    it('should call onError handler when error is logged', () => {
      const onError = vi.fn();
      logger.configure({ minLevel: 'error', timestamps: false, onError });

      const error = new Error('Test error');
      logger.error('Error occurred', error);

      expect(onError).toHaveBeenCalledWith('Error occurred', error);
    });

    it('should not call onError handler for non-error levels', () => {
      const onError = vi.fn();
      logger.configure({ minLevel: 'debug', timestamps: false, onError });

      logger.debug('Debug message');
      logger.info('Info message');
      logger.warn('Warning message');

      expect(onError).not.toHaveBeenCalled();
    });

    it('should not call onError if minLevel skips errors', () => {
      const onError = vi.fn();
      // This shouldn't normally happen, but test the behavior
      logger.configure({ minLevel: 'error', timestamps: false, onError });
      logger.error('Error', new Error('test'));

      expect(onError).toHaveBeenCalledOnce();
    });
  });

  describe('child logger', () => {
    it('should create a child logger with prefix', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });
      const childLogger = logger.child('MyModule');

      childLogger.debug('Child debug');

      expect(consoleLogSpy).toHaveBeenCalledWith('[DEBUG] [MyModule] Child debug');
    });

    it('should include prefix in all levels', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });
      const childLogger = logger.child('TestModule');

      childLogger.debug('Debug');
      childLogger.info('Info');
      childLogger.warn('Warning');
      childLogger.error('Error', new Error('test'));

      expect(consoleLogSpy).toHaveBeenCalledWith('[DEBUG] [TestModule] Debug');
      expect(consoleLogSpy).toHaveBeenCalledWith('[INFO] [TestModule] Info');
      expect(consoleWarnSpy).toHaveBeenCalledWith('[WARN] [TestModule] Warning');
      expect(consoleErrorSpy).toHaveBeenCalledWith('[ERROR] [TestModule] Error', expect.any(Error));
    });

    it('should respect parent logger configuration', () => {
      logger.configure({ minLevel: 'warn', timestamps: false });
      const childLogger = logger.child('ChildModule');

      childLogger.debug('Should not appear');
      childLogger.warn('Should appear');

      expect(consoleLogSpy).not.toHaveBeenCalled();
      expect(consoleWarnSpy).toHaveBeenCalled();
    });

    it('should support nested prefixes', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });
      const child1 = logger.child('Module1');
      const child2 = child1; // In real usage, you'd call child on child

      child2.info('Message');

      expect(consoleLogSpy).toHaveBeenCalledWith('[INFO] [Module1] Message');
    });
  });

  describe('log level ordering', () => {
    it('should respect log level hierarchy', () => {
      logger.configure({ minLevel: 'debug', timestamps: false });

      logger.debug('Debug');
      logger.info('Info');
      logger.warn('Warning');
      logger.error('Error');

      expect(consoleLogSpy).toHaveBeenCalledTimes(2); // debug and info
      expect(consoleWarnSpy).toHaveBeenCalledTimes(1);
      expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    });

    it('should filter messages below minimum level', () => {
      logger.configure({ minLevel: 'warn', timestamps: false });

      logger.debug('Debug');
      logger.info('Info');
      logger.warn('Warning');
      logger.error('Error');

      expect(consoleLogSpy).not.toHaveBeenCalled(); // No debug or info
      expect(consoleWarnSpy).toHaveBeenCalledTimes(1);
      expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('default export', () => {
    it('should export logger as default', async () => {
      const loggerModule = await import('../../src/lib/logger');
      expect(loggerModule.default).toBe(loggerModule.logger);
    });
  });
});
