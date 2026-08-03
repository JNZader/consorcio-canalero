/**
 * useRasterTileHealth — turns MapLibre's tile-error firehose into a stable,
 * per-source "degradado" signal (Batch 1 — "datos honestos").
 *
 * WHY A COUNTER AND NOT A FLAG: MapLibre emits ONE `error` event per failed
 * tile. Panning over an area a raster source does not cover produces dozens of
 * events per second, and a naive `setState` per event would re-render the whole
 * map container on every one of them. So:
 *   - every event only touches REFS (a rolling window of timestamps per source);
 *   - `setState` fires ONLY on a transition — ok → degradado and degradado → ok;
 *   - the logger emits exactly ONE line per transition, not per tile.
 *
 * A source is DEGRADADO once it accumulates `threshold` failures inside
 * `windowMs`, and RECOVERS after `recoverMs` without a single new failure
 * (checked by a 5 s interval, cleared on unmount). Tiles retry themselves on the
 * next pan/zoom, which is why the health entry exposes no `reload`.
 *
 * Errors WITHOUT a `sourceId` are counted under the `desconocido` bucket: they
 * still produce a log line when they cross the threshold, but they never enter
 * `degradedSourceIds` — we cannot honestly name a layer we could not identify.
 * That bucket LIVES in the degraded set (so it is not re-logged on every tile
 * and so it recovers like any other key) but is filtered out at PUBLICATION
 * time by `publishDegraded`. Both write paths — the threshold transition and
 * the recovery sweep — must go through that one function; publishing the raw
 * set from either would leak `desconocido` into the UI the moment a real source
 * degrades alongside it.
 */

import { type RefObject, useEffect, useRef, useState } from 'react';
import { logger } from '../../lib/logger';
import type { ClassifiedMapError } from './mapErrorClassify';

export interface UseRasterTileHealthOptions {
  /** Rolling window in which failures accumulate. Default 15 s. */
  readonly windowMs?: number;
  /** Failures inside the window that flip a source to `degradado`. Default 8. */
  readonly threshold?: number;
  /** Silence after which a degraded source recovers. Default 60 s. */
  readonly recoverMs?: number;
}

export interface RasterTileHealth {
  /** Source ids currently considered degraded. Stable identity between transitions. */
  readonly degradedSourceIds: readonly string[];
  /** Feed one classified MapLibre error. Non-tile errors are ignored. */
  readonly onMapError: (error: ClassifiedMapError) => void;
}

/** Bucket for tile errors that arrive without an identifiable source. */
export const UNKNOWN_SOURCE_KEY = 'desconocido';

/** How often the recovery sweep runs. Independent of `recoverMs`. */
const RECOVERY_SWEEP_MS = 5000;

/**
 * THE ONLY writer of the published list. Module-level (not a closure) for two
 * reasons: the recovery effect can call it while keeping `[recoverMs]` as its
 * sole dependency, and there is exactly one place where the `desconocido`
 * filter and the no-op guard can drift out of sync — none.
 *
 * Publishing is skipped when the resulting list is identical to the last one,
 * so an expiring `desconocido` (invisible by construction) never re-renders and
 * never leaves a ghost entry behind.
 */
function publishDegraded(
  degraded: Set<string>,
  publishedRef: RefObject<readonly string[]>,
  setDegradedSourceIds: (ids: readonly string[]) => void
): void {
  const next = [...degraded].filter((key) => key !== UNKNOWN_SOURCE_KEY).sort();
  const prev = publishedRef.current;
  if (prev.length === next.length && prev.every((id, index) => id === next[index])) return;
  publishedRef.current = next;
  setDegradedSourceIds(next);
}

export function useRasterTileHealth(options: UseRasterTileHealthOptions = {}): RasterTileHealth {
  const windowMs = options.windowMs ?? 15000;
  const threshold = options.threshold ?? 8;
  const recoverMs = options.recoverMs ?? 60000;

  const [degradedSourceIds, setDegradedSourceIds] = useState<readonly string[]>([]);
  /** sourceId → failure timestamps inside the rolling window. */
  const eventsRef = useRef<Map<string, number[]>>(new Map());
  /** sourceId → timestamp of its most recent failure (drives recovery). */
  const lastErrorAtRef = useRef<Map<string, number>>(new Map());
  const degradedRef = useRef<Set<string>>(new Set());
  /** Last list handed to React — lets `publishDegraded` skip no-op writes. */
  const publishedRef = useRef<readonly string[]>([]);

  const onMapError = (error: ClassifiedMapError) => {
    if (error.kind !== 'tile') return;

    const key = error.sourceId ?? UNKNOWN_SOURCE_KEY;
    const now = Date.now();

    const timestamps = eventsRef.current.get(key) ?? [];
    const recent = timestamps.filter((at) => now - at < windowMs);
    recent.push(now);
    eventsRef.current.set(key, recent);
    lastErrorAtRef.current.set(key, now);

    if (recent.length < threshold || degradedRef.current.has(key)) return;

    // ── TRANSITION ok → degradado: the only place we log and re-render.
    degradedRef.current.add(key);
    logger.warn(
      `[rasterTiles] fuente "${key}" degradada: ${recent.length} errores de mosaico en ${Math.round(
        windowMs / 1000
      )}s`,
      { status: error.status, url: error.url }
    );

    // `desconocido` is deliberately NOT special-cased here: it belongs in the
    // set (dedup + recovery) and is filtered at publication. Naming it in the
    // UI would be noise the user cannot act on.
    publishDegraded(degradedRef.current, publishedRef, setDegradedSourceIds);
  };

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      for (const key of [...degradedRef.current]) {
        const lastAt = lastErrorAtRef.current.get(key) ?? 0;
        if (now - lastAt < recoverMs) continue;

        // ── TRANSITION degradado → ok.
        degradedRef.current.delete(key);
        eventsRef.current.delete(key);
        lastErrorAtRef.current.delete(key);
        logger.warn(`[rasterTiles] fuente "${key}" recuperada`);
      }
      // Unconditional: `publishDegraded` decides whether anything actually
      // changed. A hand-rolled `changed` flag is exactly how a recovered source
      // stays on screen (or an expired `desconocido` forces a pointless write).
      publishDegraded(degradedRef.current, publishedRef, setDegradedSourceIds);
    }, RECOVERY_SWEEP_MS);

    return () => clearInterval(interval);
    // Refs and the state setter are stable; only the recovery threshold matters.
  }, [recoverMs]);

  return { degradedSourceIds, onMapError };
}
