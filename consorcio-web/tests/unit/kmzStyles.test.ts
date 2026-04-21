/**
 * kmzStyles.test.ts
 *
 * Batch C — Phase 2 [RED] for change `kmz-export-all-layers`.
 *
 * Pins the KML `<Style>` XML contract:
 *   - `webHexToKmlColor` conversion primitive (#RRGGBB[AA] → AABBGGRR).
 *   - Per-geometry style builders (point / line / polygon).
 *   - Top-level `buildKmzStyles(registry)` that dispatches by `geometryHint`.
 *
 * KML encodes colors as `AABBGGRR` (alpha first, BGR reversed). The tests
 * below pin that conversion against concrete hex values — if the Phase 2
 * implementation gets the byte order wrong, colors in Google Earth would
 * render with swapped red/blue channels.
 */

import { describe, expect, it } from 'vitest';

import {
  buildKmzStyles,
  buildLineStyle,
  buildPointStyle,
  buildPolygonStyle,
  webHexToKmlColor,
} from '../../src/lib/kmzExport/kmzStyles';
import {
  KMZ_LAYER_REGISTRY,
  type KmzLayerEntry,
} from '../../src/lib/kmzExport/kmzLayerRegistry';

// ---------------------------------------------------------------------------
// Test fixtures — synthetic entries so tests are independent from registry
// order / color drift. Registry-based tests use `KMZ_LAYER_REGISTRY` directly.
// ---------------------------------------------------------------------------

const POINT_ENTRY: KmzLayerEntry = {
  key: 'test-point',
  label: 'Test Point',
  geometryHint: 'point',
  color: '#1976d2',
  strokeColor: '#ffffff',
};

const LINE_ENTRY: KmzLayerEntry = {
  key: 'test-line',
  label: 'Test Line',
  geometryHint: 'line',
  color: '#d84315',
};

const POLYGON_ENTRY: KmzLayerEntry = {
  key: 'test-polygon',
  label: 'Test Polygon',
  geometryHint: 'polygon',
  color: '#4caf50',
  strokeColor: '#1b5e20',
};

const CATASTRO_ENTRY: KmzLayerEntry = {
  key: 'catastro',
  label: 'Catastro rural',
  geometryHint: 'polygon',
  color: '#8d6e63',
  strokeColor: '#FFFFFF',
};

// ---------------------------------------------------------------------------
// webHexToKmlColor — primitive.
// ---------------------------------------------------------------------------

describe('webHexToKmlColor', () => {
  it('converts #1976d2 → ffd27619 (default alpha ff, BGR reversed)', () => {
    expect(webHexToKmlColor('#1976d2')).toBe('ffd27619');
  });

  it('converts #d84315 → ff1543d8', () => {
    expect(webHexToKmlColor('#d84315')).toBe('ff1543d8');
  });

  it('handles uppercase: #FFEB3B → ff3bebff', () => {
    expect(webHexToKmlColor('#FFEB3B')).toBe('ff3bebff');
  });

  it('applies alphaOverride: #1976d2 + 88 → 88d27619', () => {
    expect(webHexToKmlColor('#1976d2', '88')).toBe('88d27619');
  });

  it('accepts hex without leading # (graceful): 1976d2 → ffd27619', () => {
    expect(webHexToKmlColor('1976d2')).toBe('ffd27619');
  });

  it('preserves embedded alpha from #RRGGBBAA (no override)', () => {
    // #1976d2cc → alpha cc, B=d2, G=76, R=19 → ccd27619
    expect(webHexToKmlColor('#1976d2cc')).toBe('ccd27619');
  });

  it('alphaOverride wins over embedded alpha', () => {
    expect(webHexToKmlColor('#1976d2cc', 'ff')).toBe('ffd27619');
  });

  it('throws on invalid hex (length != 6/8 after strip)', () => {
    expect(() => webHexToKmlColor('#abc')).toThrow(/invalid.*hex/i);
    expect(() => webHexToKmlColor('not-a-hex')).toThrow(/invalid.*hex/i);
    expect(() => webHexToKmlColor('')).toThrow(/invalid.*hex/i);
  });
});

// ---------------------------------------------------------------------------
// buildPointStyle — IconStyle with placemark_circle icon.
// ---------------------------------------------------------------------------

describe('buildPointStyle', () => {
  it('opens with <Style id="<key>-style">', () => {
    const xml = buildPointStyle(POINT_ENTRY);
    expect(xml.startsWith('<Style id="test-point-style">')).toBe(true);
  });

  it('closes with </Style>', () => {
    expect(buildPointStyle(POINT_ENTRY).endsWith('</Style>')).toBe(true);
  });

  it('contains an <IconStyle> block', () => {
    expect(buildPointStyle(POINT_ENTRY)).toContain('<IconStyle>');
    expect(buildPointStyle(POINT_ENTRY)).toContain('</IconStyle>');
  });

  it('<color> matches webHexToKmlColor(entry.color)', () => {
    const xml = buildPointStyle(POINT_ENTRY);
    const expected = webHexToKmlColor(POINT_ENTRY.color);
    expect(xml).toContain(`<color>${expected}</color>`);
  });

  it('references the Google-hosted placemark_circle.png icon', () => {
    expect(buildPointStyle(POINT_ENTRY)).toContain(
      'http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png',
    );
  });
});

// ---------------------------------------------------------------------------
// buildLineStyle — LineStyle only.
// ---------------------------------------------------------------------------

describe('buildLineStyle', () => {
  it('opens with <Style id="<key>-style">', () => {
    expect(buildLineStyle(LINE_ENTRY).startsWith('<Style id="test-line-style">')).toBe(true);
  });

  it('contains a <LineStyle> block with width 3', () => {
    const xml = buildLineStyle(LINE_ENTRY);
    expect(xml).toContain('<LineStyle>');
    expect(xml).toContain('</LineStyle>');
    expect(xml).toContain('<width>3</width>');
  });

  it('<color> matches webHexToKmlColor(entry.color)', () => {
    const xml = buildLineStyle(LINE_ENTRY);
    expect(xml).toContain(`<color>${webHexToKmlColor(LINE_ENTRY.color)}</color>`);
  });

  it('does NOT contain <PolyStyle> or <IconStyle>', () => {
    const xml = buildLineStyle(LINE_ENTRY);
    expect(xml).not.toContain('<PolyStyle>');
    expect(xml).not.toContain('<IconStyle>');
  });
});

// ---------------------------------------------------------------------------
// buildPolygonStyle — LineStyle + PolyStyle, with outline-only catastro.
// ---------------------------------------------------------------------------

describe('buildPolygonStyle', () => {
  it('opens with <Style id="<key>-style">', () => {
    expect(buildPolygonStyle(POLYGON_ENTRY).startsWith('<Style id="test-polygon-style">')).toBe(
      true,
    );
  });

  it('contains BOTH <LineStyle> and <PolyStyle>', () => {
    const xml = buildPolygonStyle(POLYGON_ENTRY);
    expect(xml).toContain('<LineStyle>');
    expect(xml).toContain('</LineStyle>');
    expect(xml).toContain('<PolyStyle>');
    expect(xml).toContain('</PolyStyle>');
  });

  it('polygon fill uses alpha 88 (semi-transparent)', () => {
    const xml = buildPolygonStyle(POLYGON_ENTRY);
    const expectedFill = webHexToKmlColor(POLYGON_ENTRY.color, '88');
    // Fill color lives inside <PolyStyle>.
    const polyStyle = xml.substring(xml.indexOf('<PolyStyle>'), xml.indexOf('</PolyStyle>'));
    expect(polyStyle).toContain(`<color>${expectedFill}</color>`);
  });

  it('stroke uses alpha ff (fully opaque)', () => {
    const xml = buildPolygonStyle(POLYGON_ENTRY);
    const expectedStroke = webHexToKmlColor(POLYGON_ENTRY.strokeColor ?? POLYGON_ENTRY.color, 'ff');
    const lineStyle = xml.substring(xml.indexOf('<LineStyle>'), xml.indexOf('</LineStyle>'));
    expect(lineStyle).toContain(`<color>${expectedStroke}</color>`);
  });

  it('falls back to entry.color for stroke when strokeColor absent', () => {
    const noStroke: KmzLayerEntry = {
      key: 'no-stroke',
      label: 'No stroke',
      geometryHint: 'polygon',
      color: '#4caf50',
    };
    const xml = buildPolygonStyle(noStroke);
    const expected = webHexToKmlColor(noStroke.color, 'ff');
    const lineStyle = xml.substring(xml.indexOf('<LineStyle>'), xml.indexOf('</LineStyle>'));
    expect(lineStyle).toContain(`<color>${expected}</color>`);
  });

  it('catastro: fill alpha is 00 (outline-only)', () => {
    const xml = buildPolygonStyle(CATASTRO_ENTRY);
    const expectedFill = webHexToKmlColor(CATASTRO_ENTRY.color, '00');
    const polyStyle = xml.substring(xml.indexOf('<PolyStyle>'), xml.indexOf('</PolyStyle>'));
    expect(polyStyle).toContain(`<color>${expectedFill}</color>`);
  });

  it('<fill>1</fill> and <outline>1</outline> present inside <PolyStyle> for non-catastro', () => {
    const xml = buildPolygonStyle(POLYGON_ENTRY);
    const polyStyle = xml.substring(xml.indexOf('<PolyStyle>'), xml.indexOf('</PolyStyle>'));
    expect(polyStyle).toContain('<fill>1</fill>');
    expect(polyStyle).toContain('<outline>1</outline>');
  });
});

// ---------------------------------------------------------------------------
// buildKmzStyles — dispatches by geometryHint, emits one style per registry entry.
// ---------------------------------------------------------------------------

describe('buildKmzStyles', () => {
  it('returns a string', () => {
    expect(typeof buildKmzStyles(KMZ_LAYER_REGISTRY)).toBe('string');
  });

  it('emits EXACTLY one <Style id="…"> per registry entry (13 total)', () => {
    const xml = buildKmzStyles(KMZ_LAYER_REGISTRY);
    const styleIdRe = /<Style\s+id="([^"]+)"\s*>/g;
    const matches = [...xml.matchAll(styleIdRe)];
    expect(matches.length).toBe(KMZ_LAYER_REGISTRY.length);
    expect(KMZ_LAYER_REGISTRY.length).toBe(13);
  });

  it('each registry entry key produces a matching <Style id="<key>-style">', () => {
    const xml = buildKmzStyles(KMZ_LAYER_REGISTRY);
    for (const entry of KMZ_LAYER_REGISTRY) {
      expect(xml).toContain(`<Style id="${entry.key}-style">`);
    }
  });

  it('each style id appears EXACTLY once (no duplicates)', () => {
    const xml = buildKmzStyles(KMZ_LAYER_REGISTRY);
    for (const entry of KMZ_LAYER_REGISTRY) {
      const id = `${entry.key}-style`;
      const occurrences = xml.split(`<Style id="${id}">`).length - 1;
      expect(occurrences).toBe(1);
    }
  });

  it('point entries produce <IconStyle> and NOT <LineStyle>/<PolyStyle>', () => {
    const pointOnly = KMZ_LAYER_REGISTRY.filter((e) => e.geometryHint === 'point');
    expect(pointOnly.length).toBeGreaterThan(0);
    for (const entry of pointOnly) {
      const xml = buildPointStyle(entry);
      expect(xml).toContain('<IconStyle>');
      expect(xml).not.toContain('<LineStyle>');
      expect(xml).not.toContain('<PolyStyle>');
    }
  });

  it('line entries produce <LineStyle> ONLY (no IconStyle/PolyStyle)', () => {
    const lineOnly = KMZ_LAYER_REGISTRY.filter((e) => e.geometryHint === 'line');
    expect(lineOnly.length).toBeGreaterThan(0);
    for (const entry of lineOnly) {
      const xml = buildLineStyle(entry);
      expect(xml).toContain('<LineStyle>');
      expect(xml).not.toContain('<IconStyle>');
      expect(xml).not.toContain('<PolyStyle>');
    }
  });

  it('polygon entries produce BOTH <LineStyle> and <PolyStyle> (no IconStyle)', () => {
    const polyOnly = KMZ_LAYER_REGISTRY.filter((e) => e.geometryHint === 'polygon');
    expect(polyOnly.length).toBeGreaterThan(0);
    for (const entry of polyOnly) {
      const xml = buildPolygonStyle(entry);
      expect(xml).toContain('<LineStyle>');
      expect(xml).toContain('<PolyStyle>');
      expect(xml).not.toContain('<IconStyle>');
    }
  });

  it('preserves registry order (first <Style id> matches first registry entry)', () => {
    const xml = buildKmzStyles(KMZ_LAYER_REGISTRY);
    const firstKey = KMZ_LAYER_REGISTRY[0].key;
    const lastKey = KMZ_LAYER_REGISTRY[KMZ_LAYER_REGISTRY.length - 1].key;
    expect(xml.indexOf(`<Style id="${firstKey}-style">`)).toBeLessThan(
      xml.indexOf(`<Style id="${lastKey}-style">`),
    );
  });
});

// ---------------------------------------------------------------------------
// KML well-formed-ness sanity: matched open/close counts.
// ---------------------------------------------------------------------------

describe('buildKmzStyles — well-formed-ness', () => {
  const xml = buildKmzStyles(KMZ_LAYER_REGISTRY);

  const countOccurrences = (source: string, needle: string): number =>
    source.split(needle).length - 1;

  it('every <Style> has a matching </Style>', () => {
    const open = countOccurrences(xml, '<Style ');
    const close = countOccurrences(xml, '</Style>');
    expect(open).toBe(close);
  });

  it('every <LineStyle> has a matching </LineStyle>', () => {
    expect(countOccurrences(xml, '<LineStyle>')).toBe(countOccurrences(xml, '</LineStyle>'));
  });

  it('every <PolyStyle> has a matching </PolyStyle>', () => {
    expect(countOccurrences(xml, '<PolyStyle>')).toBe(countOccurrences(xml, '</PolyStyle>'));
  });

  it('every <IconStyle> has a matching </IconStyle>', () => {
    expect(countOccurrences(xml, '<IconStyle>')).toBe(countOccurrences(xml, '</IconStyle>'));
  });

  it('every <color> has a matching </color>', () => {
    expect(countOccurrences(xml, '<color>')).toBe(countOccurrences(xml, '</color>'));
  });
});
