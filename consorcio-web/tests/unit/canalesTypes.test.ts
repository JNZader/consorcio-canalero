/**
 * canalesTypes.test.ts
 *
 * Type contracts for Pilar Azul (Canales) — validates that the TypeScript types
 * in `src/types/canales.ts` match the actual shape of the static assets under
 * `public/capas/canales/`.
 *
 * Pattern mirrors `tests/unit/pilarVerdeTypes.test.ts` — the test is
 * primarily type-level (tsc pins) + a small runtime shape check against a
 * hand-pinned fixture that mirrors the real index.json + geojson metadata.
 */

import { describe, expect, it } from 'vitest';

import type {
  CanalFeature,
  CanalFeatureProperties,
  CanalMetadata,
  CanalesData,
  CanalesFeatureCollection,
  Etapa,
  IndexFile,
} from '../../src/types/canales';
import { ALL_ETAPAS } from '../../src/types/canales';

import indexSample from '../fixtures/canales/indexSample.json';
import propuestasSample from '../fixtures/canales/propuestasSample.json';
import relevadosSample from '../fixtures/canales/relevadosSample.json';

describe('canales types · Etapa union + ALL_ETAPAS', () => {
  it('ALL_ETAPAS is the 5-item canonical list in priority-descending order', () => {
    expect(ALL_ETAPAS).toEqual([
      'Alta',
      'Media-Alta',
      'Media',
      'Opcional',
      'Largo plazo',
    ]);
    expect(ALL_ETAPAS).toHaveLength(5);
  });

  it('Etapa type accepts each canonical value (type-level pin via assignment)', () => {
    // tsc will fail this file if the union drifts — the pin is the assignment.
    const a: Etapa = 'Alta';
    const ma: Etapa = 'Media-Alta';
    const m: Etapa = 'Media';
    const o: Etapa = 'Opcional';
    const lp: Etapa = 'Largo plazo';
    expect([a, ma, m, o, lp]).toEqual(ALL_ETAPAS);
  });
});

describe('canales types · IndexFile shape', () => {
  it('indexSample fixture matches IndexFile structure', () => {
    const index = indexSample as unknown as IndexFile;

    expect(index.schema_version).toBe('1.0');
    expect(typeof index.generated_at).toBe('string');
    expect(Array.isArray(index.relevados)).toBe(true);
    expect(Array.isArray(index.propuestas)).toBe(true);

    // counts shape
    expect(index.counts.relevados).toBe(2);
    expect(index.counts.propuestas).toBe(3);
    expect(index.counts.total).toBe(5);

    // relevados (no prioridad on relevados per spec)
    const r0: CanalMetadata = index.relevados[0]!;
    expect(r0.id).toBe('canal-ne-sin-intervencion');
    expect(r0.codigo).toBeNull();
    expect(r0.featured).toBe(false);
    expect(typeof r0.longitud_m).toBe('number');

    // propuestas include prioridad
    const p0 = index.propuestas[0]!;
    expect(p0.id).toBe('n3-tramo-faltante-de-interconexion');
    expect(p0.prioridad).toBe('Alta');
    expect(p0.featured).toBe(true);
  });

  it('schema_version literal narrows to "1.0"', () => {
    const index = indexSample as unknown as IndexFile;
    // TypeScript narrows this — runtime assertion mirrors the static pin.
    const v: '1.0' = index.schema_version;
    expect(v).toBe('1.0');
  });
});

describe('canales types · Feature + FeatureCollection', () => {
  it('relevadosSample matches CanalesFeatureCollection', () => {
    const fc = relevadosSample as unknown as CanalesFeatureCollection;
    expect(fc.type).toBe('FeatureCollection');
    expect(fc.features).toHaveLength(2);
    const f0: CanalFeature = fc.features[0]!;
    const props: CanalFeatureProperties = f0.properties;
    expect(props.id).toBe('canal-ne-sin-intervencion');
    expect(props.estado).toBe('relevado');
    expect(props.prioridad).toBeNull();
    expect(f0.geometry.type).toBe('LineString');
    expect(Array.isArray(f0.geometry.coordinates)).toBe(true);
    expect(f0.geometry.coordinates[0]).toHaveLength(2);
  });

  it('propuestasSample matches CanalesFeatureCollection with prioridad set', () => {
    const fc = propuestasSample as unknown as CanalesFeatureCollection;
    expect(fc.features).toHaveLength(3);
    const alta = fc.features[0]!;
    expect(alta.properties.estado).toBe('propuesto');
    expect(alta.properties.prioridad).toBe('Alta');
    expect(alta.properties.featured).toBe(true);
    expect(alta.properties.source_style).toBe('prio_Alta');

    const nullPrio = fc.features[2]!;
    expect(nullPrio.properties.prioridad).toBeNull();
  });
});

describe('canales types · CanalesData composite', () => {
  it('CanalesData accepts a typed triple of slots including null slots', () => {
    const data: CanalesData = {
      relevados: relevadosSample as unknown as CanalesFeatureCollection,
      propuestas: propuestasSample as unknown as CanalesFeatureCollection,
      index: indexSample as unknown as IndexFile,
    };
    expect(data.relevados?.features).toHaveLength(2);
    expect(data.propuestas?.features).toHaveLength(3);
    expect(data.index?.counts.total).toBe(5);

    // Null-tolerant shape
    const partial: CanalesData = {
      relevados: null,
      propuestas: null,
      index: null,
    };
    expect(partial.relevados).toBeNull();
  });
});
