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
// flujo-caminos S4 — task 4.5: the road-crossing popup
// ---------------------------------------------------------------------------

describe('road-flow whitelist (flujo-caminos, design D6)', () => {
  it('routes BOTH ml layers to the single `road-flow` key', () => {
    expect(resolveLayerWhitelistKey(ROAD_FLOW_LAYER_IDS.FLUJO)).toBe('road-flow');
    expect(resolveLayerWhitelistKey(ROAD_FLOW_LAYER_IDS.CANAL)).toBe('road-flow');
  });

  it('reads Spanish labels — NEVER raw wire keys', () => {
    const rows = getDisplayableProperties(ROAD_FLOW_LAYER_IDS.FLUJO, {
      id: 'e1b0d0ee-1c6e-4a0f-9d2e-2b7b7f6ab111',
      tipo: 'flujo_natural',
      tramo_ref: 'RV-1042',
      canal_ref: null,
      direccion_flujo_deg: 245,
      rumbo_camino_deg: 88,
      lado_cruce: 'norte',
      area_aporte_ha: 128.4,
      orden_ranking: 3,
      confianza: 'alta',
      nota: null,
    });

    const labels = rows.map((r) => r.label);
    expect(labels).toContain('Dirección del flujo');
    expect(labels).toContain('Rumbo del camino');
    expect(labels).toContain('Área de aporte');
    expect(labels).toContain('Puesto');
    expect(labels).toContain('Confianza');

    // No raw key ever reaches the popup as its own label.
    for (const raw of [
      'direccion_flujo_deg',
      'rumbo_camino_deg',
      'area_aporte_ha',
      'orden_ranking',
      'confianza',
    ]) {
      expect(labels).not.toContain(raw);
    }

    // Plumbing stays hidden.
    expect(rows.map((r) => r.key)).not.toContain('id');
    expect(rows.map((r) => r.key)).not.toContain('canal_ref');
    expect(rows.map((r) => r.key)).not.toContain('lado_cruce');
  });

  it('formats degrees, hectares and the low-confidence marker', () => {
    const rows = getDisplayableProperties(ROAD_FLOW_LAYER_IDS.CANAL, {
      tramo_ref: 'RV-77',
      direccion_flujo_deg: 12,
      area_aporte_ha: 1520.55,
      confianza: 'baja',
      nota: 'incidencia oblicua (31.2 grados)',
    });
    const by = (key: string) => rows.find((r) => r.key === key)?.formatted;
    expect(by('direccion_flujo_deg')).toBe('12°');
    expect(by('area_aporte_ha')).toBe('1.520,6 ha');
    expect(by('confianza')).toBe('Baja — orientación aproximada');
  });

  it('publishes NO hydraulic magnitude — not even as a hidden key', () => {
    const forbidden = [
      'volumen',
      'caudal',
      'profundidad',
      'ancho_cuneta',
      'capacidad',
      'periodo_retorno',
    ];
    for (const key of LAYER_PROPERTY_WHITELISTS['road-flow']) {
      expect(forbidden).not.toContain(key);
    }
  });
});
