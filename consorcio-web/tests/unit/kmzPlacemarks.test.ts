/**
 * kmzPlacemarks.test.ts
 *
 * Batch D — Phase 3 Pair 2 [RED] for `kmz-export-all-layers`.
 *
 * Pins the `buildPlacemark(feature, entry, index)` geometry emitter:
 *   - All 6 GeoJSON primitives → KML mapping (Point/LineString/Polygon,
 *     Multi* → `<MultiGeometry>`).
 *   - Polygon holes → multiple `<innerBoundaryIs>`.
 *   - XML entity escape in `<name>` (`&`, `<`, `>`, `"`, `'`).
 *   - Name source priority: `properties.nombre` → `properties.name` →
 *     `${entry.label} ${index + 1}` (Pair 4 extends this test block).
 *   - Escuelas humanization: leading `"Esc. "` → `"Escuela "`.
 *   - Missing geometry → `<Placemark>` with a `<!-- no geometry -->`
 *     comment, NO throw.
 *   - `<styleUrl>#<key>-style</styleUrl>` on every Placemark.
 */

import { describe, expect, it } from 'vitest';
import type { Feature } from 'geojson';

import { buildPlacemark } from '../../src/lib/kmzExport/kmzPlacemarks';
import type { KmzLayerEntry } from '../../src/lib/kmzExport/kmzLayerRegistry';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const POINT_ENTRY: KmzLayerEntry = {
  key: 'escuelas',
  label: 'Escuelas rurales',
  geometryHint: 'point',
  color: '#1976d2',
};
const LINE_ENTRY: KmzLayerEntry = {
  key: 'canales_relevados',
  label: 'Canales relevados',
  geometryHint: 'line',
  color: '#1976d2',
};
const POLY_ENTRY: KmzLayerEntry = {
  key: 'pilar_verde_bpa_historico',
  label: 'BPA histórico',
  geometryHint: 'polygon',
  color: '#2f9e44',
};

function feature(
  geometry: Feature['geometry'] | null,
  properties: Record<string, unknown> = {},
): Feature {
  return { type: 'Feature', properties, geometry } as Feature;
}

// ---------------------------------------------------------------------------
// Geometry dispatch
// ---------------------------------------------------------------------------

describe('buildPlacemark — Point', () => {
  it('emits <Point><coordinates>lng,lat</coordinates></Point>', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62.6, -32.6] },
      { nombre: 'Test Point' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<Point>');
    expect(out).toContain('<coordinates>-62.6,-32.6</coordinates>');
    expect(out).toContain('</Point>');
  });

  it('preserves the explicit Z coordinate when present', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62.6, -32.6, 123] },
      { nombre: 'With altitude' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<coordinates>-62.6,-32.6,123</coordinates>');
  });
});

describe('buildPlacemark — LineString', () => {
  it('emits <LineString><coordinates>space-separated</coordinates></LineString>', () => {
    const f = feature(
      {
        type: 'LineString',
        coordinates: [
          [-62.5, -32.5],
          [-62.6, -32.6],
          [-62.7, -32.7],
        ],
      },
      { nombre: 'Canal 1' },
    );
    const out = buildPlacemark(f, LINE_ENTRY, 0);
    expect(out).toContain('<LineString>');
    expect(out).toContain(
      '<coordinates>-62.5,-32.5 -62.6,-32.6 -62.7,-32.7</coordinates>',
    );
    expect(out).toContain('</LineString>');
  });
});

describe('buildPlacemark — Polygon', () => {
  it('emits <Polygon><outerBoundaryIs><LinearRing><coordinates>…</coordinates></LinearRing></outerBoundaryIs></Polygon> for a simple ring', () => {
    const f = feature(
      {
        type: 'Polygon',
        coordinates: [
          [
            [-62.5, -32.5],
            [-62.6, -32.5],
            [-62.6, -32.6],
            [-62.5, -32.6],
            [-62.5, -32.5],
          ],
        ],
      },
      { nombre: 'Zone 1' },
    );
    const out = buildPlacemark(f, POLY_ENTRY, 0);
    expect(out).toContain('<Polygon>');
    expect(out).toContain('<outerBoundaryIs>');
    expect(out).toContain('<LinearRing>');
    expect(out).toContain('</LinearRing>');
    expect(out).toContain('</outerBoundaryIs>');
    expect(out).toContain('</Polygon>');
    expect(out).not.toContain('<innerBoundaryIs>');
  });

  it('emits <innerBoundaryIs> per additional ring (holes)', () => {
    const f = feature(
      {
        type: 'Polygon',
        coordinates: [
          // outer
          [
            [-62.5, -32.5],
            [-62.7, -32.5],
            [-62.7, -32.7],
            [-62.5, -32.7],
            [-62.5, -32.5],
          ],
          // hole 1
          [
            [-62.55, -32.55],
            [-62.6, -32.55],
            [-62.6, -32.6],
            [-62.55, -32.6],
            [-62.55, -32.55],
          ],
          // hole 2
          [
            [-62.62, -32.62],
            [-62.65, -32.62],
            [-62.65, -32.65],
            [-62.62, -32.65],
            [-62.62, -32.62],
          ],
        ],
      },
      { nombre: 'Donut' },
    );
    const out = buildPlacemark(f, POLY_ENTRY, 0);
    const innerCount = (out.match(/<innerBoundaryIs>/g) ?? []).length;
    expect(innerCount).toBe(2);
  });
});

describe('buildPlacemark — Multi geometries wrap in <MultiGeometry>', () => {
  it('MultiPoint wraps multiple <Point> in <MultiGeometry>', () => {
    const f = feature(
      {
        type: 'MultiPoint',
        coordinates: [
          [-62.5, -32.5],
          [-62.6, -32.6],
        ],
      },
      { nombre: 'Cluster' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<MultiGeometry>');
    expect(out).toContain('</MultiGeometry>');
    const pointCount = (out.match(/<Point>/g) ?? []).length;
    expect(pointCount).toBe(2);
  });

  it('MultiLineString wraps multiple <LineString> in <MultiGeometry>', () => {
    const f = feature(
      {
        type: 'MultiLineString',
        coordinates: [
          [
            [-62.5, -32.5],
            [-62.6, -32.6],
          ],
          [
            [-62.7, -32.7],
            [-62.8, -32.8],
          ],
        ],
      },
      { nombre: 'Split' },
    );
    const out = buildPlacemark(f, LINE_ENTRY, 0);
    expect(out).toContain('<MultiGeometry>');
    const lineCount = (out.match(/<LineString>/g) ?? []).length;
    expect(lineCount).toBe(2);
  });

  it('MultiPolygon wraps multiple <Polygon> in <MultiGeometry>', () => {
    const f = feature(
      {
        type: 'MultiPolygon',
        coordinates: [
          [
            [
              [-62.5, -32.5],
              [-62.6, -32.5],
              [-62.6, -32.6],
              [-62.5, -32.5],
            ],
          ],
          [
            [
              [-62.7, -32.7],
              [-62.8, -32.7],
              [-62.8, -32.8],
              [-62.7, -32.7],
            ],
          ],
        ],
      },
      { nombre: 'Two islands' },
    );
    const out = buildPlacemark(f, POLY_ENTRY, 0);
    expect(out).toContain('<MultiGeometry>');
    const polyCount = (out.match(/<Polygon>/g) ?? []).length;
    expect(polyCount).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Name resolution
// ---------------------------------------------------------------------------

describe('buildPlacemark — name source priority', () => {
  it('uses feature.properties.nombre when present', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { nombre: 'From nombre', name: 'From name' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<name>From nombre</name>');
    expect(out).not.toContain('<name>From name</name>');
  });

  it('falls back to feature.properties.name when nombre is absent', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { name: 'Plain name' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<name>Plain name</name>');
  });
});

describe('buildPlacemark — XML entity escape', () => {
  it('escapes the 5 XML entities in <name>', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { nombre: `A & B < C > "D" 'E'` },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    // Expected output uses the 5 XML entities.
    expect(out).toContain(
      '<name>A &amp; B &lt; C &gt; &quot;D&quot; &apos;E&apos;</name>',
    );
  });
});

describe('buildPlacemark — escuelas humanization', () => {
  it('replaces leading "Esc. " with "Escuela " for escuelas entry', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { nombre: 'Esc. San Martin' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<name>Escuela San Martin</name>');
    expect(out).not.toContain('<name>Esc. San Martin</name>');
  });

  it('does NOT humanize a non-escuelas entry', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { nombre: 'Esc. Not a school' },
    );
    const YPF_ENTRY: KmzLayerEntry = {
      key: 'ypf-estacion-bombeo',
      label: 'YPF',
      geometryHint: 'point',
      color: '#ff9800',
    };
    const out = buildPlacemark(f, YPF_ENTRY, 0);
    expect(out).toContain('<name>Esc. Not a school</name>');
  });
});

// ---------------------------------------------------------------------------
// Invalid geometry
// ---------------------------------------------------------------------------

describe('buildPlacemark — invalid geometry', () => {
  it('returns a <Placemark> with a <!-- no geometry --> comment when geometry is null', () => {
    const f = feature(null, { nombre: 'Orphan' });
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<Placemark>');
    expect(out).toContain('<!-- no geometry -->');
    expect(out).not.toContain('<Point>');
  });

  it('returns a <Placemark> with a <!-- no geometry --> comment when coordinates are missing', () => {
    const f = {
      type: 'Feature',
      properties: { nombre: 'Bad' },
      // Note: no `coordinates` — this is an invalid-but-possible GeoJSON shape.
      geometry: { type: 'Point' } as unknown as Feature['geometry'],
    } as Feature;
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<!-- no geometry -->');
  });

  it('does NOT throw on unknown geometry types', () => {
    const f = {
      type: 'Feature',
      properties: { nombre: 'Weird' },
      geometry: { type: 'GeometryCollection', geometries: [] } as unknown as Feature['geometry'],
    } as Feature;
    expect(() => buildPlacemark(f, POINT_ENTRY, 0)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Style URL
// ---------------------------------------------------------------------------

describe('buildPlacemark — <styleUrl>', () => {
  it('carries <styleUrl>#<key>-style</styleUrl> on every Placemark', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { nombre: 'Styled' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<styleUrl>#escuelas-style</styleUrl>');
  });
});

// ---------------------------------------------------------------------------
// Pair 4 — null-name fallback (1-indexed)
// ---------------------------------------------------------------------------

describe('buildPlacemark — null-name fallback (Pair 4)', () => {
  it('uses `${entry.label} ${index+1}` when neither nombre nor name is present', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { otherProp: 'whatever' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<name>Escuelas rurales 1</name>');
  });

  it('is 1-indexed — index 3 → "{label} 4"', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { otherProp: 'whatever' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 3);
    expect(out).toContain('<name>Escuelas rurales 4</name>');
  });

  it('falls back on empty-string nombre', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { nombre: '' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<name>Escuelas rurales 1</name>');
  });

  it('falls back on empty-string name', () => {
    const f = feature(
      { type: 'Point', coordinates: [-62, -32] },
      { name: '' },
    );
    const out = buildPlacemark(f, POINT_ENTRY, 0);
    expect(out).toContain('<name>Escuelas rurales 1</name>');
  });

  it('falls back when properties is missing altogether', () => {
    const f = { type: 'Feature', properties: null, geometry: { type: 'Point', coordinates: [-62, -32] } } as Feature;
    const out = buildPlacemark(f, POINT_ENTRY, 2);
    expect(out).toContain('<name>Escuelas rurales 3</name>');
  });
});
