import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  registerExceptionReporter,
  registerLogErrorSink,
  reportException,
  resetErrorReportingForTests,
} from '../../src/lib/errorReporting';

describe('errorReporting bus', () => {
  afterEach(() => {
    resetErrorReportingForTests();
  });

  it('buffers early exceptions and flushes them upon sink registration', () => {
    const err1 = new Error('early-1');
    const err2 = new Error('early-2');

    reportException(err1, { boundary: 'RouterErrorFallback' });
    reportException(err2, { boundary: 'ErrorBoundary' });

    const sentrySink = vi.fn();
    const logtailSink = vi.fn();

    registerExceptionReporter(sentrySink);
    registerLogErrorSink(logtailSink);

    expect(sentrySink).toHaveBeenCalledTimes(2);
    expect(sentrySink).toHaveBeenNthCalledWith(1, err1, { boundary: 'RouterErrorFallback' });
    expect(sentrySink).toHaveBeenNthCalledWith(2, err2, { boundary: 'ErrorBoundary' });

    expect(logtailSink).toHaveBeenCalledTimes(2);
    expect(logtailSink).toHaveBeenNthCalledWith(1, err1, { boundary: 'RouterErrorFallback' });
    expect(logtailSink).toHaveBeenNthCalledWith(2, err2, { boundary: 'ErrorBoundary' });
  });

  it('caps pending queue at 10 entries keeping the newest exceptions', () => {
    for (let i = 0; i < 15; i++) {
      reportException(new Error(`err-${i}`), { index: i });
    }

    const sentrySink = vi.fn();
    registerExceptionReporter(sentrySink);

    expect(sentrySink).toHaveBeenCalledTimes(10);
    expect((sentrySink.mock.calls[0][0] as Error).message).toBe('err-5');
    expect((sentrySink.mock.calls[9][0] as Error).message).toBe('err-14');
  });

  it('dispatches immediately once sinks are registered and isolates sink failures', () => {
    const throwingSink = vi.fn(() => {
      throw new Error('sink-failure');
    });
    const healthySink = vi.fn();

    registerExceptionReporter(throwingSink);
    registerLogErrorSink(healthySink);

    const boom = new Error('boom');
    expect(() => reportException(boom, { route: '/mapa' })).not.toThrow();
    expect(throwingSink).toHaveBeenCalledWith(boom, { route: '/mapa' });
    expect(healthySink).toHaveBeenCalledWith(boom, { route: '/mapa' });
  });
});
