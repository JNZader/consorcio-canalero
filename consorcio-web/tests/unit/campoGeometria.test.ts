/**
 * Campo (PR 6, S6) — the geometry core the GPS panel trusts: point-in-class
 * (ray casting with holes), distance-to-edge in metres, and the boundary
 * warning that names the neighbour class.
 */

import { describe, expect, it } from 'vitest';

import {
  analizarPosicion,
  circuloPrecision,
  claseEnPunto,
  puntoEnGeometria,
} from '@/components/campo/geometriaCampo';
import type { TemaCampo } from '@/components/campo/tiposCampo';

// Three classes of one theme tiling a 0.01° strip (~1.1 km), split by
// vertical edges at lon -61.90 and -61.89 — the same shape the e2e mocks.
const cuadro = (x0: number, x1: number) => ({
  type: 'Polygon' as const,
  coordinates: [
    [
      [x0, -33.01],
      [x1, -33.01],
      [x1, -33.0],
      [x0, -33.0],
      [x0, -33.01],
    ],
  ],
});

const tema: TemaCampo = {
  titulo: 'Riesgo hídrico',
  clases: [
    { clase: 'Bajo', color: '#1a9850', geometrias: [cuadro(-61.91, -61.9)] },
    { clase: 'Medio', color: '#fee08b', geometrias: [cuadro(-61.9, -61.89)] },
    { clase: 'Alto', color: '#fc8d59', geometrias: [cuadro(-61.89, -61.88)] },
  ],
};

const M_LON = 111_320 * Math.cos((-33.005 * Math.PI) / 180); // m per degree lon

describe('puntoEnGeometria', () => {
  it('dice dentro/fuera del polígono y respuesta huecos', () => {
    expect(puntoEnGeometria([-61.905, -33.005], cuadro(-61.91, -61.9))).toBe(true);
    expect(puntoEnGeometria([-61.895, -33.005], cuadro(-61.91, -61.9))).toBe(false);
    const conHueco = {
      type: 'Polygon' as const,
      coordinates: [
        [
          [0, 0],
          [0, 2],
          [2, 2],
          [2, 0],
          [0, 0],
        ],
        [
          [0.5, 0.5],
          [0.5, 1.5],
          [1.5, 1.5],
          [1.5, 0.5],
          [0.5, 0.5],
        ],
      ],
    };
    expect(puntoEnGeometria([0.2, 0.2], conHueco)).toBe(true);
    expect(puntoEnGeometria([1, 1], conHueco)).toBe(false);
  });

  it('soporta MultiPolygon', () => {
    const multi = {
      type: 'MultiPolygon' as const,
      coordinates: [
        [
          [
            [0, 0],
            [0, 1],
            [1, 1],
            [1, 0],
            [0, 0],
          ],
        ],
        [
          [
            [5, 5],
            [5, 6],
            [6, 6],
            [6, 5],
            [5, 5],
          ],
        ],
      ],
    };
    expect(puntoEnGeometria([0.5, 0.5], multi)).toBe(true);
    expect(puntoEnGeometria([5.5, 5.5], multi)).toBe(true);
    expect(puntoEnGeometria([3, 3], multi)).toBe(false);
  });
});

describe('claseEnPunto', () => {
  it('encuentra la clase que contiene al punto', () => {
    expect(claseEnPunto(tema, [-61.905, -33.005])?.clase).toBe('Bajo');
    expect(claseEnPunto(tema, [-61.895, -33.005])?.clase).toBe('Medio');
    expect(claseEnPunto(tema, [-61.885, -33.005])?.clase).toBe('Alto');
    expect(claseEnPunto(tema, [-61.5, -33.005])).toBeNull();
  });
});

describe('analizarPosicion', () => {
  it('lejos del borde: clase limpia, sin aviso', () => {
    // ~0.0025° lon del borde ≈ 230 m ≫ precisión 30 m
    const r = analizarPosicion(tema, [-61.905, -33.005], 30);
    expect(r.clase?.clase).toBe('Bajo');
    expect(r.enLimite).toBe(false);
    expect(r.vecino).toBeNull();
    expect(r.distanciaBordeM).toBeGreaterThan(100);
  });

  it('cerca del borde dentro de la precisión: aviso CON vecino (S6)', () => {
    // 15 m al oeste del borde -61.90, precisión 50 m → límite Bajo|Medio
    const punto: [number, number] = [-61.9 - 15 / M_LON, -33.005];
    const r = analizarPosicion(tema, punto, 50);
    expect(r.clase?.clase).toBe('Bajo');
    expect(r.enLimite).toBe(true);
    expect(r.vecino?.clase).toBe('Medio');
  });

  it('del otro lado del mismo borde nombra el vecino correcto', () => {
    const punto: [number, number] = [-61.9 + 12 / M_LON, -33.005];
    const r = analizarPosicion(tema, punto, 40);
    expect(r.clase?.clase).toBe('Medio');
    expect(r.vecino?.clase).toBe('Bajo');
  });

  it('precisión chica cerca del borde: sin aviso (la duda no alcanza)', () => {
    const punto: [number, number] = [-61.9 + 12 / M_LON, -33.005];
    expect(analizarPosicion(tema, punto, 5).enLimite).toBe(false);
  });

  it('fuera de toda clase y sin tema: null sin explotar', () => {
    const fuera = analizarPosicion(tema, [-61.5, -33.005], 30);
    expect(fuera.clase).toBeNull();
    expect(fuera.enLimite).toBe(false);
    const sinTema = analizarPosicion(null, [-61.5, -33.005], 30);
    expect(sinTema.clase).toBeNull();
  });
});

describe('circuloPrecision', () => {
  it('cierra el anillo con 65 puntos y radio en grados coherente', () => {
    const anillo = circuloPrecision([-61.9, -33.005], 100);
    const coords = (anillo.coordinates as number[][][])[0];
    expect(coords).toHaveLength(65);
    expect(coords[0]).toEqual(coords[64]); // cerrado
    // El primer vértice del anillo está ~100 m al norte del centro (ángulo
    // 0 → +lat; con 64 segmentos la cuerda queda a <1 m del arco).
    const dLat = (coords[0][1] + 33.005) * 110_540;
    expect(Math.abs(dLat - 100)).toBeLessThan(1);
  });
});
