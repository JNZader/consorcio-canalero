/**
 * Centralized logger utility for the application.
 *
 * In development: logs all messages to console
 * In production: only logs errors (and can be configured to send to external service)
 *
 * Usage:
 * ```ts
 * import { logger } from '../lib/logger';
 *
 * logger.debug('Debug info');           // Only in development
 * logger.info('Info message');          // Only in development
 * logger.warn('Warning', { data });     // Only in development
 * logger.error('Error occurred', err);  // Always logged
 * ```
 */

const isDev = import.meta.env?.DEV ?? process.env.NODE_ENV === 'development';

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LoggerConfig {
  /** Minimum log level to output */
  minLevel: LogLevel;
  /** Whether to include timestamps */
  timestamps: boolean;
  /** Optional external error reporting function */
  onError?: (message: string, error?: unknown) => void;
}

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const defaultConfig: LoggerConfig = {
  minLevel: isDev ? 'debug' : 'error',
  timestamps: isDev,
};

let config: LoggerConfig = { ...defaultConfig };

function shouldLog(level: LogLevel): boolean {
  return LOG_LEVELS[level] >= LOG_LEVELS[config.minLevel];
}

function formatMessage(level: LogLevel, message: string): string {
  if (config.timestamps) {
    const time = new Date().toISOString().split('T')[1].slice(0, 8);
    return `[${time}] [${level.toUpperCase()}] ${message}`;
  }
  return `[${level.toUpperCase()}] ${message}`;
}

export const logger = {
  /**
   * Configure the logger.
   */
  configure(newConfig: Partial<LoggerConfig>) {
    config = { ...config, ...newConfig };
  },

  /**
   * Debug level logging - only in development.
   */
  debug(message: string, ...args: unknown[]) {
    if (shouldLog('debug')) {
      // biome-ignore lint/suspicious/noConsoleLog: logger utility
      console.log(formatMessage('debug', message), ...args);
    }
  },

  /**
   * Info level logging - only in development.
   */
  info(message: string, ...args: unknown[]) {
    if (shouldLog('info')) {
      // biome-ignore lint/suspicious/noConsoleLog: logger utility
      console.log(formatMessage('info', message), ...args);
    }
  },

  /**
   * Warning level logging - only in development.
   */
  warn(message: string, ...args: unknown[]) {
    if (shouldLog('warn')) {
      console.warn(formatMessage('warn', message), ...args);
    }
  },

  /**
   * Error level logging - always logged.
   * Can optionally send to external error tracking service.
   */
  error(message: string, error?: unknown, ...args: unknown[]) {
    if (shouldLog('error')) {
      console.error(formatMessage('error', message), error, ...args);

      // Call external error handler if configured
      if (config.onError) {
        config.onError(message, error);
      }
    }
  },

  /**
   * Create a child logger with a prefix.
   */
  child(prefix: string) {
    return {
      debug: (message: string, ...args: unknown[]) => logger.debug(`[${prefix}] ${message}`, ...args),
      info: (message: string, ...args: unknown[]) => logger.info(`[${prefix}] ${message}`, ...args),
      warn: (message: string, ...args: unknown[]) => logger.warn(`[${prefix}] ${message}`, ...args),
      error: (message: string, error?: unknown, ...args: unknown[]) =>
        logger.error(`[${prefix}] ${message}`, error, ...args),
    };
  },
};

export default logger;
