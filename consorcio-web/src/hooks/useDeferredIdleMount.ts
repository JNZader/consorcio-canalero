import { useEffect, useState } from 'react';

/**
 * Fallback delay for browsers without ``requestIdleCallback`` (Safari <17).
 * Three seconds is past the LCP window on the slow mobile links this app is
 * actually used on, while still being early enough that a long-lived tab
 * notices a deploy within the same minute.
 */
const IDLE_FALLBACK_MS = 3000;

/**
 * Deadline for ``requestIdleCallback`` so a permanently busy main thread
 * cannot postpone the work forever.
 */
const IDLE_TIMEOUT_MS = 5000;

/**
 * Returns ``false`` until the page has finished loading AND the main thread
 * has gone idle, then flips to ``true`` — permanently.
 *
 * Use it to keep work that is genuinely not needed in the first seconds out
 * of the critical rendering path. Gating a component on this hook means its
 * hooks do not run at all on the first React commit, which is the only way to
 * defer a side effect that lives inside a third-party hook.
 */
export function useDeferredIdleMount(): boolean {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let idleHandle: number | undefined;
    let timeoutHandle: ReturnType<typeof setTimeout> | undefined;

    const flip = () => {
      if (!cancelled) setReady(true);
    };

    const armIdleCallback = () => {
      if (cancelled) return;
      if (typeof window.requestIdleCallback === 'function') {
        idleHandle = window.requestIdleCallback(flip, { timeout: IDLE_TIMEOUT_MS });
      } else {
        timeoutHandle = setTimeout(flip, IDLE_FALLBACK_MS);
      }
    };

    // ``load`` has already fired if this mounts after hydration of a warm
    // navigation — the event would never come again, so arm immediately.
    if (document.readyState === 'complete') {
      armIdleCallback();
    } else {
      window.addEventListener('load', armIdleCallback, { once: true });
    }

    return () => {
      cancelled = true;
      window.removeEventListener('load', armIdleCallback);
      if (idleHandle !== undefined) window.cancelIdleCallback?.(idleHandle);
      if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
    };
  }, []);

  return ready;
}
