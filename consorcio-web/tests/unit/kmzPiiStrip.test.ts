/**
 * kmzPiiStrip.test.ts
 *
 * Batch D — Phase 3 Pair 3 [RED] for `kmz-export-all-layers`.
 *
 * Pins `stripPii(properties)`:
 *   - Removes keys matching (case-insensitive): `cue`, `telefono`,
 *     `teléfono`, `email`, `directivo`, `sector`, `departamento`.
 *   - Preserves all other keys unchanged (including `null`/`undefined`
 *     values).
 *   - Recurses into nested objects (sanitizing PII at every depth).
 *   - Does NOT mutate the input — returns a new object.
 *   - `{}` input → `{}` output.
 *
 * Defensive contract: Phase 3 doesn't emit `<description>` yet, so
 * `stripPii` is unused in the current Placemark output. The helper is
 * still exported + tested so that when Phase 4+ adds extended data /
 * descriptions, PII can't leak by accident.
 */

import { describe, expect, it } from 'vitest';

import { stripPii } from '../../src/lib/kmzExport/kmzPiiStrip';

describe('stripPii — removes PII keys', () => {
  it('removes `cue`', () => {
    expect(stripPii({ cue: '12345', nombre: 'Ok' })).toEqual({ nombre: 'Ok' });
  });

  it('removes `telefono`', () => {
    expect(stripPii({ telefono: '0351-1234', nombre: 'Ok' })).toEqual({
      nombre: 'Ok',
    });
  });

  it('removes `teléfono` (accented)', () => {
    expect(stripPii({ teléfono: '0351-1234', nombre: 'Ok' })).toEqual({
      nombre: 'Ok',
    });
  });

  it('removes `email`', () => {
    expect(stripPii({ email: 'a@b.c', nombre: 'Ok' })).toEqual({ nombre: 'Ok' });
  });

  it('removes `directivo`', () => {
    expect(stripPii({ directivo: 'Sra Fulana', nombre: 'Ok' })).toEqual({
      nombre: 'Ok',
    });
  });

  it('removes `sector`', () => {
    expect(stripPii({ sector: 'Norte', nombre: 'Ok' })).toEqual({ nombre: 'Ok' });
  });

  it('removes `departamento`', () => {
    expect(stripPii({ departamento: 'Tercero Arriba', nombre: 'Ok' })).toEqual({
      nombre: 'Ok',
    });
  });
});

describe('stripPii — case insensitivity', () => {
  it('matches CUE, Cue, cUe indifferently', () => {
    expect(
      stripPii({ CUE: '1', Cue: '2', cUe: '3', keep: 'yes' }),
    ).toEqual({ keep: 'yes' });
  });

  it('matches DIRECTIVO and directivo and DirEctivo', () => {
    expect(
      stripPii({ DIRECTIVO: 'X', DirEctivo: 'Y', keep: 'yes' }),
    ).toEqual({ keep: 'yes' });
  });

  it('matches TELÉFONO / Teléfono', () => {
    expect(
      stripPii({ TELÉFONO: 'x', Teléfono: 'y', keep: 'yes' }),
    ).toEqual({ keep: 'yes' });
  });
});

describe('stripPii — preservation', () => {
  it('keeps unrelated keys unchanged', () => {
    const input = {
      nombre: 'Ok',
      count: 5,
      active: true,
      tags: ['a', 'b'],
    };
    expect(stripPii(input)).toEqual(input);
  });

  it('keeps null and undefined values on preserved keys', () => {
    const input = {
      nombre: null,
      extra: undefined,
      keep: 'yes',
    };
    expect(stripPii(input)).toEqual(input);
  });

  it('empty input → empty output', () => {
    expect(stripPii({})).toEqual({});
  });
});

describe('stripPii — immutability', () => {
  it('does NOT mutate the input', () => {
    const input = { cue: '1', nombre: 'Ok' };
    const before = { ...input };
    stripPii(input);
    expect(input).toEqual(before);
  });

  it('returns a new reference', () => {
    const input = { nombre: 'Ok' };
    const output = stripPii(input);
    expect(output).not.toBe(input);
  });
});

describe('stripPii — recursion into nested objects', () => {
  it('sanitizes nested objects recursively', () => {
    const input = {
      nombre: 'Ok',
      meta: {
        cue: 'hidden',
        directivo: 'hidden',
        keep: 'yes',
      },
    };
    expect(stripPii(input)).toEqual({
      nombre: 'Ok',
      meta: { keep: 'yes' },
    });
  });

  it('sanitizes deeply nested objects', () => {
    const input = {
      a: {
        b: {
          cue: 'hidden',
          keep: 'yes',
        },
        keep2: 'yes2',
      },
    };
    expect(stripPii(input)).toEqual({
      a: {
        b: { keep: 'yes' },
        keep2: 'yes2',
      },
    });
  });

  it('does not treat arrays as objects to recurse into', () => {
    const input = {
      nombre: 'Ok',
      list: [{ cue: '1', keep: 'yes' }],
    };
    const output = stripPii(input);
    // Arrays must be preserved as-is. Whether array items are also
    // sanitized is a future extension; the contract for Phase 3 keeps
    // the original semantics: recurse only into plain object values.
    expect(output.list).toBe(input.list);
  });
});
