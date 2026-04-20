/**
 * pilarVerdeTypes.test.ts
 * Type-level + runtime smoke tests for the frozen Pilar Verde JSON schemas.
 *
 * The intent: ensure the TypeScript types compile against literal samples that
 * mirror the REAL JSON shapes produced by `scripts/etl_pilar_verde` (verified
 * against `consorcio-web/public/data/pilar-verde/*.json` on 2026-04-20).
 *
 * Notes on real-data discrepancies surfaced from inspection (relevant to types):
 *  - `bpa_2025.bpa_total` is emitted as a STRING ("2") in `bpa_enriched.json`.
 *  - `bpa_2025.activa` is `boolean` in `bpa_enriched.json` but `"1"`/`"0"` STRING
 *    in the GeoJSON `bpa_2025.geojson` properties (normalize at hook layer).
 *  - GeoJSON `bpa_2025` properties are FLAT (`eje_persona`, etc.), not nested.
 *  - `agro_aceptada.geojson` features can have `geometry.type === "Polygon"`
 *    OR `"MultiPolygon"`.
 */

import { describe, expect, it } from 'vitest';
import {
  PILAR_VERDE_BPA_YEARS,
  PILAR_VERDE_PRACTICA_KEYS,
} from '../../src/types/pilarVerde';
import type {
  AggregatesFile,
  Bpa2025FeatureProperties,
  BpaEnrichedFile,
  BpaHistoryFile,
  BpaYear,
  ParcelEnriched,
  PilarVerdePracticaKey,
} from '../../src/types/pilarVerde';

describe('pilarVerde types', () => {
  it('BpaEnrichedFile literal matches real schema 1.0', () => {
    const sample: BpaEnrichedFile = {
      schema_version: '1.0',
      generated_at: '2026-04-20T05:37:59Z',
      source: 'IDECor WFS bpa_2025 + agricultura_v_agro_aceptada_cuentas + agricultura_v_agro_presentada_cuentas + catastro_rural_cu',
      parcels: [
        {
          nro_cuenta: '190119253342',
          nomenclatura: '1901401196560216',
          departamento: 'MARCOS JUAREZ',
          pedania: 'COLONIAS',
          superficie_ha: 49.9,
          valuacion: 688660161.54,
          ley_forestal: 'presentada',
          bpa_2025: {
            n_explotacion: 'Luis Garcia',
            superficie_bpa: 50,
            bpa_total: '2',
            id_explotacion: '4527',
            activa: true,
            ejes: { persona: 'Si', planeta: 'Si', prosperidad: 'No', alianza: 'No' },
            practicas: {
              capacitacion: 'Si',
              tranqueras_abiertas: 'No',
              polinizacion: 'No',
              integ_comunidad: 'No',
              nutricion_suelo: 'No',
              rotacion_gramineas: 'Si',
              pasturas_implantadas: 'No',
              sistema_terraza: 'No',
              bioinsumos: 'No',
              manejo_de_cultivo_int: 'No',
              trazabilidad: 'No',
              tecn_pecuaria: 'No',
              agricultura_de_precision: 'No',
              economia_circular: 'No',
              participacion_grup_asociativo: 'No',
              indiacagro: 'No',
              caminos_rurales: 'No',
              ag_tech: 'No',
              bpa_tutor: 'No',
              corredores_bio: 'No',
              riego_precision: 'No',
            },
          },
          bpa_historico: { '2020': 'Luis Garcia', '2019': 'Luis Garcia' },
        },
      ],
    };
    expect(sample.parcels[0].bpa_2025?.activa).toBe(true);
    expect(sample.parcels[0].bpa_2025?.bpa_total).toBe('2');
  });

  it('ParcelEnriched accepts bpa_2025 === null and null valuacion', () => {
    const sample: ParcelEnriched = {
      nro_cuenta: '999999999999',
      nomenclatura: 'X',
      departamento: 'MARCOS JUAREZ',
      pedania: 'X',
      superficie_ha: 12.3,
      valuacion: null,
      ley_forestal: 'no_inscripta',
      bpa_2025: null,
      bpa_historico: {},
    };
    expect(sample.bpa_2025).toBeNull();
    expect(sample.valuacion).toBeNull();
  });

  it('BpaHistoryFile literal matches real schema 1.0', () => {
    const sample: BpaHistoryFile = {
      schema_version: '1.0',
      generated_at: '2026-04-20T05:37:59Z',
      history: {
        '190203947643': {
          '2024': 'VICHUQUIN 1A / VICHUQUIN 1B',
          '2022': 'VICHUQUIN 1A / VICHUQUIN 1B',
          '2021': 'VICHUQUIN 1A / VICHUQUIN 1B',
          '2020': 'VICHUQUIN 1A / VICHUQUIN 1B',
          '2019': 'VICHUQUIN 1A / VICHUQUIN 1B',
        },
      },
    };
    expect(Object.keys(sample.history)).toContain('190203947643');
  });

  it('AggregatesFile literal matches real schema 1.1 (with historical KPIs)', () => {
    const sample: AggregatesFile = {
      schema_version: '1.1',
      generated_at: '2026-04-20T05:37:59Z',
      zona: { nombre: 'CC 10 de Mayo Ampliada', superficie_ha: 88227.5 },
      ley_forestal: {
        aceptada_count: 252,
        presentada_count: 511,
        no_inscripta_count: 559,
        aceptada_superficie_ha: 27967.6,
        presentada_superficie_ha: 36252.1,
        cumplimiento_pct_parcelas: 33.0,
        cumplimiento_pct_superficie: 43.5,
      },
      bpa: {
        explotaciones_activas: 70,
        superficie_total_ha: 6097.3,
        cobertura_pct_zona: 6.9,
        cobertura_historica_count: 228,
        cobertura_historica_pct: 17.2,
        abandonaron_count: 158,
        abandonaron_pct: 12.0,
        nunca_count: 1094,
        nunca_pct: 82.8,
        evolucion_anual: {
          '2019': 122,
          '2020': 103,
          '2021': 96,
          '2022': 101,
          '2023': 80,
          '2024': 106,
          '2025': 70,
        },
        practica_top_adoptada: { nombre: 'rotacion_gramineas', adopcion_pct: 92.9 },
        practica_top_no_adoptada: { nombre: 'sistema_terraza', adopcion_pct: 0.0 },
        practicas_ranking: [
          { nombre: 'rotacion_gramineas', adopcion_pct: 92.9 },
          { nombre: 'nutricion_suelo', adopcion_pct: 38.6 },
        ],
        ejes_distribucion: { persona: 70, planeta: 60, prosperidad: 50, alianza: 40 },
      },
      grilla_aggregates: {
        altura_med_mean: 120.7,
        pend_media_mean: 0.3,
        forest_mean_pct: 0,
        categoria_distribution: { 'Sin zonas': 3724 },
        drenaje_distribution: {
          'Bien drenado': 325,
          'Imperfectamente drenado': 1126,
          'Moderadamente bien drenado': 2273,
        },
      },
      zonas_agroforestales: [{ leyenda: '11 - Sist Rio Tercero - Este', superficie_ha_en_zona: 0 }],
    };
    expect(sample.bpa.evolucion_anual['2025']).toBe(70);
    expect(sample.bpa.cobertura_historica_count).toBe(228);
  });

  it('BpaYear union covers 2019..2025', () => {
    const years: BpaYear[] = ['2019', '2020', '2021', '2022', '2023', '2024', '2025'];
    expect(years).toHaveLength(7);
    expect(PILAR_VERDE_BPA_YEARS).toEqual(years);
  });

  it('Bpa2025FeatureProperties matches FLAT GeoJSON shape with string activa/bpa_total', () => {
    const props: Bpa2025FeatureProperties = {
      n_explotacion: 'Santo Domingo',
      cuenta: '360302679394',
      superficie: 26.72,
      superficie_bpa: 26.72,
      capacitacion: 'No',
      tranqueras_abiertas: 'No',
      polinizacion: 'No',
      integ_comunidad: 'No',
      nutricion_suelo: 'No',
      rotacion_gramineas: 'Si',
      pasturas_implantadas: 'No',
      sistema_terraza: 'No',
      bioinsumos: 'No',
      manejo_de_cultivo_int: 'No',
      trazabilidad: 'Si',
      tecn_pecuaria: 'No',
      agricultura_de_precision: 'Si',
      economia_circular: 'No',
      participacion_grup_asociativo: 'No',
      indiacagro: 'No',
      caminos_rurales: 'No',
      ag_tech: 'Si',
      bpa_tutor: 'No',
      corredores_bio: 'No',
      riego_precision: 'No',
      eje_persona: 'No',
      eje_planeta: 'Si',
      eje_prosperidad: 'Si',
      eje_alianza: 'Si',
      bpa_total: '4',
      id_explotacion: '1494',
      activa: '1',
    };
    expect(props.activa).toBe('1');
    expect(props.bpa_total).toBe('4');
  });

  it('PilarVerdePracticaKey union exposes the 21 keys', () => {
    const keys: PilarVerdePracticaKey[] = [
      'capacitacion',
      'tranqueras_abiertas',
      'polinizacion',
      'integ_comunidad',
      'nutricion_suelo',
      'rotacion_gramineas',
      'pasturas_implantadas',
      'sistema_terraza',
      'bioinsumos',
      'manejo_de_cultivo_int',
      'trazabilidad',
      'tecn_pecuaria',
      'agricultura_de_precision',
      'economia_circular',
      'participacion_grup_asociativo',
      'indiacagro',
      'caminos_rurales',
      'ag_tech',
      'bpa_tutor',
      'corredores_bio',
      'riego_precision',
    ];
    expect(keys).toHaveLength(21);
    expect(PILAR_VERDE_PRACTICA_KEYS).toHaveLength(21);
    // Set equality regardless of order
    expect(new Set(PILAR_VERDE_PRACTICA_KEYS)).toEqual(new Set(keys));
  });
});
