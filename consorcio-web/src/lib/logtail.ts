/**
 * BetterStack (Logtail) browser shipper — initialised only when
 * ``VITE_LOGTAIL_TOKEN`` is set.
 *
 * Off by default: silent no-op for dev and self-hosted operators that
 * don't want frontend logs leaving the box. When configured, replaces
 * the global ``console.log/info/warn/error/debug`` so app-level logs
 * surface in BetterStack without sprinkling a separate logger import
 * across the code.
 *
 * Tuning:
 *   - ``VITE_LOGTAIL_TOKEN`` — "Source token" from
 *     https://logs.betterstack.com (Sources → Logtail). Free tier:
 *     1 GB/mes.
 *   - ``VITE_LOGTAIL_ENDPOINT`` — override the ingest URL. EU region
 *     uses ``https://eu1.logs.betterstack.com``; leave empty for the
 *     SDK's default (US).
 */

import { Logtail } from '@logtail/browser';

const TOKEN = import.meta.env.VITE_LOGTAIL_TOKEN ?? '';
const ENDPOINT = import.meta.env.VITE_LOGTAIL_ENDPOINT ?? '';

let logtail: Logtail | null = null;

export function initLogtail(): void {
  if (!TOKEN) {
    // Silent no-op when not configured.
    return;
  }
  logtail = new Logtail(TOKEN, ENDPOINT ? { endpoint: ENDPOINT } : undefined);
  // Mirror console.* into BetterStack. The original console calls keep
  // running so the devtools experience is unchanged.
  const origLog = console.log.bind(console);
  const origInfo = console.info.bind(console);
  const origWarn = console.warn.bind(console);
  const origError = console.error.bind(console);
  console.log = (...args: unknown[]) => {
    origLog(...args);
    logtail?.info(args.map(String).join(' '));
  };
  console.info = (...args: unknown[]) => {
    origInfo(...args);
    logtail?.info(args.map(String).join(' '));
  };
  console.warn = (...args: unknown[]) => {
    origWarn(...args);
    logtail?.warn(args.map(String).join(' '));
  };
  console.error = (...args: unknown[]) => {
    origError(...args);
    logtail?.error(args.map(String).join(' '));
  };
}
