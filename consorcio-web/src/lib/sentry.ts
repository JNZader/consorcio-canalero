/**
 * Sentry init wrapper — fires only when ``VITE_SENTRY_DSN`` is set.
 *
 * Off by default so dev and forks pay zero overhead and no
 * cross-origin network request to ingest.sentry.io on every page load.
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

const DSN = import.meta.env.VITE_SENTRY_DSN ?? '';
const ENVIRONMENT =
  import.meta.env.VITE_SENTRY_ENVIRONMENT ?? import.meta.env.MODE ?? 'development';
const TRACES_SAMPLE_RATE = Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? '0');
const RELEASE = import.meta.env.VITE_APP_VERSION ?? undefined;

export function initSentry(): void {
  if (!DSN) {
    // Silent no-op in dev / unconfigured deploys.
    return;
  }
  Sentry.init({
    dsn: DSN,
    environment: ENVIRONMENT,
    release: RELEASE,
    tracesSampleRate: Number.isFinite(TRACES_SAMPLE_RATE) ? TRACES_SAMPLE_RATE : 0,
    // PII off — the backend already strips reset tokens / producer names
    // from public surfaces (Phase 0). Letting Sentry attach cookies and
    // IP addresses would walk that back. Operators who need the IP can
    // turn this on in their own fork.
    sendDefaultPii: false,
    // Filter known noise: ResizeObserver loop spam, dev HMR errors.
    ignoreErrors: [
      /ResizeObserver loop limit exceeded/,
      /ResizeObserver loop completed with undelivered notifications/,
    ],
  });
}

export const SentryErrorBoundary = Sentry.ErrorBoundary;
