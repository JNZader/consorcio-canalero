import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  sentryInitMock,
  sentryCaptureExceptionMock,
  sentryAddBreadcrumbMock,
  logtailErrorMock,
  logtailConstructorSpy,
} = vi.hoisted(() => ({
  sentryInitMock: vi.fn(),
  sentryCaptureExceptionMock: vi.fn(),
  sentryAddBreadcrumbMock: vi.fn(),
  logtailErrorMock: vi.fn(),
  logtailConstructorSpy: vi.fn(),
}));

vi.mock('@sentry/react', () => ({
  init: sentryInitMock,
  captureException: sentryCaptureExceptionMock,
  addBreadcrumb: sentryAddBreadcrumbMock,
  ErrorBoundary: ({ children }: { children: unknown }) => children,
}));

vi.mock('@logtail/browser', () => ({
  Logtail: class MockLogtail {
    constructor(token: string, options?: unknown) {
      logtailConstructorSpy(token, options);
    }
    info = vi.fn();
    warn = vi.fn();
    error = logtailErrorMock;
  },
}));

import { reportException, resetErrorReportingForTests } from '../../src/lib/errorReporting';
import { logger } from '../../src/lib/logger';
import { initLogtail, logError, resetLogtailForTests } from '../../src/lib/logtail';
import {
  captureException,
  initSentry,
  resetSentryForTests,
  resolveTracesSampleRate,
} from '../../src/lib/sentry';

describe('observability wiring (Sentry RUM + Logtail)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
    resetErrorReportingForTests();
    resetSentryForTests();
    resetLogtailForTests();
    logger.configure({ minLevel: 'error', timestamps: false, onError: undefined });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    resetErrorReportingForTests();
    resetSentryForTests();
    resetLogtailForTests();
  });

  it('resolveTracesSampleRate defaults to 0.1 and clamps valid env values', () => {
    expect(resolveTracesSampleRate(undefined)).toBe(0.1);
    expect(resolveTracesSampleRate('')).toBe(0.1);
    expect(resolveTracesSampleRate('0.25')).toBe(0.25);
    expect(resolveTracesSampleRate('1.5')).toBe(1);
    expect(resolveTracesSampleRate('-0.5')).toBe(0);
    expect(resolveTracesSampleRate('not-a-number')).toBe(0);
  });

  it('initSentry is a no-op without DSN and captureException stays inert', () => {
    vi.stubEnv('VITE_SENTRY_DSN', '');
    initSentry();
    captureException(new Error('ignored'));

    expect(sentryInitMock).not.toHaveBeenCalled();
    expect(sentryCaptureExceptionMock).not.toHaveBeenCalled();
  });

  it('initSentry uses 0.1 default tracesSampleRate, registers reporter, flushes early errors, and starts Web Vitals RUM', () => {
    const observedTypes: string[] = [];
    const callbacks = new Map<string, (list: { getEntries: () => unknown[] }) => void>();

    class MockPerformanceObserver {
      private cb: (list: { getEntries: () => unknown[] }) => void;
      constructor(cb: (list: { getEntries: () => unknown[] }) => void) {
        this.cb = cb;
      }
      observe({ type }: { type: string }) {
        observedTypes.push(type);
        callbacks.set(type, this.cb);
        if (type === 'event') {
          throw new Error('unsupported entryType');
        }
      }
    }

    vi.stubGlobal('PerformanceObserver', MockPerformanceObserver);
    vi.stubEnv('VITE_SENTRY_DSN', 'https://key@o1.ingest.us.sentry.io/1');
    vi.stubEnv('VITE_SENTRY_TRACES_SAMPLE_RATE', '');

    const earlyErr = new Error('pre-idle-crash');
    reportException(earlyErr, { boundary: 'RouterErrorFallback' });

    initSentry();

    expect(sentryInitMock).toHaveBeenCalledWith(
      expect.objectContaining({
        dsn: 'https://key@o1.ingest.us.sentry.io/1',
        tracesSampleRate: 0.1,
      })
    );
    expect(sentryCaptureExceptionMock).toHaveBeenCalledWith(earlyErr, {
      extra: { boundary: 'RouterErrorFallback' },
    });
    expect(observedTypes).toEqual(
      expect.arrayContaining(['largest-contentful-paint', 'layout-shift', 'first-input'])
    );

    callbacks.get('largest-contentful-paint')?.({
      getEntries: () => [{ startTime: 412.5 }],
    });
    callbacks.get('layout-shift')?.({
      getEntries: () => [{ hadRecentInput: false, value: 0.04 }],
    });

    expect(sentryAddBreadcrumbMock).toHaveBeenCalledWith(
      expect.objectContaining({
        category: 'web-vital',
        data: { metric: 'LCP', value: 412.5 },
      })
    );
    expect(sentryAddBreadcrumbMock).toHaveBeenCalledWith(
      expect.objectContaining({
        category: 'web-vital',
        data: { metric: 'CLS', value: 0.04 },
      })
    );
  });

  it('initLogtail wires logger.error and reportException through sensitive scrubbing', () => {
    vi.stubEnv('VITE_LOGTAIL_TOKEN', 'source-token-123');
    vi.stubEnv('VITE_LOGTAIL_ENDPOINT', 'https://eu1.logs.betterstack.com');
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    reportException(new Error('boot failed for user@example.com'), {
      auth: 'Bearer secret.jwt.token',
    });

    initLogtail();

    expect(logtailConstructorSpy).toHaveBeenCalledWith('source-token-123', {
      endpoint: 'https://eu1.logs.betterstack.com',
    });

    // Flushed buffered exception had PII/JWT scrubbed.
    expect(logtailErrorMock).toHaveBeenCalledTimes(1);
    expect(logtailErrorMock.mock.calls[0][0]).toContain('[email]');
    expect(logtailErrorMock.mock.calls[0][0]).toContain('Bearer [REDACTED]');
    expect(logtailErrorMock.mock.calls[0][0]).not.toContain('user@example.com');
    expect(logtailErrorMock.mock.calls[0][0]).not.toContain('secret.jwt.token');

    // Runtime logger.error now forwards to Logtail via logger.configure({ onError }).
    logger.error('API failure for operator@consorcio.ar', new Error('500 error'));
    expect(logtailErrorMock).toHaveBeenCalledTimes(2);
    expect(logtailErrorMock.mock.calls[1][0]).toContain('[email]');
    expect(logtailErrorMock.mock.calls[1][0]).not.toContain('operator@consorcio.ar');

    logError('Manual error');
    expect(logtailErrorMock).toHaveBeenCalledTimes(3);
    consoleErrorSpy.mockRestore();
  });
});
