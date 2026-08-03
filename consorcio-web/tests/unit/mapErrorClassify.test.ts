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
