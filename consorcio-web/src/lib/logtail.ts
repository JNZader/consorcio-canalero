/**
 * BetterStack (Logtail) browser shipper — opt-in, explicit-call only.
 *
 * Initialised when ``VITE_LOGTAIL_TOKEN`` is set; otherwise the
 * exported ``logtail`` reference is ``null`` and the helper functions
 * are silent no-ops.
 *
 * Design note (post-3vr security review): an earlier version of this
 * module monkey-patched ``console.log/info/warn/error`` so every
 * console call also shipped to BetterStack. That captured a LOT of
 * accidental PII — every third-party lib that logs a request object
 * leaks the JWT bearer header, every Mantine notification error logs
 * the user email, etc. Now we keep ``console.*`` untouched and offer
 * explicit ``logInfo`` / ``logWarn`` / ``logError`` callers can opt
 * into per call site, with defensive redaction of Bearer tokens and
 * emails before the value leaves the box.
 *
 * Tuning:
 *   - ``VITE_LOGTAIL_TOKEN`` — "Source token" from
 *     https://logs.betterstack.com (Sources). Free tier: 1 GB/month.
 *   - ``VITE_LOGTAIL_ENDPOINT`` — override the ingest URL. EU region
 *     uses ``https://eu1.logs.betterstack.com``; leave empty for the
 *     SDK's default (US).
 */

import { Logtail } from '@logtail/browser';

import { registerLogErrorSink } from './errorReporting';
import { logger } from './logger';

let logtail: Logtail | null = null;

export function initLogtail(): void {
  const token = import.meta.env.VITE_LOGTAIL_TOKEN ?? '';
  const endpoint = import.meta.env.VITE_LOGTAIL_ENDPOINT ?? '';
  if (!token) {
    return;
  }
  logtail = new Logtail(token, endpoint ? { endpoint } : undefined);
  logger.configure({
    onError: (message, data) => {
      if (data === undefined) {
        logError(message);
      } else if (typeof data === 'object' && data !== null) {
        logError(message, data);
      } else {
        logError(message, { detail: data });
      }
    },
  });
  registerLogErrorSink((error, context) => {
    const errorMessage = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    const payload = {
      ...context,
      ...(error instanceof Error && error.stack ? { stack: error.stack } : {}),
    };
    logError(errorMessage, payload);
  });
}

export function resetLogtailForTests(): void {
  logtail = null;
  logger.configure({ onError: undefined });
}

/**
 * Defensive scrubber — runs on every value before it ships to
 * BetterStack so an accidental ``logError(error)`` that includes a
 * bearer token or an email doesn't leak to the log sink.
 *
 * Not a security boundary by itself (callers SHOULD avoid logging
 * sensitive data in the first place), but a meaningful second line
 * of defence.
 */
const BEARER_RE = /Bearer\s+[\w.\-]+/gi;
const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/g;

function redact(value: unknown): string {
  let s: string;
  if (typeof value === 'string') {
    s = value;
  } else if (value instanceof Error) {
    s = `${value.name}: ${value.message}`;
  } else if (value === null || value === undefined) {
    return String(value);
  } else {
    try {
      s = JSON.stringify(value);
    } catch {
      s = String(value);
    }
  }
  return s.replace(BEARER_RE, 'Bearer [REDACTED]').replace(EMAIL_RE, '[email]');
}

function formatMessage(args: unknown[]): string {
  return args.map(redact).join(' ');
}

export function logInfo(...args: unknown[]): void {
  logtail?.info(formatMessage(args));
}

export function logWarn(...args: unknown[]): void {
  logtail?.warn(formatMessage(args));
}

export function logError(...args: unknown[]): void {
  logtail?.error(formatMessage(args));
}
