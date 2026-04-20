/**
 * layerPropertyWhitelists.test.ts
 *
 * Phase 8 — whitelist the (very noisy) `caminos` / Red Vial feature properties
 * down to 7 human-labeled fields. Any layer without a whitelist falls through
 * to the default "show all non-__-prefixed" behavior.
 *
 * Single source of truth for tests is the module under test — labels live
 * there, not here — but we spot-check the 7 caminos keys exactly, in the
 * documented order.
 */

import { describe, expect, it } from 'vitest';

import {
  LAYER_PROPERTY_WHITELISTS,
  getDisplayableProperties,
  resolveLayerWhitelistKey,
} from '../../src/components/map2d/layerPropertyWhitelists';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';

describe('LAYER_PROPERTY_WHITELISTS', () => {
  it('defines the 7 caminos keys in the documented order', () => {
    expect(LAYER_PROPERTY_WHITELISTS.caminos).toEqual([
      'ccn',
      'fna',
      'gna',
      'hct',
      'red',
      'rst',
      'rtn',
    ]);
  });
});

describe('resolveLayerWhitelistKey', () => {
  it('resolves the roads line layer id to the "caminos" whitelist key', () => {
    expect(resolveLayerWhitelistKey(`${SOURCE_IDS.ROADS}-line`)).toBe('caminos');
  });

  it('returns null for a layer without a whitelist', () => {
    expect(resolveLayerWhitelistKey(`${SOURCE_IDS.CATASTRO}-fill`)).toBeNull();
  });

  it('returns null for undefined / empty input', () => {
    expect(resolveLayerWhitelistKey(undefined)).toBeNull();
    expect(resolveLayerWhitelistKey('')).toBeNull();
  });
});

describe('getDisplayableProperties', () => {
  const redVialProps = {
    altitudeMo: 'clampToGround',
    begin: '2000',
    ccc: null,
    ccn: '158',
    descriptio: 'RN 158 tramo A',
    end: '2023',
    extrude: 0,
    fna: 'RN 158',
    gna: 'Ruta Nacional',
    hct: 'Primaria',
    icon: '',
    lzn: null,
    rcc: null,
    red: 'Nacional',
    rst: 'Pavimentada',
    rtn: '158',
    tessellate: -1,
    timestamp: null,
    visibility: -1,
    color: '#FFEB3B',
  };

  it('returns ONLY the 7 whitelisted caminos keys in order for the roads layer', () => {
    const rows = getDisplayableProperties(`${SOURCE_IDS.ROADS}-line`, redVialProps);

    const keys = rows.map((r) => r.key);
    expect(keys).toEqual(['ccn', 'fna', 'gna', 'hct', 'red', 'rst', 'rtn']);
  });

  it('humanizes labels for caminos keys (Spanish — Rioplatense)', () => {
    const rows = getDisplayableProperties(`${SOURCE_IDS.ROADS}-line`, redVialProps);

    const labels = Object.fromEntries(rows.map((r) => [r.key, r.label]));
    expect(labels.ccn).toBe('Denominación');
    expect(labels.fna).toBe('Nombre');
    expect(labels.gna).toBe('Tipo');
    expect(labels.hct).toBe('Jerarquía');
    expect(labels.red).toBe('Red');
    expect(labels.rst).toBe('Superficie');
    expect(labels.rtn).toBe('Ruta');
  });

  it('preserves the original value for each whitelisted key', () => {
    const rows = getDisplayableProperties(`${SOURCE_IDS.ROADS}-line`, redVialProps);
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r.value]));
    expect(byKey.ccn).toBe('158');
    expect(byKey.fna).toBe('RN 158');
    expect(byKey.red).toBe('Nacional');
    expect(byKey.rst).toBe('Pavimentada');
  });

  it('skips whitelisted keys whose value is null / undefined / empty string', () => {
    const sparse = { ccn: '158', fna: null, gna: undefined, red: '' };
    const rows = getDisplayableProperties(`${SOURCE_IDS.ROADS}-line`, sparse);
    const keys = rows.map((r) => r.key);
    expect(keys).toEqual(['ccn']); // only the non-empty value
  });

  it('falls back to ALL non-__ properties (label === key) when layer has no whitelist', () => {
    const props = { nombre: 'Canal Este', estado: 'activo', __internal: 'hidden' };
    const rows = getDisplayableProperties(`${SOURCE_IDS.CATASTRO}-fill`, props);
    const keys = rows.map((r) => r.key);
    expect(keys).toEqual(['nombre', 'estado']);
    const labels = rows.map((r) => r.label);
    expect(labels).toEqual(['nombre', 'estado']); // label defaults to the key
  });

  it('falls back when layerId is undefined (no layer ID on feature)', () => {
    const props = { a: 1, b: 2 };
    const rows = getDisplayableProperties(undefined, props);
    expect(rows.map((r) => r.key)).toEqual(['a', 'b']);
  });

  it('handles empty properties object', () => {
    expect(getDisplayableProperties(`${SOURCE_IDS.ROADS}-line`, {})).toEqual([]);
    expect(getDisplayableProperties(undefined, {})).toEqual([]);
  });
});
