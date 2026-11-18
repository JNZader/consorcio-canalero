/**
 * useSeleccionArea.test.ts
 *
 * The informe de área selection machine (odd/tasks/informe-area-pr1.md, S5):
 *   - sumar: set union, no duplicates;
 *   - quitar: set difference (removable Pills);
 *   - toda la cuenca: union/difference over a cuenca's explicit ids;
 *   - estado indeterminado: `parcial` when some (not all) of a cuenca's zonas
 *     are selected — the Checkbox `indeterminate` state;
 *   - plus the S3 cap: the selection never exceeds 60 ids.
 */

import { describe, expect, it } from 'vitest';

import {
  claveDeSeleccion,
  contarSeleccion,
  cupoLleno,
  estadoCuenca,
  idsDeCuenca,
  LIMITE_ZONAS,
  type SeleccionAreaState,
  seleccionAreaReducer,
  seleccionVacia,
  type ZonaRef,
  zonasSeleccionadas,
} from '../../../src/components/map2d/informeArea/useSeleccionArea';

/** Three zonas across two cuencas — the minimal S5 world. */
const CATALOGO: ZonaRef[] = [
  { id: 'a1', nombre: 'Alta 1', cuenca: 'Río Tercero' },
  { id: 'a2', nombre: 'Alta 2', cuenca: 'Río Tercero' },
  { id: 'b1', nombre: 'Baja 1', cuenca: 'Arroyo Algodón' },
];

function seleccion(...ids: string[]): SeleccionAreaState {
  return new Set(ids);
}

describe('seleccionAreaReducer — sumar', () => {
  it('unions ids without duplicating an already-selected zona', () => {
    const estado = seleccionAreaReducer(seleccion('a1'), { type: 'sumar', ids: ['a2', 'a1'] });
    expect([...estado].sort()).toEqual(['a1', 'a2']);
  });

  it('is idempotent when the same ids arrive twice', () => {
    const primerPaso = seleccionAreaReducer(seleccion(), { type: 'sumar', ids: ['a1'] });
    const segundoPaso = seleccionAreaReducer(primerPaso, { type: 'sumar', ids: ['a1'] });
    expect(segundoPaso).toEqual(primerPaso);
  });
});

describe('seleccionAreaReducer — quitar', () => {
  it('removes only the requested ids', () => {
    const estado = seleccionAreaReducer(seleccion('a1', 'a2', 'b1'), {
      type: 'quitar',
      ids: ['a2'],
    });
    expect([...estado].sort()).toEqual(['a1', 'b1']);
  });

  it('keeps the selection when removing an id that is not selected', () => {
    const estado = seleccion('a1');
    expect(seleccionAreaReducer(estado, { type: 'quitar', ids: ['zzz'] })).toEqual(estado);
  });
});

describe('seleccionAreaReducer — alternar (ctrl/⌘+click suma o saca)', () => {
  it('adds the zona when it is not selected', () => {
    const estado = seleccionAreaReducer(seleccion('a1'), { type: 'alternar', id: 'b1' });
    expect([...estado].sort()).toEqual(['a1', 'b1']);
  });

  it('removes the zona when it already is selected', () => {
    const estado = seleccionAreaReducer(seleccion('a1', 'b1'), { type: 'alternar', id: 'a1' });
    expect([...estado]).toEqual(['b1']);
  });
});

describe('seleccionAreaReducer — reemplazar (plain click)', () => {
  it('replaces the whole selection with the clicked zona', () => {
    const estado = seleccionAreaReducer(seleccion('a1', 'a2'), { type: 'reemplazar', ids: ['b1'] });
    expect([...estado]).toEqual(['b1']);
  });
});

describe('seleccionAreaReducer — toda la cuenca', () => {
  it('includes=true adds every zona of the cuenca, deduplicated', () => {
    const ids = idsDeCuenca(CATALOGO, 'Río Tercero');
    const estado = seleccionAreaReducer(seleccion('a1'), { type: 'cuenca', ids, incluir: true });
    expect([...estado].sort()).toEqual(['a1', 'a2']);
  });

  it('includes=false removes every zona of the cuenca and keeps the others', () => {
    const ids = idsDeCuenca(CATALOGO, 'Río Tercero');
    const estado = seleccionAreaReducer(seleccion('a1', 'a2', 'b1'), {
      type: 'cuenca',
      ids,
      incluir: false,
    });
    expect([...estado]).toEqual(['b1']);
  });
});

describe('estadoCuenca — estado indeterminado (S5)', () => {
  it('is "ninguna" when no zona of the cuenca is selected', () => {
    expect(estadoCuenca(CATALOGO, 'Río Tercero', seleccion('b1'))).toBe('ninguna');
  });

  it('is "parcial" (indeterminate) when only some zonas are selected', () => {
    expect(estadoCuenca(CATALOGO, 'Río Tercero', seleccion('a1'))).toBe('parcial');
  });

  it('is "toda" when every zona of the cuenca is selected', () => {
    expect(estadoCuenca(CATALOGO, 'Río Tercero', seleccion('a1', 'a2'))).toBe('toda');
  });

  it('is "ninguna" for a cuenca with no zonas in the catalog', () => {
    expect(estadoCuenca(CATALOGO, 'Cuenca fantasma', seleccion('a1'))).toBe('ninguna');
  });
});

describe('cap de 60 subcuencas (S3)', () => {
  const muchos = Array.from({ length: 100 }, (_, i) => `zona-${i}`);

  it('sumar stops adding at LIMITE_ZONAS, preserving incoming order', () => {
    const estado = seleccionAreaReducer(seleccion(), { type: 'sumar', ids: muchos });
    expect(contarSeleccion(estado)).toBe(LIMITE_ZONAS);
    expect([...estado]).toEqual(muchos.slice(0, LIMITE_ZONAS));
  });

  it('reemplazar clamps an oversized click selection', () => {
    const estado = seleccionAreaReducer(seleccion('a1', 'a2'), { type: 'reemplazar', ids: muchos });
    expect(contarSeleccion(estado)).toBe(LIMITE_ZONAS);
  });

  it('alternar cannot push the selection past the cap', () => {
    const ids = muchos.slice(0, LIMITE_ZONAS);
    let estado: SeleccionAreaState = seleccion();
    estado = seleccionAreaReducer(estado, { type: 'sumar', ids });
    expect(cupoLleno(estado)).toBe(true);
    expect(seleccionAreaReducer(estado, { type: 'alternar', id: 'zona-extra' })).toEqual(estado);
  });

  it('cupoLleno is false below the cap and quitar frees room again', () => {
    let estado: SeleccionAreaState = seleccion();
    estado = seleccionAreaReducer(estado, { type: 'sumar', ids: muchos.slice(0, 10) });
    expect(cupoLleno(estado)).toBe(false);
    estado = seleccionAreaReducer(estado, { type: 'quitar', ids: muchos.slice(0, 10) });
    expect(seleccionVacia(estado)).toBe(true);
  });
});

describe('helpers', () => {
  it('vaciar clears the selection', () => {
    const estado = seleccionAreaReducer(seleccion('a1', 'b1'), { type: 'vaciar' });
    expect(seleccionVacia(estado)).toBe(true);
    expect(contarSeleccion(estado)).toBe(0);
  });

  it('zonasSeleccionadas returns catalog-ordered ZonaRefs', () => {
    const zonas = zonasSeleccionadas(CATALOGO, seleccion('b1', 'a2'));
    expect(zonas.map((zona) => zona.id)).toEqual(['a2', 'b1']);
    expect(zonas[0]).toMatchObject({ nombre: 'Alta 2', cuenca: 'Río Tercero' });
  });

  it('claveDeSeleccion is order-independent (stable query key)', () => {
    expect(claveDeSeleccion(seleccion('b1', 'a1', 'a2'))).toBe(
      claveDeSeleccion(seleccion('a2', 'a1', 'b1'))
    );
  });
});
