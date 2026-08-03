/**
 * kmzMissingVisibleLayers.test.ts — T3c final round, R4-003.
 *
 * `buildKmz` filters the registry by VISIBILITY and skips absent/empty data
 * slots silently. That is the right export behaviour (a partial KMZ still
 * helps), but it used to hide behind a green "KMZ descargado correctamente":
 * exporting while a lazy source was still downloading produced a quietly
 * incomplete file. `findMissingVisibleLayerKeys` is what lets the caller tell
 * the truth in the toast.
 */

import { describe, expect, it } from 'vitest';

import { findMissingVisibleLayerKeys } from '../../src/lib/kmzExport/kmzBuilder';

const fc = {
  type: 'FeatureCollection',
  features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: {} }],
  // biome-ignore lint/suspicious/noExplicitAny: narrow fixture
} as any;
// biome-ignore lint/suspicious/noExplicitAny: narrow fixture
const emptyFc = { type: 'FeatureCollection', features: [] } as any;

/**
 * The YPF pin is ALWAYS-ON and always present in the real app (a bundled
 * constant, not a fetch), so fixtures include it unless the test is
 * specifically about the always-on rule.
 */
function withYpf(data: Record<string, unknown>) {
  // biome-ignore lint/suspicious/noExplicitAny: narrow fixture
  return { 'ypf-estacion-bombeo': fc, ...data } as any;
}

describe('findMissingVisibleLayerKeys', () => {
  it('reports a VISIBLE layer whose source is still null (mid-download)', () => {
    const missing = findMissingVisibleLayerKeys(
      { canales_relevados: true, escuelas: true },
      withYpf({ canales_relevados: null, escuelas: fc })
    );

    expect(missing).toEqual(['canales_relevados']);
  });

  it('reports a VISIBLE layer whose source resolved EMPTY', () => {
    const missing = findMissingVisibleLayerKeys(
      { escuelas: true },
      withYpf({ escuelas: emptyFc })
    );

    expect(missing).toEqual(['escuelas']);
  });

  it('reports nothing when every visible layer has data', () => {
    const missing = findMissingVisibleLayerKeys(
      { canales_relevados: true, escuelas: true },
      withYpf({ canales_relevados: fc, escuelas: fc })
    );

    expect(missing).toEqual([]);
  });

  it('ignores layers the user turned OFF — those are absent on purpose', () => {
    const missing = findMissingVisibleLayerKeys(
      { canales_relevados: false },
      withYpf({ canales_relevados: null })
    );

    expect(missing).toEqual([]);
  });

  it('still reports an always-on layer with no data (implicitly requested)', () => {
    const missing = findMissingVisibleLayerKeys({}, { 'ypf-estacion-bombeo': null });
    expect(missing).toContain('ypf-estacion-bombeo');
  });

  it('never reports an EXCLUDED key, even when flipped on', () => {
    const missing = findMissingVisibleLayerKeys(
      { puntos_conflicto: true, approved_zones: true, basins: true },
      withYpf({})
    );

    expect(missing).not.toContain('puntos_conflicto');
    expect(missing).not.toContain('approved_zones');
    expect(missing).not.toContain('basins');
  });
});
