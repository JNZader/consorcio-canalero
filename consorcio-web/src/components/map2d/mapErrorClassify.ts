/**
 * MapLibre `error` event classification (Batch 1 — "datos honestos").
 *
 * Extracted verbatim from the heuristic that used to live inline in
 * `useMapInitialization.ts`: a MapLibre error is a TILE error when the event
 * carries a `tile`, when the message names an `AJAXError`, or when it points at
 * Earth Engine's tile host. Everything else is a real map error and still goes
 * to `logger.error`.
 *
 * The classifier adds what the inline version threw away: the failing
 * `sourceId` and the AJAXError's `status` / `url`. That is what lets
 * `useRasterTileHealth` count failures PER SOURCE instead of treating the whole
 * map as one undifferentiated blob.
 *
 * Contract: total and null-safe. Any input (including `null`, `undefined` or a
 * string) yields a well-formed `ClassifiedMapError`; this runs inside a MapLibre
 * event handler where a throw would be swallowed or would break the map.
 */

export interface ClassifiedMapError {
  /** `tile` = a transport failure for one source's mosaics; `other` = real error. */
  readonly kind: 'tile' | 'other';
  /** MapLibre source id that failed, when the event carries one. */
  readonly sourceId: string | null;
  /**
   * MapLibre source TYPE (`raster`, `vector`, `image`, …) when the event
   * carries the serialized source, `null` otherwise.
   *
   * `Style.addSource` attaches `{ sourceId, source: sourceCache.serialize() }`
   * to every event a source fires, so a failing source names its own type. That
   * distinction is load-bearing (B4c/T4, RES-003): a `raster`/`vector` source
   * fails one MOSAIC at a time and needs a threshold to separate "this layer is
   * broken" from "we panned off its coverage", while an `image` source is ONE
   * request — one failure is the whole verdict, and waiting for 8 of them means
   * waiting forever.
   */
  readonly sourceType: string | null;
  /** HTTP status from an `AJAXError`, when present. */
  readonly status: number | null;
  /** Request URL from an `AJAXError`, when present. */
  readonly url: string | null;
  /** Best-effort human message; `''` when the event carries none. */
  readonly message: string;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null) return null;
  return value as Record<string, unknown>;
}

function extractMessage(error: unknown): string {
  if (typeof error === 'string') return error;
  if (error instanceof Error) return error.message;
  const record = asRecord(error);
  if (record && typeof record.message === 'string') return record.message;
  return '';
}

export function classifyMapError(event: unknown): ClassifiedMapError {
  const eventRecord = asRecord(event);
  const error = eventRecord ? eventRecord.error : undefined;
  const errorRecord = asRecord(error);

  const message = extractMessage(error);
  const errorName = errorRecord && typeof errorRecord.name === 'string' ? errorRecord.name : '';

  // Same three signals as the original inline check, plus `error.name` — a
  // MapLibre AJAXError does not always spell its class into the message.
  const isTile =
    (eventRecord !== null && 'tile' in eventRecord) ||
    /AJAXError/i.test(message) ||
    /AJAXError/i.test(errorName) ||
    /earthengine\.googleapis\.com/i.test(message);

  // `event.source` is the SERIALIZED source spec (`{ type, url, … }`) that
  // `Style.addSource` merges into every event the source fires — the only place
  // the source TYPE is available, and a second chance at the id.
  const sourceRecord = eventRecord ? asRecord(eventRecord.source) : null;

  const sourceId =
    eventRecord && typeof eventRecord.sourceId === 'string'
      ? eventRecord.sourceId
      : sourceRecord && typeof sourceRecord.id === 'string'
        ? sourceRecord.id
        : null;
  const sourceType =
    sourceRecord && typeof sourceRecord.type === 'string'
      ? sourceRecord.type
      : eventRecord && typeof eventRecord.sourceType === 'string'
        ? eventRecord.sourceType
        : null;
  const status = errorRecord && typeof errorRecord.status === 'number' ? errorRecord.status : null;
  const url = errorRecord && typeof errorRecord.url === 'string' ? errorRecord.url : null;

  return {
    kind: isTile ? 'tile' : 'other',
    sourceId,
    sourceType,
    status,
    url,
    message,
  };
}
