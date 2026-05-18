/**
 * useVersionCheck — polls ``/version.json`` to detect a newer deployment.
 *
 * Cloudflare Pages serves the SPA bundle with hashed filenames, so any code
 * change produces new asset URLs. The hashed JS gets cached by URL forever
 * (long-cache OK), but the user's tab keeps the previously-loaded module
 * graph in memory — they only see the new version after a reload.
 *
 * This hook fetches ``/version.json`` shortly after mount, again every
 * ``intervalMs`` (default 5 minutes), and again when the tab regains
 * visibility. The first response defines the "baseline" SHA the tab was
 * loaded with; if a later response carries a different ``sha`` we surface
 * that to the caller, which renders a "Reload to update" notification.
 *
 * Lives next to the other ``hooks/`` so it can share TanStack Query with
 * the rest of the app — but we deliberately use a raw ``fetch`` here:
 *   - the response must NEVER be cached, even within the React Query cache,
 *   - the polling cadence is driven by ``setInterval`` + the visibility
 *     event, not by Query's staleness model.
 */
import { useEffect, useRef, useState } from 'react';

import { logger } from '../lib/logger';

interface VersionInfo {
  sha: string;
  buildTime: string;
}

export interface VersionCheckResult {
  /** SHA seen on the very first response — what this tab was loaded with. */
  initialSha: string | null;
  /** Most recent SHA returned by ``/version.json``. */
  latestSha: string | null;
  /** True iff ``latestSha`` is set and different from ``initialSha``. */
  updateAvailable: boolean;
  /** Forces a one-shot reload that bypasses the HTTP cache. */
  reload: () => void;
}

const DEFAULT_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

async function fetchVersion(): Promise<VersionInfo | null> {
  try {
    const res = await fetch(`/version.json?t=${Date.now()}`, {
      cache: 'no-store',
      credentials: 'omit',
    });
    if (!res.ok) return null;
    const data = (await res.json()) as Partial<VersionInfo>;
    if (typeof data.sha !== 'string' || !data.sha) return null;
    return { sha: data.sha, buildTime: data.buildTime ?? '' };
  } catch (err) {
    // Offline / blocked / 404 — treat as "no info" rather than crashing.
    logger.debug('[version-check] fetch failed', err);
    return null;
  }
}

export function useVersionCheck(intervalMs: number = DEFAULT_INTERVAL_MS): VersionCheckResult {
  const initialShaRef = useRef<string | null>(null);
  const [initialSha, setInitialSha] = useState<string | null>(null);
  const [latestSha, setLatestSha] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      const info = await fetchVersion();
      if (cancelled || !info) return;
      if (initialShaRef.current === null) {
        initialShaRef.current = info.sha;
        setInitialSha(info.sha);
      }
      setLatestSha(info.sha);
    };

    void tick();
    const id = setInterval(() => void tick(), intervalMs);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void tick();
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [intervalMs]);

  const updateAvailable = !!(initialSha && latestSha && latestSha !== initialSha);

  return {
    initialSha,
    latestSha,
    updateAvailable,
    reload: () => {
      // Hash-route apps benefit from a hard reload — the bundled module
      // graph in memory references the previous deploy's chunks, which may
      // no longer exist on the CDN once the new deploy goes live.
      window.location.reload();
    },
  };
}
