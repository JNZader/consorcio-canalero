/**
 * Selection identity for a multi-parcel ficha (T4).
 *
 * `fichaSelectionKey` is the reset TRIGGER for every ficha panel and the query
 * key for the fetch, so "the UI thinks this is a new selection" and "the query
 * refetches" are the same decision. For a union the identity is the SET of
 * parcels: adding or removing one MUST change it; re-ordering must NOT.
 */

import { describe, expect, it } from 'vitest';

import {
  FICHA_IDLE_SELECTION_KEY,
  fichaSelectionKey,
  refKeyFor,
} from '../../src/hooks/useFichaTerritorial';

const A = '13-06-01-0201';
const B = '13-06-01-0202';
const C = '13-06-01-0203';

describe('fichaSelectionKey — tipo=parcelas', () => {
  it('is order-independent: the same SET is the same selection', () => {
    expect(refKeyFor({ tipo: 'parcelas', nomenclaturas: [C, A, B] })).toBe(
      refKeyFor({ tipo: 'parcelas', nomenclaturas: [A, B, C] })
    );
  });

  it('CHANGES when a parcel is added', () => {
    const dos = fichaSelectionKey({ tipo: 'parcelas', nomenclaturas: [A, B] });
    const tres = fichaSelectionKey({ tipo: 'parcelas', nomenclaturas: [A, B, C] });
    expect(tres).not.toBe(dos);
  });

  it('CHANGES when a parcel is removed', () => {
    const tres = fichaSelectionKey({ tipo: 'parcelas', nomenclaturas: [A, B, C] });
    const dos = fichaSelectionKey({ tipo: 'parcelas', nomenclaturas: [A, C] });
    expect(dos).not.toBe(tres);
  });

  it('never collides with the single-parcel key of one of its members', () => {
    expect(fichaSelectionKey({ tipo: 'parcelas', nomenclaturas: [A, B] })).not.toBe(
      fichaSelectionKey({ tipo: 'parcela', nomenclatura: A })
    );
  });

  it('is the idle constant when nothing is selected', () => {
    expect(fichaSelectionKey(null)).toBe(FICHA_IDLE_SELECTION_KEY);
  });
});
