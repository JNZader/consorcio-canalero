/**
 * Sentry init wrapper — fires only when ``VITE_SENTRY_DSN`` is set.
 *
 * Off by default so dev and forks pay zero overhead and no
 * cross-origin request to the DSN host (<org>.ingest.us.sentry.io) on every
 * page load. That host pattern is allow-listed in public/_headers.
 * The DSN comes in via Vite's ``import.meta.env`` at build time —
 * Cloudflare Pages sets it as a project variable.
 *
 * Tuning:
 *   - ``VITE_SENTRY_ENVIRONMENT`` (defaults to import.meta.env.MODE) —
 *     "production" vs "preview" vs "development".
 *   - ``VITE_SENTRY_TRACES_SAMPLE_RATE`` (defaults to 0 = no
 *     transaction sampling). Bump to 0.1 to capture 10 % of routes for
 *     performance traces; free tier covers it.
 *   - ``VITE_APP_VERSION`` — release tag for Sentry's "Releases" view.
 *     Set in CI to the short SHA so each deploy is a discrete release.
 */

import * as Sentry from '@sentry/react';

import { registerExceptionReporter } from './errorReporting';

const DEFAULT_TRACES_SAMPLE_RATE = 0.1;

let initialized = false;
let rumInitialized = false;

export function resolveTracesSampleRate(raw?: string): number {
  if (raw === undefined || raw.trim() === '') {
    return DEFAULT_TRACES_SAMPLE_RATE;
  }
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.min(1, Math.max(0, parsed));
}

export function captureException(error: unknown, context?: Record<string, unknown>): void {
  if (!initialized) {
    return;
  }
  Sentry.captureException(error, context ? { extra: context } : undefined);
}

function recordVitalBreadcrumb(metric: string, value: number): void {
  if (!Number.isFinite(value)) {
    return;
  }
  Sentry.addBreadcrumb?.({
    category: 'web-vital',
    level: 'info',
    message: metric,
    data: { metric, value: Math.round(value * 1000) / 1000 },
  });
}

function observeEntryType(
  entryType: string,
  handler: (entries: PerformanceEntryList) => void
): void {
  try {
    const observer = new PerformanceObserver((list) => {
      handler(list.getEntries());
    });
    observer.observe({ type: entryType, buffered: true });
  } catch {
    // Unsupported PerformanceObserver entryType in older runtimes or jsdom.
  }
}

function initWebVitalsRum(): void {
  if (rumInitialized || typeof PerformanceObserver === 'undefined') {
    return;
  }
  rumInitialized = true;

  let clsScore = 0;

  observeEntryType('largest-contentful-paint', (entries) => {
    const last = entries[entries.length - 1];
    if (last) {
      recordVitalBreadcrumb('LCP', last.startTime);
    }
  });

  observeEntryType('layout-shift', (entries) => {
    let updated = false;
    for (const entry of entries) {
      const shift = entry as PerformanceEntry & {
        hadRecentInput?: boolean;
        value?: number;
      };
      if (!shift.hadRecentInput && typeof shift.value === 'number' && shift.value > 0) {
        clsScore += shift.value;
        updated = true;
      }
    }
    if (updated) {
      recordVitalBreadcrumb('CLS', clsScore);
    }
  });

  observeEntryType('first-input', (entries) => {
    const first = entries[0] as (PerformanceEntry & { processingStart?: number }) | undefined;
    if (first && typeof first.processingStart === 'number') {
      recordVitalBreadcrumb('FID', Math.max(0, first.processingStart - first.startTime));
    }
  });

  observeEntryType('event', (entries) => {
    let maxDuration = 0;
    for (const entry of entries) {
      if (entry.duration > maxDuration) {
        maxDuration = entry.duration;
      }
    }
    if (maxDuration > 0) {
      recordVitalBreadcrumb('INP', maxDuration);
    }
  });
}

export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN ?? '';
  if (!dsn) {
    // Silent no-op in dev / unconfigured deploys.
    return;
  }
  const environment =
    import.meta.env.VITE_SENTRY_ENVIRONMENT ?? import.meta.env.MODE ?? 'development';
  const tracesSampleRate = resolveTracesSampleRate(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE);
  const release = import.meta.env.VITE_APP_VERSION ?? undefined;

  Sentry.init({
    dsn,
    environment,
    release,
    tracesSampleRate,
    // Sentry 11 dropped sendDefaultPii. Unset dataCollection collects
    // everything (IP, cookies, bodies). Keep the v10-restrictive baseline.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: {
        request: { deny: ['forwarded', '-ip', 'remote-', 'via', '-user'] },
        response: { deny: ['forwarded', '-ip', 'remote-', 'via', '-user'] },
      },
      httpBodies: [],
      urlQueryParams: { deny: ['forwarded', '-ip', 'remote-', 'via', '-user'] },
      genAI: { inputs: false, outputs: false },
      databaseQueryData: false,
      graphQL: { document: false, variables: false },
    },
    // Filter known noise: ResizeObserver loop spam, dev HMR errors.
    ignoreErrors: [
      /ResizeObserver loop limit exceeded/,
      /ResizeObserver loop completed with undelivered notifications/,
    ],
  });

  initialized = true;
  registerExceptionReporter(captureException);
  initWebVitalsRum();
}

export function resetSentryForTests(): void {
  initialized = false;
  rumInitialized = false;
}

export const SentryErrorBoundary = Sentry.ErrorBoundary;
