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
  LAYER_PROPERTY_FORMATTERS,
  LAYER_PROPERTY_LABELS,
  LAYER_PROPERTY_WHITELISTS,
  getDisplayableProperties,
  resolveLayerWhitelistKey,
} from '../../src/components/map2d/layerPropertyWhitelists';
import { buildClickableLayers } from '../../src/components/map2d/useMapInteractionEffects';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { ROAD_FLOW_LAYER_IDS } from '../../src/components/map2d/roadFlowLayers';

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

  it('returns catastro for CATASTRO fill/line layer ids', () => {
    expect(resolveLayerWhitelistKey(`${SOURCE_IDS.CATASTRO}-fill`)).toBe('catastro');
    expect(resolveLayerWhitelistKey(`${SOURCE_IDS.CATASTRO}-line`)).toBe('catastro');
  });

  it('returns null for a layer without a whitelist', () => {
    expect(resolveLayerWhitelistKey('some-unknown-layer-id')).toBeNull();
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
    const rows = getDisplayableProperties('some-unknown-layer-id', props);
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

  // ── approved-zones / cuencas: formatters ──────────────────────────────

  it('formats approved-zones superficie_ha as es-AR with " ha" suffix', () => {
    const rows = getDisplayableProperties(`${SOURCE_IDS.APPROVED_ZONES}-fill`, {
      nombre: 'Candil',
      superficie_ha: 22603.1,
    });
    const sup = rows.find((r) => r.key === 'superficie_ha');
    expect(sup?.formatted).toBe('22.603,1 ha');
  });

  it('formats member_basin_names as a string[] for bullet rendering', () => {
    const rows = getDisplayableProperties(`${SOURCE_IDS.APPROVED_ZONES}-fill`, {
      nombre: 'Candil',
      member_basin_names: ['Sub-cuenca 13', 'Sub-cuenca 7'],
    });
    const compone = rows.find((r) => r.key === 'member_basin_names');
    expect(compone?.formatted).toEqual(['Sub-cuenca 13', 'Sub-cuenca 7']);
  });

  it('parses MapLibre-serialised JSON-string arrays back into bullet lists', () => {
    // MapLibre's GeoJSON source stringifies array properties — what arrives
    // at the click handler is the literal string, not a JS array. The
    // formatter must defend against this so the InfoPanel never shows a raw
    // JSON dump in the "Compone" row.
    const rows = getDisplayableProperties(`${SOURCE_IDS.APPROVED_ZONES}-fill`, {
      nombre: 'Monte Leña',
      member_basin_names: '["Sub-cuenca 15 (ml)","Sub-cuenca 4 (ml)"]',
    });
    const compone = rows.find((r) => r.key === 'member_basin_names');
    expect(compone?.formatted).toEqual(['Sub-cuenca 15 (ml)', 'Sub-cuenca 4 (ml)']);
  });

  it('hides debug fields (zone_id, status, source, member_basin_ids) on approved-zones', () => {
    const rows = getDisplayableProperties(`${SOURCE_IDS.APPROVED_ZONES}-fill`, {
      zone_id: 'draft-zone-candil',
      nombre: 'Candil',
      status: 'approved-draft',
      source: 'suggested-zones-editor',
      family: 'candil',
      member_basin_ids: '["uuid1","uuid2"]',
    });
    const keys = rows.map((r) => r.key);
    expect(keys).not.toContain('zone_id');
    expect(keys).not.toContain('status');
    expect(keys).not.toContain('source');
    expect(keys).not.toContain('member_basin_ids');
    expect(keys).toContain('nombre');
  });

  // ── basins / sub-cuencas ──────────────────────────────────────────────

  it('hides the UUID id on basins and formats superficie_ha', () => {
    const rows = getDisplayableProperties(`${SOURCE_IDS.BASINS}-fill`, {
      id: '997b93a6-b4eb-4e56-9be0-7bb3229ee28e',
      nombre: 'Sub-cuenca 4 (ml)',
      cuenca: 'Monte Leña',
      superficie_ha: 7652.7,
    });
    const keys = rows.map((r) => r.key);
    expect(keys).toEqual(['nombre', 'cuenca', 'superficie_ha']);
    expect(rows.find((r) => r.key === 'superficie_ha')?.formatted).toBe('7.652,7 ha');
  });
});

// ---------------------------------------------------------------------------
// flujo-caminos S4 — task 4.5, RETIRED by the owner decision of 2026-08-23
// ---------------------------------------------------------------------------

/**
 * Task 4.5 whitelisted the properties of a CROSSING POPUP. The ratified wiring
 * builds no such popup: a crossing click opens `TramoSurveySheet` for its
 * segment, and the two `road_flow` ml layers are deliberately absent from
 * `buildClickableLayers`, so InfoPanel never receives one of those features.
 *
 * These assertions replace the ones that exercised the dead table. They pin the
 * RETIREMENT rather than deleting the coverage silently: re-adding a whitelist
 * here without also making those layers clickable (and mounting a disclaimer in
 * whatever surface reads them) would fail this file.
 */
describe('road-flow whitelist — retired with the popup (owner decision 2026-08-23)', () => {
  it('neither ml layer resolves to a whitelist key', () => {
    expect(resolveLayerWhitelistKey(ROAD_FLOW_LAYER_IDS.FLUJO)).toBeNull();
    expect(resolveLayerWhitelistKey(ROAD_FLOW_LAYER_IDS.CANAL)).toBeNull();
  });

  it('no `road-flow` table survives in any of the three registries', () => {
    expect(LAYER_PROPERTY_WHITELISTS['road-flow']).toBeUndefined();
    expect(LAYER_PROPERTY_LABELS['road-flow']).toBeUndefined();
    expect(LAYER_PROPERTY_FORMATTERS['road-flow']).toBeUndefined();
  });

  it('those layers are not clickable, which is WHY there is no whitelist', () => {
    const clickable = buildClickableLayers('idle');
    expect(clickable).not.toContain(ROAD_FLOW_LAYER_IDS.FLUJO);
    expect(clickable).not.toContain(ROAD_FLOW_LAYER_IDS.CANAL);
  });
});
