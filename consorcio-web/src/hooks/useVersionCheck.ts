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
      // Kick the service worker to check for a new ``sw.js`` whenever we
      // detect a fresh ``version.json``. Without this, the SW only re-checks
      // when the browser decides (can take 24 h), so when the user clicks
      // "Actualizar" the new SW might still be the old one in cache and the
      // banner-reload cycle keeps serving stale assets — the very thing
      // forcing a Ctrl+Shift+R bypass.
      if (
        info.sha !== initialShaRef.current &&
        typeof navigator !== 'undefined' &&
        'serviceWorker' in navigator
      ) {
        try {
          const reg = await navigator.serviceWorker.getRegistration();
          if (reg) await reg.update();
        } catch (err) {
          logger.debug('[version-check] reg.update() failed', err);
        }
      }
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
  };
}
