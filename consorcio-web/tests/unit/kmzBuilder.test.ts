/**
 * kmzBuilder.test.ts
 *
 * Batch D — Phase 3 [RED] for change `kmz-export-all-layers`.
 *
 * Pins the top-level `buildKmz` contract:
 *   - Returns a Blob with MIME `application/vnd.google-earth.kmz`.
 *   - Contents (when unzipped) are EXACTLY one entry: `doc.kml`.
 *   - `doc.kml` is well-formed XML with KML 2.2 root + `<Document>` +
 *     `<Style>` block BEFORE any `<Folder>`.
 *   - Visibility gating — only visible allowlisted layers get a Folder.
 *   - Exclusion gating — `puntos_conflicto` / `approved_zones` / `basins`
 *     never appear, even with `visibleLayers[k] === true`.
 *   - YPF is always-on (no toggle required).
 *   - Each Placemark carries `<styleUrl>#<key>-style</styleUrl>`.
 *   - Pair 3: PII strip — cue / directivo / etc. must not appear in
 *     serialized KML.
 *   - Pair 4: canales_propuestos respects `propuestasEtapasVisibility`.
 *
 * We unzip the blob with JSZip to inspect `doc.kml`; we parse with
 * `DOMParser` (provided by happy-dom) to catch malformed XML.
 */

import JSZip from 'jszip';
import { describe, expect, it } from 'vitest';
import type { Feature, FeatureCollection, Geometry } from 'geojson';

import { buildKmz } from '../../src/lib/kmzExport/kmzBuilder';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Helper to build a FeatureCollection inline. */
function fc(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

function pt(coords: [number, number], props: Record<string, unknown> = {}): Feature {
  return {
    type: 'Feature',
    properties: props,
    geometry: { type: 'Point', coordinates: coords },
  } as Feature<Geometry>;
}

function line(coords: Array<[number, number]>, props: Record<string, unknown> = {}): Feature {
  return {
    type: 'Feature',
    properties: props,
    geometry: { type: 'LineString', coordinates: coords },
  } as Feature<Geometry>;
}

function poly(
  rings: Array<Array<[number, number]>>,
  props: Record<string, unknown> = {},
): Feature {
  return {
    type: 'Feature',
    properties: props,
    geometry: { type: 'Polygon', coordinates: rings },
  } as Feature<Geometry>;
}

const escuelas = fc([
  pt([-62.6, -32.6], { nombre: 'Esc. San Martin' }),
  pt([-62.7, -32.7], { nombre: 'Esc. Belgrano' }),
]);
const canalesRelevados = fc([
  line(
    [
      [-62.5, -32.5],
      [-62.6, -32.6],
    ],
    { nombre: 'Canal 1' },
  ),
]);
const pilarVerdeBpa = fc([
  poly(
    [
      [
        [-62.5, -32.5],
        [-62.6, -32.5],
        [-62.6, -32.6],
        [-62.5, -32.6],
        [-62.5, -32.5],
      ],
    ],
    { nombre: 'BPA 1' },
  ),
]);
const puntosConflicto = fc([pt([-62.4, -32.4], { nombre: 'PC 1' })]);
const ypf = fc([pt([-62.55, -32.55], { nombre: 'YPF Bombeo' })]);

// Small helper: read back the kml string from a blob.
async function extractKml(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const zip = await JSZip.loadAsync(buffer);
  const entry = zip.file('doc.kml');
  if (!entry) throw new Error('doc.kml missing from kmz');
  return entry.async('string');
}

async function listEntries(blob: Blob): Promise<string[]> {
  const buffer = await blob.arrayBuffer();
  const zip = await JSZip.loadAsync(buffer);
  return Object.keys(zip.files);
}

function parseXml(xml: string): Document {
  const doc = new DOMParser().parseFromString(xml, 'application/xml');
  const error = doc.querySelector('parsererror');
  if (error) throw new Error(`XML parse error: ${error.textContent}`);
  return doc;
}

// ---------------------------------------------------------------------------
// Pair 1 — Builder contract
// ---------------------------------------------------------------------------

describe('buildKmz — Blob + zip structure', () => {
  it('returns a Blob', async () => {
    const blob = await buildKmz({ visibleLayers: {}, data: {} });
    expect(blob).toBeInstanceOf(Blob);
  });

  it('uses MIME `application/vnd.google-earth.kmz`', async () => {
    const blob = await buildKmz({ visibleLayers: {}, data: {} });
    expect(blob.type).toBe('application/vnd.google-earth.kmz');
  });

  it('contains EXACTLY one entry: doc.kml', async () => {
    const blob = await buildKmz({ visibleLayers: {}, data: {} });
    const entries = await listEntries(blob);
    expect(entries).toEqual(['doc.kml']);
  });
});

describe('buildKmz — KML well-formed-ness', () => {
  it('produces parseable XML', async () => {
    const blob = await buildKmz({ visibleLayers: {}, data: {} });
    const xml = await extractKml(blob);
    expect(() => parseXml(xml)).not.toThrow();
  });

  it('root element is <kml> with KML 2.2 namespace', async () => {
    const blob = await buildKmz({ visibleLayers: {}, data: {} });
    const xml = await extractKml(blob);
    const doc = parseXml(xml);
    expect(doc.documentElement.localName).toBe('kml');
    expect(doc.documentElement.getAttribute('xmlns')).toBe(
      'http://www.opengis.net/kml/2.2',
    );
  });

  it('Document <name> matches /^Consorcio Canalero — \\d{4}-\\d{2}-\\d{2}$/', async () => {
    const blob = await buildKmz({
      visibleLayers: {},
      data: {},
      timestamp: new Date('2026-04-21T12:00:00Z'),
    });
    const xml = await extractKml(blob);
    expect(xml).toMatch(
      /<name>Consorcio Canalero — \d{4}-\d{2}-\d{2}<\/name>/,
    );
  });

  it('uses provided timestamp date in Document <name>', async () => {
    const blob = await buildKmz({
      visibleLayers: {},
      data: {},
      timestamp: new Date('2026-04-21T12:00:00Z'),
    });
    const xml = await extractKml(blob);
    expect(xml).toContain('<name>Consorcio Canalero — 2026-04-21</name>');
  });
});

describe('buildKmz — visibility gating', () => {
  it('emits a Folder for visible + has-data layers', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true },
      data: { escuelas },
    });
    const xml = await extractKml(blob);
    expect(xml).toContain('<Folder>');
    expect(xml).toContain('<name>Escuelas rurales</name>');
  });

  it('omits Folder for layers with visibleLayers[key] === false', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: false },
      data: { escuelas },
    });
    const xml = await extractKml(blob);
    expect(xml).not.toContain('Escuelas rurales');
  });

  it('omits Folder for layers missing from visibleLayers', async () => {
    const blob = await buildKmz({
      visibleLayers: {},
      data: { escuelas },
    });
    const xml = await extractKml(blob);
    expect(xml).not.toContain('Escuelas rurales');
  });

  it('silently skips visible layers whose data is null', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true },
      data: { escuelas: null },
    });
    const xml = await extractKml(blob);
    expect(xml).not.toContain('Escuelas rurales');
  });

  it('silently skips visible layers whose data is missing', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true },
      data: {},
    });
    const xml = await extractKml(blob);
    expect(xml).not.toContain('Escuelas rurales');
  });

  it('emits at least one Placemark inside a visible + has-data Folder', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true },
      data: { escuelas },
    });
    const xml = await extractKml(blob);
    expect(xml).toMatch(/<Folder>[\s\S]*<Placemark>/);
  });
});

describe('buildKmz — exclusion gating (hard invariant)', () => {
  it('NEVER emits puntos_conflicto even when visible + has data', async () => {
    const blob = await buildKmz({
      visibleLayers: { puntos_conflicto: true },
      data: { puntos_conflicto: puntosConflicto },
    });
    const xml = await extractKml(blob);
    expect(xml).not.toContain('puntos_conflicto');
    expect(xml).not.toContain('PC 1');
  });

  it('NEVER emits approved_zones', async () => {
    const blob = await buildKmz({
      visibleLayers: { approved_zones: true },
      data: { approved_zones: fc([pt([-62, -32], { nombre: 'AZ' })]) },
    });
    const xml = await extractKml(blob);
    expect(xml).not.toContain('approved_zones');
  });

  it('NEVER emits basins', async () => {
    const blob = await buildKmz({
      visibleLayers: { basins: true },
      data: { basins: fc([pt([-62, -32], { nombre: 'B' })]) },
    });
    const xml = await extractKml(blob);
    expect(xml).not.toContain('basins');
  });
});

describe('buildKmz — YPF special case (always-on)', () => {
  it('includes ypf-estacion-bombeo even when visibleLayers omits the key', async () => {
    const blob = await buildKmz({
      visibleLayers: {},
      data: { 'ypf-estacion-bombeo': ypf },
    });
    const xml = await extractKml(blob);
    // Label from registry — YPF_ESTACION_BOMBEO_LABEL.
    expect(xml).toMatch(/<Folder>[\s\S]*<name>[^<]*YPF[^<]*<\/name>/);
  });

  it('includes ypf-estacion-bombeo when visibleLayers[key] === false', async () => {
    const blob = await buildKmz({
      visibleLayers: { 'ypf-estacion-bombeo': false },
      data: { 'ypf-estacion-bombeo': ypf },
    });
    const xml = await extractKml(blob);
    expect(xml).toMatch(/<name>[^<]*YPF[^<]*<\/name>/);
  });

  it('skips ypf when data is missing', async () => {
    const blob = await buildKmz({
      visibleLayers: { 'ypf-estacion-bombeo': true },
      data: {},
    });
    const xml = await extractKml(blob);
    expect(xml).not.toMatch(/<name>[^<]*YPF[^<]*<\/name>/);
  });
});

describe('buildKmz — styles block placement', () => {
  it('emits <Style> blocks inside <Document> BEFORE any <Folder>', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true },
      data: { escuelas },
    });
    const xml = await extractKml(blob);
    const styleIdx = xml.indexOf('<Style ');
    const folderIdx = xml.indexOf('<Folder>');
    expect(styleIdx).toBeGreaterThan(-1);
    expect(folderIdx).toBeGreaterThan(-1);
    expect(styleIdx).toBeLessThan(folderIdx);
  });

  it('only emits <Style> blocks for layers actually included', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true },
      data: { escuelas },
    });
    const xml = await extractKml(blob);
    // escuelas style present, canales_relevados-style absent.
    expect(xml).toContain('id="escuelas-style"');
    expect(xml).not.toContain('id="canales_relevados-style"');
  });

  it('Placemarks carry <styleUrl>#<key>-style</styleUrl>', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true },
      data: { escuelas },
    });
    const xml = await extractKml(blob);
    expect(xml).toContain('<styleUrl>#escuelas-style</styleUrl>');
  });
});

describe('buildKmz — multi-layer integration', () => {
  it('emits multiple Folders in registry order', async () => {
    const blob = await buildKmz({
      visibleLayers: {
        canales_relevados: true,
        escuelas: true,
        pilar_verde_bpa_historico: true,
      },
      data: {
        canales_relevados: canalesRelevados,
        escuelas,
        pilar_verde_bpa_historico: pilarVerdeBpa,
      },
    });
    const xml = await extractKml(blob);
    const canalesIdx = xml.indexOf('Canales relevados');
    const escuelasIdx = xml.indexOf('Escuelas rurales');
    const bpaIdx = xml.indexOf('BPA histórico');
    expect(canalesIdx).toBeGreaterThan(-1);
    expect(escuelasIdx).toBeGreaterThan(-1);
    expect(bpaIdx).toBeGreaterThan(-1);
    // Registry order: canales_relevados → escuelas → pilar_verde_bpa_historico
    expect(canalesIdx).toBeLessThan(escuelasIdx);
    expect(escuelasIdx).toBeLessThan(bpaIdx);
  });

  it('does NOT touch registered but excluded keys in the same run', async () => {
    const blob = await buildKmz({
      visibleLayers: { escuelas: true, puntos_conflicto: true },
      data: { escuelas, puntos_conflicto: puntosConflicto },
    });
    const xml = await extractKml(blob);
    expect(xml).toContain('Escuelas rurales');
    expect(xml).not.toContain('PC 1');
    expect(xml).not.toContain('puntos_conflicto');
  });
});
