/**
 * Zero-dependency error reporting bus used by ErrorBoundary and RouterErrorFallback.
 *
 * Keeps Sentry/Logtail SDKs out of the initial entry chunk while buffering up to
 * {@link MAX_PENDING} early exceptions raised before lazy observability init.
 */

export type ErrorContext = Record<string, unknown>;
export type ExceptionSink = (error: unknown, context?: ErrorContext) => void;

const MAX_PENDING = 10;

let exceptionReporter: ExceptionSink | null = null;
let logErrorSink: ExceptionSink | null = null;

const pendingExceptions: Array<{ error: unknown; context?: ErrorContext }> = [];
const pendingLogErrors: Array<{ error: unknown; context?: ErrorContext }> = [];

function safeInvoke(sink: ExceptionSink, error: unknown, context?: ErrorContext): void {
  try {
    sink(error, context);
  } catch {
    // Error reporting must never cascade into a UI crash.
  }
}

function enqueue(
  queue: Array<{ error: unknown; context?: ErrorContext }>,
  error: unknown,
  context?: ErrorContext
): void {
  if (queue.length >= MAX_PENDING) {
    queue.shift();
  }
  queue.push({ error, context });
}

export function registerExceptionReporter(sink: ExceptionSink): void {
  exceptionReporter = sink;
  for (const item of pendingExceptions.splice(0)) {
    safeInvoke(sink, item.error, item.context);
  }
}

export function registerLogErrorSink(sink: ExceptionSink): void {
  logErrorSink = sink;
  for (const item of pendingLogErrors.splice(0)) {
    safeInvoke(sink, item.error, item.context);
  }
}

export function reportException(error: unknown, context?: ErrorContext): void {
  if (exceptionReporter) {
    safeInvoke(exceptionReporter, error, context);
  } else {
    enqueue(pendingExceptions, error, context);
  }

  if (logErrorSink) {
    safeInvoke(logErrorSink, error, context);
  } else {
    enqueue(pendingLogErrors, error, context);
  }
}

export function resetErrorReportingForTests(): void {
  exceptionReporter = null;
  logErrorSink = null;
  pendingExceptions.length = 0;
  pendingLogErrors.length = 0;
}
