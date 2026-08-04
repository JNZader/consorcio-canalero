/**
 * mapErrorClassify.test.ts — Batch 1 "datos honestos".
 *
 * The classifier must preserve the EXACT heuristic that used to live inline in
 * `useMapInitialization.ts` (a regression here silently floods `logger.error`
 * with tile noise, or worse, hides a real map error), and it must be total:
 * it runs inside a MapLibre event handler where a throw is swallowed.
 */

import { describe, expect, it } from 'vitest';

import { classifyMapError } from '../../src/components/map2d/mapErrorClassify';

describe('classifyMapError · tile detection', () => {
  it('classifies an event carrying a `tile` as a tile error', () => {
    expect(classifyMapError({ tile: {}, error: new Error('whatever') }).kind).toBe('tile');
  });

  it('classifies an AJAXError by message', () => {
    expect(classifyMapError({ error: new Error('AJAXError: Not Found (404)') }).kind).toBe('tile');
  });

  it('classifies an AJAXError by error name even when the message is generic', () => {
    const error = Object.assign(new Error('Not Found'), { name: 'AJAXError' });

    expect(classifyMapError({ error }).kind).toBe('tile');
  });

  it('classifies an Earth Engine tile host failure', () => {
    const error = new Error('Failed to fetch https://earthengine.googleapis.com/v1/tiles/1/2/3');

    expect(classifyMapError({ error }).kind).toBe('tile');
  });

  it('classifies a genuine map error as `other`', () => {
    expect(classifyMapError({ error: new Error('Style is not done loading') }).kind).toBe('other');
  });
});

describe('classifyMapError · extraction', () => {
  it('extracts sourceId, status and url from an AJAXError event', () => {
    const error = Object.assign(new Error('AJAXError: Not Found (404)'), {
      status: 404,
      url: 'https://tiles.example/1/2/3.png',
    });

    const classified = classifyMapError({ sourceId: 'dem-tiles', error });

    expect(classified).toEqual({
      kind: 'tile',
      sourceId: 'dem-tiles',
      // No serialized `source` travels with this event → type unknown (B4c/T4).
      sourceType: null,
      status: 404,
      url: 'https://tiles.example/1/2/3.png',
      message: 'AJAXError: Not Found (404)',
    });
  });

  it('leaves sourceId/status/url null when the event does not carry them', () => {
    const classified = classifyMapError({ error: new Error('AJAXError') });

    expect(classified.sourceId).toBeNull();
    expect(classified.status).toBeNull();
    expect(classified.url).toBeNull();
  });

  it('reads a string `error` as the message', () => {
    expect(classifyMapError({ error: 'AJAXError: boom' }).message).toBe('AJAXError: boom');
  });

  it('ignores a non-string sourceId instead of coercing it', () => {
    expect(classifyMapError({ sourceId: 42, error: new Error('AJAXError') }).sourceId).toBeNull();
  });
});

describe('classifyMapError · null safety', () => {
  it.each([[null], [undefined], ['boom'], [42]])('never throws for %p', (input) => {
    const classified = classifyMapError(input);

    expect(classified.kind).toBe('other');
    expect(classified.sourceId).toBeNull();
    expect(classified.status).toBeNull();
    expect(classified.url).toBeNull();
    expect(classified.message).toBe('');
  });

  it('handles an event with no `error` field at all', () => {
    expect(classifyMapError({}).kind).toBe('other');
    expect(classifyMapError({}).message).toBe('');
  });
});

/**
 * B4c/T4 (RES-003) — the source TYPE is what tells a one-shot `image` source
 * (the IGN overlay: one WebP for the whole extent) apart from a mosaic source
 * that fails one tile at a time. `Style.addSource` merges
 * `{ sourceId, source: sourceCache.serialize() }` into every event a source
 * fires, so the type travels with the failure.
 */
describe('classifyMapError · source type (B4c/T4)', () => {
  it('reads the type off the serialized `source`', () => {
    const classified = classifyMapError({
      sourceId: 'map2d-ign-overlay',
      source: { type: 'image', url: '/assets/ign.webp' },
      error: Object.assign(new Error('Not Found'), { name: 'AJAXError', status: 404 }),
    });

    expect(classified.sourceType).toBe('image');
    expect(classified.sourceId).toBe('map2d-ign-overlay');
    expect(classified.status).toBe(404);
  });

  it('falls back to the source id inside `source` when the event has no `sourceId`', () => {
    const classified = classifyMapError({
      source: { id: 'map2d-dem-raster', type: 'raster' },
      error: new Error('AJAXError'),
    });

    expect(classified.sourceId).toBe('map2d-dem-raster');
    expect(classified.sourceType).toBe('raster');
  });

  it('accepts a bare `sourceType` field when no serialized source travels', () => {
    expect(
      classifyMapError({ sourceType: 'vector', error: new Error('AJAXError') }).sourceType
    ).toBe('vector');
  });

  it('is null when nothing names a type, and never throws on a junk source', () => {
    expect(classifyMapError({ error: new Error('AJAXError') }).sourceType).toBeNull();
    expect(classifyMapError({ source: 'nope', error: new Error('x') }).sourceType).toBeNull();
    expect(classifyMapError({ source: { type: 7 }, error: new Error('x') }).sourceType).toBeNull();
  });
});
