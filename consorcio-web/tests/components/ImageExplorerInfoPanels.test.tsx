/**
 * ImageExplorerInfoPanels.test.tsx — the frontend half of the extreme-rainfall
 * catalog contract (lluvia-eventos-extremos, slice B2c).
 *
 * The change's headline success criterion is **zero frontend changes**: the
 * backend stops serving three module literals and starts serving a catalog of
 * ~180 rows, and the picker is supposed to keep working untouched. Until this
 * file existed, that claim was defended by nothing — the directory had no test
 * at all, so "it still works" was an assertion about code nobody executed.
 *
 * Four properties carry the claim, and each one fails SILENTLY if it breaks:
 *
 *  1. **`isHistoricFlood` tolerates the catalog's extra keys** and requires
 *     `id` / `name` / `date` as strings (`useImageExplorerController.tsx:48-56`).
 *     It `.filter()`s — a record it rejects does not error, it VANISHES. A
 *     nameless detected row is therefore an invisible defect, not a cosmetic
 *     one, which is why the backend synthesizes a name at read time (D10).
 *  2. **The severity palette is actually reached** (D9).
 *     `ImageExplorerInfoPanels.tsx:214-225` styles exactly `alta` -> red and
 *     `media` -> orange; EVERYTHING else falls to the palest yellow available.
 *     That is the whole reason the wire severity is the remapped
 *     `extrema -> alta` / `alta -> media` rather than the true tier: serving
 *     `extrema` on the wire paints the most extreme events the faintest colour
 *     in the palette.
 *  3. **`description` renders unconditionally** (`:228`), so the synthesized
 *     Spanish description — CHIRPS disclosure sentence included — reaches the
 *     DOM, and an empty one renders an empty line rather than throwing.
 *  4. **The restore path's `days_buffer` ceiling** (`typeGuards.ts:405-411`)
 *     accepts the curated seed's `30` and refuses `31`. The backend clamps to
 *     [1, 30] because of this guard; the ceiling is pinned on both sides.
 *
 * CROSS-TREE FIXTURE PIN (task 6.4). The three `SERVED_*` fixtures below are
 * copied VERBATIM from the payload the backend contract test asserts, and a
 * pytest reads this file's source and compares their key sets against the
 * records the router actually serves
 * (`gee-backend/tests/new/geo/rainfall/test_rainfall_catalog_serving.py`,
 * section "B2c"). A hand-written frontend fixture drifts from the backend that
 * feeds it, silently, and the whole point of these tests is that they run
 * against the SERVED shape rather than against a shape a frontend developer
 * imagined. The delimiters below are load-bearing: the pytest parses them.
 */

import { MantineProvider } from '@mantine/core';
import { render, renderHook, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// `useImageExplorerController` pulls in `useImageExplorerMap`, which imports
// maplibre-gl at module scope. The map is not under test here and happy-dom has
// no WebGL, so the module is stubbed rather than the hook being reshaped.
vi.mock('maplibre-gl', () => ({ default: { Map: vi.fn() } }));

const apiFetch = vi.fn();
vi.mock('../../src/lib/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

import { ImageExplorerInfoPanels } from '../../src/components/admin/images/ImageExplorerInfoPanels';
import { useImageExplorerController } from '../../src/components/admin/images/useImageExplorerController';
import { isValidSelectedImage } from '../../src/lib/typeGuards';

// ===========================================================================
// The served records, copied verbatim from the B2a contract test's payload.
// ===========================================================================

// >>> SERVED_DETECTED
const SERVED_DETECTED = {
  id: 'ext_20150312',
  name: 'Lluvia extrema 12-15 de marzo 2015',
  date: '2015-03-14',
  description:
    'Ventanas que superaron el umbral: d3 (p99.8). Percentil maximo 99.8 sobre 1991-2025. CHIRPS ordena de forma relativa: no es una medicion en milimetros.',
  severity: 'alta',
  tier: 'extrema',
  provenance: 'detected',
  curated: false,
  confirmation: null,
  confirmed_by: null,
  start_date: '2015-03-12',
  end_date: '2015-03-15',
  peak_date: '2015-03-14',
  max_percentile: 99.81,
  fired_windows: {
    d3: { peak_end: '2015-03-14', peak_total_mm: 180.0, percentile: 99.81 },
  },
  clipped_at_span_end: false,
  imagery_candidate: true,
  imagery_note: 'Candidato a imagen satelital: Sentinel-2 y Sentinel-1 disponibles.',
  dataset_disclosure:
    'CHIRPS ordena de forma relativa y acota la ventana de busqueda satelital; no es una medicion en milimetros.',
};
// <<< SERVED_DETECTED

// >>> SERVED_CURATED_UNCONFIRMED
const SERVED_CURATED_UNCONFIRMED = {
  id: 'mar_2015',
  name: 'Inundacion Marzo 2015',
  date: '2015-03-15',
  description: 'Evento historico para revisar con Landsat 8/Landsat 7 y Sentinel-1',
  severity: 'alta',
  tier: null,
  provenance: 'curated',
  curated: true,
  confirmation: 'not_confirmed',
  confirmed_by: null,
  confirmation_label: 'curated, not detector-confirmed',
  start_date: '2015-03-15',
  end_date: '2015-03-15',
  peak_date: null,
  max_percentile: null,
  fired_windows: null,
  imagery_candidate: true,
  imagery_note: 'Candidato a imagen satelital: Sentinel-2 y Sentinel-1 disponibles.',
  dataset_disclosure:
    'CHIRPS ordena de forma relativa y acota la ventana de busqueda satelital; no es una medicion en milimetros.',
  sensor: 'landsat8',
  max_cloud: 80,
  days_buffer: 30,
};
// <<< SERVED_CURATED_UNCONFIRMED

// >>> SERVED_CURATED_CONFIRMED
const SERVED_CURATED_CONFIRMED = {
  id: 'feb_2017',
  name: 'Inundacion Febrero 2017',
  date: '2017-02-20',
  description: '',
  severity: 'alta',
  tier: 'alta',
  provenance: 'detected',
  curated: true,
  confirmation: 'detector_confirmed',
  confirmed_by: 'alt_20170218',
  confirmation_label:
    'curated, detector-confirmed by alt_20170218 (1 day(s) from the curated date)',
  start_date: '2017-02-20',
  end_date: '2017-02-20',
  peak_date: '2017-02-18',
  max_percentile: 99.81,
  fired_windows: {
    d3: { peak_end: '2017-02-18', peak_total_mm: 180.0, percentile: 99.81 },
  },
  imagery_candidate: true,
  imagery_note: 'Ventana dorada: Sentinel-2 (5 dias) + Sentinel-1 (6 dias).',
  dataset_disclosure:
    'CHIRPS ordena de forma relativa y acota la ventana de busqueda satelital; no es una medicion en milimetros.',
  sensor: 'landsat8',
  confirmation_offset_days: 1,
  confirmation_tolerance_days: 3,
};
// <<< SERVED_CURATED_CONFIRMED

// ===========================================================================
// Harness
// ===========================================================================

type FloodCard = { id: string; name: string; date: string; description: string; severity: string };

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

/** Every prop the panel needs, with the historic-floods list left to the caller. */
function renderPanels(historicFloods: FloodCard[]) {
  return render(
    <ImageExplorerInfoPanels
      result={null}
      isCurrentImageSelected={false}
      comparison={null}
      onSelectImage={() => {}}
      onSetLeftImage={() => {}}
      onSetRightImage={() => {}}
      historicFloods={historicFloods}
      onLoadHistoricFlood={() => {}}
      selectedImage={null}
      onClearSelectedImage={() => {}}
      comparisonReady={false}
      onClearComparison={() => {}}
      sensor="sentinel2"
      scenes={[]}
      selectedSceneId={null}
      onSelectScene={() => {}}
      compositionMode="scene"
    />,
    { wrapper }
  );
}

/** The colour Mantine resolved for a badge, read off the CSS variable its root
 * carries — the only place `color="red"` is observable in the rendered DOM. */
function badgeColour(label: string): string {
  const root = screen.getByText(label).parentElement;
  if (!root) throw new Error(`badge "${label}" has no root element`);
  return root.style.getPropertyValue('--badge-bg');
}

/** Drive the REAL `isHistoricFlood` filter: it is module-private, so the only
 * honest way to exercise it is through the controller that owns it. A test that
 * re-implemented the predicate here would pin the copy, not the code. */
async function floodsAfterTheGuard(floods: unknown[]): Promise<unknown[]> {
  apiFetch.mockImplementation((url: string) =>
    url.includes('historic-floods') ? Promise.resolve({ floods }) : Promise.resolve([])
  );
  const { result } = renderHook(() => useImageExplorerController(), { wrapper });
  await waitFor(() => expect(apiFetch).toHaveBeenCalled());
  await waitFor(() => expect(result.current.loadingDates).toBe(false));
  return result.current.historicFloods;
}

beforeEach(() => {
  apiFetch.mockReset();
});

// ===========================================================================
// 6.1 -- D10: the catalog record survives `isHistoricFlood`, extras and all
// ===========================================================================

describe('isHistoricFlood against the served catalog record', () => {
  it('accepts a synthesized detected record and carries its extra catalog keys through', async () => {
    const kept = (await floodsAfterTheGuard([SERVED_DETECTED])) as Record<string, unknown>[];

    expect(kept).toHaveLength(1);
    // Extra-key TOLERANCE is what makes "zero frontend change" true. It is
    // currently true by accident of implementation (a structural predicate,
    // not an exact-shape one); this is the assertion that makes it a contract.
    for (const extra of [
      'tier',
      'provenance',
      'curated',
      'confirmation',
      'max_percentile',
      'fired_windows',
      'clipped_at_span_end',
      'imagery_candidate',
      'imagery_note',
      'dataset_disclosure',
    ]) {
      expect(kept[0]).toHaveProperty(extra);
    }
  });

  it('accepts both curated shapes, confirmed and not', async () => {
    const kept = await floodsAfterTheGuard([
      SERVED_CURATED_UNCONFIRMED,
      SERVED_CURATED_CONFIRMED,
    ]);

    expect((kept as FloodCard[]).map((f) => f.id)).toEqual(['mar_2015', 'feb_2017']);
  });

  it('drops a record with no name SILENTLY — the invisible failure mode', async () => {
    const { name: _dropped, ...nameless } = SERVED_DETECTED;

    const kept = await floodsAfterTheGuard([nameless, SERVED_CURATED_UNCONFIRMED]);

    // No throw, no error state, no console noise: the card is simply not there.
    // This is the frontend half of "a nameless detected row is an INVISIBLE
    // defect" — the backend half is `synthesize_name` at read time (D10).
    expect((kept as FloodCard[]).map((f) => f.id)).toEqual(['mar_2015']);
  });

  it('drops a record whose id or date is not a string', async () => {
    const kept = await floodsAfterTheGuard([
      { ...SERVED_DETECTED, id: 42 },
      { ...SERVED_DETECTED, id: 'no_date', date: null },
      SERVED_DETECTED,
    ]);

    expect((kept as FloodCard[]).map((f) => f.id)).toEqual(['ext_20150312']);
  });
});

// ===========================================================================
// 6.1, second half -- the restore path's `days_buffer` ceiling
// ===========================================================================

describe('typeGuards restore path against the catalog record', () => {
  const restored = (overrides: Record<string, unknown>) => ({
    tile_url: 'https://earthengine.googleapis.com/v1/tiles/{z}/{x}/{y}',
    target_date: SERVED_CURATED_UNCONFIRMED.date,
    sensor: 'Landsat 8',
    visualization: 'rgb',
    visualization_description: 'Color natural',
    collection: 'LANDSAT/LC08/C02/T1_L2',
    images_count: 3,
    selected_at: '2026-08-26T12:00:00.000Z',
    flood_info: {
      id: SERVED_CURATED_UNCONFIRMED.id,
      name: SERVED_CURATED_UNCONFIRMED.name,
      description: SERVED_CURATED_UNCONFIRMED.description,
      severity: SERVED_CURATED_UNCONFIRMED.severity,
    },
    ...overrides,
  });

  it('accepts the curated seed buffer of 30 — the ceiling the backend clamps to', () => {
    expect(SERVED_CURATED_UNCONFIRMED.days_buffer).toBe(30);
    expect(isValidSelectedImage(restored({ days_buffer: 30 }))).toBe(true);
  });

  it('refuses 31 — which is why the served payload is clamped to [1, 30]', () => {
    expect(isValidSelectedImage(restored({ days_buffer: 31 }))).toBe(false);
    expect(isValidSelectedImage(restored({ days_buffer: 0 }))).toBe(false);
  });

  it('tolerates catalog keys it does not know about', () => {
    expect(
      isValidSelectedImage(
        restored({
          days_buffer: 30,
          tier: SERVED_DETECTED.tier,
          provenance: SERVED_DETECTED.provenance,
          imagery_candidate: SERVED_DETECTED.imagery_candidate,
          dataset_disclosure: SERVED_DETECTED.dataset_disclosure,
        })
      )
    ).toBe(true);
  });
});

// ===========================================================================
// 6.2 -- D9: the badge palette the wire severity is remapped FOR
// ===========================================================================

describe('the historic-flood severity palette', () => {
  const card = (severity: string, id: string): FloodCard => ({
    id,
    name: `card ${id}`,
    date: '2015-03-14',
    description: 'x',
    severity,
  });

  it('paints the wire severities the catalog actually emits', () => {
    renderPanels([card('alta', 'a'), card('media', 'm')]);

    expect(badgeColour('alta')).toBe('var(--mantine-color-red-filled)');
    expect(badgeColour('media')).toBe('var(--mantine-color-orange-filled)');
  });

  it('falls to the palest yellow for the TRUE tier — the reason the wire domain is not widened', () => {
    // D9's entire argument, executed: if the backend ever served the tier
    // verbatim, the most extreme events in the catalog would render in the
    // faintest colour the component knows, with nothing failing anywhere.
    renderPanels([card('extrema', 'e')]);

    expect(badgeColour('extrema')).toBe('var(--mantine-color-yellow-filled)');
  });

  it('remaps the served record itself, not a hand-made one', () => {
    expect(SERVED_DETECTED.tier).toBe('extrema');
    expect(SERVED_DETECTED.severity).toBe('alta');

    renderPanels([SERVED_DETECTED as FloodCard]);

    expect(badgeColour('alta')).toBe('var(--mantine-color-red-filled)');
  });
});

// ===========================================================================
// 6.3 -- D10: the synthesized description reaches the DOM
// ===========================================================================

describe('the historic-flood card body', () => {
  it('renders the synthesized name, description and date', () => {
    renderPanels([SERVED_DETECTED as FloodCard]);

    expect(screen.getByText(SERVED_DETECTED.name)).toBeInTheDocument();
    expect(screen.getByText(SERVED_DETECTED.description)).toBeInTheDocument();
    // The CHIRPS sentence is not decoration: R5 requires every record to
    // disclose that CHIRPS ranks rather than measures, and the picker card is
    // where an operator reads it.
    expect(SERVED_DETECTED.description).toContain('CHIRPS');
    expect(screen.getByText(SERVED_DETECTED.date)).toBeInTheDocument();
  });

  it('renders an empty line rather than failing when the description is empty', () => {
    // `feb_2017` is served with `description: ""` — the curated payload carries
    // no description and `_curated_record` defaults it to the empty string.
    // `:228` renders it unconditionally, so this is a blank line, not a crash.
    expect(SERVED_CURATED_CONFIRMED.description).toBe('');

    renderPanels([SERVED_CURATED_CONFIRMED as FloodCard]);

    expect(screen.getByText(SERVED_CURATED_CONFIRMED.name)).toBeInTheDocument();
    expect(screen.getByText(SERVED_CURATED_CONFIRMED.date)).toBeInTheDocument();
  });

  it('renders one card per served record at catalog scale', () => {
    // BL-PICKER-AT-CATALOG-VOLUME, pinned rather than hidden: the `SimpleGrid`
    // was built for three cards and renders all ~180 without complaint. That is
    // the backlog item, and this assertion is what makes it measurable.
    const many = Array.from({ length: 30 }, (_, i) => card(i));

    renderPanels(many);

    expect(screen.getAllByText(/^card /)).toHaveLength(30);
  });

  function card(i: number): FloodCard {
    return {
      id: `ext_2015031${i}`,
      name: `card ${i}`,
      date: '2015-03-14',
      description: 'x',
      severity: i % 2 === 0 ? 'alta' : 'media',
    };
  }
});
