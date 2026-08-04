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
 * ONE-SHOT SOURCES BYPASS THE THRESHOLD (B4c/T4, RES-003): the historic IGN
 * altimetry overlay is a MapLibre `image` source — a single WebP request for the
 * whole extent. It can never reach 8 failures in 15 s, so a 404 right after the
 * user turned the layer on was a silent no-op: the layer simply never appeared
 * and `layerHealth` said everything was fine. For source types that fail as a
 * WHOLE (`image`, `video`, `canvas`) one failure IS the verdict, so they degrade
 * on the first error. Mosaic sources (`raster`, `vector`) keep the counter —
 * that anti-noise rule is what stops a pan off-coverage from screaming.
 *
 * …AND THEY DO NOT RECOVER BY SILENCE (B4c fix round, REL-001/RES-001). The
 * `recoverMs` sweep encodes "no new failures ⇒ the source healed", which is true
 * for tiles precisely BECAUSE they retry themselves on the next pan/zoom. An
 * `ImageSource` never retries anything: it requests once from `onAdd` and
 * `loadTile` only marks the tile errored. Letting the sweep clear it would have
 * declared the layer recovered 60 s later with the map still blank — the same
 * silent no-op, one minute late. One-shot keys therefore stay degraded until
 * something ACTS: {@link RasterTileHealth.clearSource}, called by the retry that
 * actually re-downloads (`reloadIgnSource`). A fresh failure re-degrades on its
 * first error, so an optimistic clear is never a lie for long.
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
import { SOURCE_IDS } from './map2dConfig';
import type { ClassifiedMapError } from './mapErrorClassify';

export interface UseRasterTileHealthOptions {
  /** Rolling window in which failures accumulate. Default 15 s. */
  readonly windowMs?: number;
  /** Failures inside the window that flip a source to `degradado`. Default 8. */
  readonly threshold?: number;
  /** Silence after which a degraded source recovers. Default 60 s. */
  readonly recoverMs?: number;
  /**
   * Extra source ids that degrade on the FIRST failure, whatever type the event
   * reports. The type check below already covers the real ones; this is the
   * escape hatch for an event that arrives without a serialized source (and the
   * seam the tests use). Defaults to the IGN overlay.
   */
  readonly immediateSourceIds?: readonly string[];
}

export interface RasterTileHealth {
  /** Source ids currently considered degraded. Stable identity between transitions. */
  readonly degradedSourceIds: readonly string[];
  /**
   * Feed one classified MapLibre error.
   *
   * Ignored unless it is a `tile` error OR it names a ONE-SHOT source (an
   * `image`/`video`/`canvas` source, or one listed in `immediateSourceIds`) —
   * an image source that fails without an AJAXError-shaped message is exactly
   * the silent case this hook exists to catch, so `kind: 'other'` is not a
   * reason to drop it there.
   */
  readonly onMapError: (error: ClassifiedMapError) => void;
  /**
   * Forget everything known about one source: degraded flag, failure window and
   * last-error stamp.
   *
   * The recovery path for one-shot sources, which never recover by silence (see
   * the module header). Call it FROM the action that genuinely retries the
   * download; if the retry fails again the next error re-degrades it
   * immediately. A no-op for a source that was never degraded.
   */
  readonly clearSource: (sourceId: string) => void;
}

/** Bucket for tile errors that arrive without an identifiable source. */
export const UNKNOWN_SOURCE_KEY = 'desconocido';

/**
 * MapLibre source types served by ONE request for the whole extent. A failure
 * is terminal for the layer, not a sample of a mosaic — see the module header.
 */
export const SINGLE_REQUEST_SOURCE_TYPES: readonly string[] = ['image', 'video', 'canvas'];

/** Source ids that degrade on the first failure by default (the IGN overlay). */
export const DEFAULT_IMMEDIATE_SOURCE_IDS: readonly string[] = [SOURCE_IDS.IGN];

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
  // UNION, not replace: the option is documented as EXTRA ids, so overriding it
  // must not silently drop the IGN overlay from the one-shot set (a caller that
  // adds one id would otherwise take the built-in default away).
  const immediateSourceIds = [
    ...DEFAULT_IMMEDIATE_SOURCE_IDS,
    ...(options.immediateSourceIds ?? []),
  ];

  const [degradedSourceIds, setDegradedSourceIds] = useState<readonly string[]>([]);
  /** sourceId → failure timestamps inside the rolling window. */
  const eventsRef = useRef<Map<string, number[]>>(new Map());
  /** sourceId → timestamp of its most recent failure (drives recovery). */
  const lastErrorAtRef = useRef<Map<string, number>>(new Map());
  const degradedRef = useRef<Set<string>>(new Set());
  /**
   * Degraded keys that must NOT be cleared by the silence sweep — one-shot
   * sources, which never retry themselves. See the module header.
   */
  const oneShotRef = useRef<Set<string>>(new Set());
  /** Last list handed to React — lets `publishDegraded` skip no-op writes. */
  const publishedRef = useRef<readonly string[]>([]);

  const onMapError = (error: ClassifiedMapError) => {
    const key = error.sourceId ?? UNKNOWN_SOURCE_KEY;

    // ONE-SHOT verdict (B4c/T4): an `image`/`video`/`canvas` source is a single
    // request for the whole extent. Named sources only — `desconocido` can never
    // be published, so degrading it instantly would just be a silent no-op.
    const isOneShot =
      key !== UNKNOWN_SOURCE_KEY &&
      ((error.sourceType !== null && SINGLE_REQUEST_SOURCE_TYPES.includes(error.sourceType)) ||
        immediateSourceIds.includes(key));

    // Non-tile errors still reach the health registry when they name a one-shot
    // source: an image source that fails without an AJAXError-shaped message is
    // exactly the silent case this exists to catch.
    if (error.kind !== 'tile' && !isOneShot) return;

    const now = Date.now();

    const timestamps = eventsRef.current.get(key) ?? [];
    const recent = timestamps.filter((at) => now - at < windowMs);
    recent.push(now);
    eventsRef.current.set(key, recent);
    lastErrorAtRef.current.set(key, now);

    if (degradedRef.current.has(key)) return;
    // Mosaic sources keep the anti-noise threshold; one-shot sources skip it.
    if (!isOneShot && recent.length < threshold) return;

    // ── TRANSITION ok → degradado: the only place we log and re-render.
    degradedRef.current.add(key);
    // Remember HOW it degraded: the silence sweep must not "recover" a source
    // that has no retry of its own (REL-001).
    if (isOneShot) oneShotRef.current.add(key);
    logger.warn(
      isOneShot
        ? `[rasterTiles] fuente "${key}" degradada: falló su única request (source de tipo ${
            error.sourceType ?? 'imagen'
          })`
        : `[rasterTiles] fuente "${key}" degradada: ${recent.length} errores de mosaico en ${Math.round(
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
        // A one-shot source produces no further errors BECAUSE it never retries,
        // so silence here means "still broken", not "healed" (REL-001). Only an
        // explicit `clearSource` — from the action that actually re-downloads —
        // takes it out.
        if (oneShotRef.current.has(key)) continue;
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

  const clearSource = (sourceId: string) => {
    const wasDegraded = degradedRef.current.delete(sourceId);
    eventsRef.current.delete(sourceId);
    lastErrorAtRef.current.delete(sourceId);
    oneShotRef.current.delete(sourceId);
    if (wasDegraded) logger.warn(`[rasterTiles] fuente "${sourceId}" reintentada`);
    // Unconditional for the same reason the sweep is: `publishDegraded` is the
    // one place that decides whether React hears about it.
    publishDegraded(degradedRef.current, publishedRef, setDegradedSourceIds);
  };

  return { degradedSourceIds, onMapError, clearSource };
}
