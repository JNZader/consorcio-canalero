/**
 * layerHealth.test.ts — Batch 1 "datos honestos".
 *
 * Pins the four rules that make the registry honest:
 *   1. aggregation — one entry per FAMILY, `failed` = error + degradado;
 *   2. `cargando` is NOT a failure (a family still loading has not failed);
 *   3. a CLOSED gate produces NO entry (no false positive for the anonymous
 *      visitor, and `retryAll` can never fire the deferred multi-MB fetch);
 *   4. `retryAll` only reloads FAILED entries and tolerates a null `reload`.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  buildHealthBannerText,
  buildLayerHealth,
  rasterTilesMessage,
} from '../../src/components/map2d/layerHealth';
import { LAYER_CATEGORY } from '../../src/components/map2d/map2dDerived';

describe('buildLayerHealth · aggregation', () => {
  it('returns an empty registry for empty inputs', () => {
    const health = buildLayerHealth();

    expect(health.entries).toHaveLength(0);
    expect(health.failed).toHaveLength(0);
    expect(health.byCategory).toEqual({});
  });

  it('classifies each slot into ok / cargando / error', () => {
    const health = buildLayerHealth({
      basins: { error: null },
      waterways: { loading: true },
      canales: { error: 'No se pudieron cargar los canales' },
    });

    const byKey = Object.fromEntries(health.entries.map((entry) => [entry.key, entry]));
    expect(byKey.basins?.status).toBe('ok');
    expect(byKey.waterways?.status).toBe('cargando');
    expect(byKey.canales?.status).toBe('error');
  });

  it('counts ONLY error + degradado as failed — `cargando` is not a failure', () => {
    const health = buildLayerHealth({
      waterways: { loading: true },
      basins: { error: null },
      canales: { error: 'boom' },
      raster_tiles: { degradedSourceIds: ['dem-tiles'] },
    });

    expect(health.failed.map((entry) => entry.key)).toEqual(['canales', 'raster_tiles']);
  });

  it('maps failed entries onto their accordion category, first failure winning', () => {
    const health = buildLayerHealth({
      // Both live in TERRITORIO — soil comes first in the registry order.
      soil: { error: 'suelos caídos' },
      escuelas: { error: 'escuelas caídas' },
      canales: { error: 'canales caídos' },
    });

    expect(health.byCategory.territorio?.key).toBe('soil');
    expect(health.byCategory.canales?.key).toBe('canales');
    // Healthy categories are simply absent.
    expect(health.byCategory.hidrografia).toBeUndefined();
  });

  it('never gives raster tiles an accordion home (banner only)', () => {
    const health = buildLayerHealth({
      raster_tiles: { degradedSourceIds: ['a', 'b'] },
    });

    const entry = health.entries[0];
    expect(entry?.key).toBe('raster_tiles');
    expect(entry?.status).toBe('degradado');
    expect(entry?.category).toBeNull();
    expect(entry?.reload).toBeNull();
    expect(entry?.message).toBe(rasterTilesMessage(2));
    expect(Object.keys(health.byCategory)).toHaveLength(0);
  });

  it('pluralises the raster-tile copy on the source count', () => {
    expect(rasterTilesMessage(1)).toMatch(/de 1 capa /);
    expect(rasterTilesMessage(3)).toMatch(/de 3 capas /);
  });

  it('omits the raster-tile entry when nothing is degraded', () => {
    const health = buildLayerHealth({
      raster_tiles: { degradedSourceIds: [] },
    });

    expect(health.entries).toHaveLength(0);
  });
});

describe('buildLayerHealth · gates', () => {
  it('produces NO entry for a lazy family whose gate is closed', () => {
    const health = buildLayerHealth({
      soil: { error: 'suelos caídos' },
      catastro: { error: 'catastro caído' },
      geo_layers: { error: 'DEM caído' },
      gates: { soil: false, catastro: false, geoLayers: false },
    });

    expect(health.entries).toHaveLength(0);
    expect(health.failed).toHaveLength(0);
  });

  it('reports a gated family once its gate opens', () => {
    const health = buildLayerHealth({
      soil: { error: 'suelos caídos' },
      gates: { soil: true },
    });

    expect(health.failed.map((entry) => entry.key)).toEqual(['soil']);
  });

  it('defaults an unspecified gate to OPEN (back-compat for partial callers)', () => {
    const health = buildLayerHealth({ soil: { error: 'suelos caídos' } });

    expect(health.failed.map((entry) => entry.key)).toEqual(['soil']);
  });

  it('a closed gate keeps retryAll from firing the deferred fetch', () => {
    const reloadSoil = vi.fn();
    const health = buildLayerHealth({
      soil: { error: 'suelos caídos', reload: reloadSoil },
      gates: { soil: false },
    });

    health.retryAll();

    expect(reloadSoil).not.toHaveBeenCalled();
  });
});

describe('buildLayerHealth · retryAll', () => {
  it('reloads ONLY the failed entries', () => {
    const reloadOk = vi.fn();
    const reloadLoading = vi.fn();
    const reloadFailed = vi.fn();

    const health = buildLayerHealth({
      basins: { error: null, reload: reloadOk },
      waterways: { loading: true, reload: reloadLoading },
      canales: { error: 'boom', reload: reloadFailed },
    });

    health.retryAll();

    expect(reloadOk).not.toHaveBeenCalled();
    expect(reloadLoading).not.toHaveBeenCalled();
    expect(reloadFailed).toHaveBeenCalledTimes(1);
  });

  it('tolerates a failed entry without a reload (raster tiles) and still reloads the rest', () => {
    const reloadCanales = vi.fn();

    const health = buildLayerHealth({
      canales: { error: 'boom', reload: reloadCanales },
      escuelas: { error: 'boom' },
      raster_tiles: { degradedSourceIds: ['dem-tiles'] },
    });

    expect(() => health.retryAll()).not.toThrow();
    expect(reloadCanales).toHaveBeenCalledTimes(1);
  });
});

describe('buildLayerHealth · curated user-facing copy', () => {
  it('NEVER surfaces the raw technical Error message from the slot', () => {
    const health = buildLayerHealth({
      soil: { error: 'Error fetching soil map: 404 (/data/suelos_cu.geojson)' },
    });

    const entry = health.entries[0];
    expect(entry?.message).toBe('No se pudo cargar la capa de suelos');
    expect(entry?.message).not.toMatch(/404|geojson|fetching/i);
  });

  it('gives every family a Spanish message and none while healthy', () => {
    const health = buildLayerHealth({
      caminos: { error: 'boom' },
      basins: { error: 'boom' },
      waterways: { error: 'boom' },
      geo_layers: { error: 'boom' },
      catastro: { error: 'boom' },
      canales: { error: 'boom' },
      escuelas: { error: 'boom' },
      pilar_verde: { error: 'boom' },
    });

    for (const entry of health.entries) {
      expect(entry.message).toMatch(/^No se pud/);
    }
    expect(buildLayerHealth({ basins: { error: null } }).entries[0]?.message).toBeNull();
  });
});

describe('buildLayerHealth · Pilar Verde gate', () => {
  it('produces NO entry while no pilar_verde layer is toggled on', () => {
    // Real sequence this guards: layer on → group fails → user turns it off.
    // `staleTime: Infinity` keeps `layersError` set forever, so without the gate
    // the banner became permanent and its retry re-downloaded ~1 MB.
    const health = buildLayerHealth({
      pilar_verde: { error: 'Pilar Verde: no se pudieron cargar agroZonas' },
      gates: { pilarVerde: false },
    });

    expect(health.entries).toHaveLength(0);
    expect(health.failed).toHaveLength(0);
  });

  it('reports the family while a pilar_verde layer IS on', () => {
    const health = buildLayerHealth({
      pilar_verde: { error: 'Pilar Verde: no se pudieron cargar agroZonas' },
      gates: { pilarVerde: true },
    });

    expect(health.failed.map((entry) => entry.key)).toEqual(['pilar_verde']);
    expect(health.byCategory.pilar_verde?.message).toBe(
      'No se pudieron cargar las capas de Pilar Verde'
    );
  });
});

describe('buildHealthBannerText', () => {
  it('returns null when nothing failed', () => {
    expect(buildHealthBannerText([])).toBeNull();
    expect(buildHealthBannerText(buildLayerHealth({ basins: { error: null } }).failed)).toBeNull();
  });

  it('uses the singular / plural "no cargó" copy for real load failures', () => {
    const one = buildLayerHealth({ basins: { error: 'boom' } });
    const many = buildLayerHealth({
      basins: { error: 'boom' },
      canales: { error: 'boom' },
    });

    expect(buildHealthBannerText(one.failed)).toBe('1 capa no cargó');
    expect(buildHealthBannerText(many.failed)).toBe('2 capas no cargaron');
  });

  it('does NOT call a degraded raster source a layer that "no cargó"', () => {
    const health = buildLayerHealth({ raster_tiles: { degradedSourceIds: ['dem-tiles'] } });

    expect(buildHealthBannerText(health.failed)).toBe(rasterTilesMessage(1));
    expect(buildHealthBannerText(health.failed)).not.toMatch(/no cargó/);
  });

  it('reports both kinds when they coexist', () => {
    const health = buildLayerHealth({
      basins: { error: 'boom' },
      raster_tiles: { degradedSourceIds: ['dem-tiles', 'gee-tiles'] },
    });

    expect(buildHealthBannerText(health.failed)).toBe(`1 capa no cargó · ${rasterTilesMessage(2)}`);
  });
});

/**
 * B4c fix round (REL-001/RES-001) — the IGN altimetry overlay gets its OWN
 * entry instead of a number inside the anonymous `raster_tiles` aggregate.
 *
 * The aggregate is a transport counter with `reload: null` ("tiles retry
 * themselves on the next pan/zoom") — true for mosaics, false for an
 * `ImageSource`, which fetches once and never again. Folding IGN in there gave
 * the user a count they could not act on for the ONE failure that is actually
 * fixable.
 */
describe('buildLayerHealth · IGN overlay entry', () => {
  const IGN_SOURCE = 'map2d-ign-overlay';

  it('reports the IGN overlay as its own named entry, with a real reload', () => {
    const reload = vi.fn();
    const health = buildLayerHealth({
      ign_overlay: { error: 'ign image source failed', reload },
      raster_tiles: { degradedSourceIds: [IGN_SOURCE] },
      gates: { ignOverlay: true },
    });

    const entry = health.entries.find((item) => item.key === 'ign_overlay');
    expect(entry).toBeDefined();
    expect(entry?.label).toBe('Altimetría IGN');
    expect(entry?.status).toBe('error');
    expect(entry?.message).toBe('No se pudo cargar la altimetría IGN');
    expect(entry?.reload).toBe(reload);

    health.retryAll();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('does NOT count the IGN source twice in the raster aggregate', () => {
    const health = buildLayerHealth({
      ign_overlay: { error: 'boom', reload: () => {} },
      raster_tiles: { degradedSourceIds: [IGN_SOURCE] },
      gates: { ignOverlay: true },
    });

    // The aggregate entry disappears entirely — IGN was its only member.
    expect(health.entries.some((item) => item.key === 'raster_tiles')).toBe(false);
    expect(health.failed).toHaveLength(1);
  });

  it('keeps counting the OTHER degraded sources in the aggregate', () => {
    const health = buildLayerHealth({
      ign_overlay: { error: 'boom', reload: () => {} },
      raster_tiles: { degradedSourceIds: [IGN_SOURCE, 'map2d-dem-raster'] },
      gates: { ignOverlay: true },
    });

    const aggregate = health.entries.find((item) => item.key === 'raster_tiles');
    // 2 degraded sources, 1 promoted out → the aggregate says ONE, not two.
    expect(aggregate?.message).toBe('Los mosaicos de 1 capa están fallando');
    expect(health.failed).toHaveLength(2);
  });

  it('does not swallow the IGN signal when the caller wires no dedicated slot', () => {
    // Back-compat: without the slot there is no dedicated entry, so the id must
    // still reach the aggregate rather than vanish.
    const health = buildLayerHealth({ raster_tiles: { degradedSourceIds: [IGN_SOURCE] } });

    const aggregate = health.entries.find((item) => item.key === 'raster_tiles');
    expect(aggregate?.message).toBe('Los mosaicos de 1 capa están fallando');
  });

  it('produces NO entry while the overlay is switched off (lazy, never mounted)', () => {
    const health = buildLayerHealth({
      ign_overlay: { error: 'boom', reload: () => {} },
      raster_tiles: { degradedSourceIds: [IGN_SOURCE] },
      gates: { ignOverlay: false },
    });

    expect(health.entries.some((item) => item.key === 'ign_overlay')).toBe(false);
    // …and with the dedicated entry gone the id falls back to the aggregate,
    // so the signal is never lost.
    expect(health.entries.some((item) => item.key === 'raster_tiles')).toBe(true);
  });

  it('is healthy (and never in `failed`) when the overlay is on and fine', () => {
    const health = buildLayerHealth({
      ign_overlay: { error: null, reload: () => {} },
      gates: { ignOverlay: true },
    });

    const entry = health.entries.find((item) => item.key === 'ign_overlay');
    expect(entry?.status).toBe('ok');
    expect(health.failed).toEqual([]);
  });

  it('lands in the Base accordion family', () => {
    const health = buildLayerHealth({
      ign_overlay: { error: 'boom', reload: () => {} },
      gates: { ignOverlay: true },
    });

    expect(health.byCategory[LAYER_CATEGORY.BASE]?.key).toBe('ign_overlay');
  });
});
