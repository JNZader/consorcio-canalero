import { describe, expect, it } from 'vitest';

import {
  LAYER_ACCORDION_ALL,
  displayedAccordionValue,
  idleAccordionValue,
  rememberAccordionChange,
} from '../../src/components/map2d/accordionOpenState';

describe('accordionOpenState UX-07', () => {
  it('opens active families plus raster when a DEM is on', () => {
    expect(idleAccordionValue(['hidrografia'], true)).toEqual(['hidrografia', 'raster']);
  });

  it('opens every section while searching without forgetting idle state', () => {
    expect(displayedAccordionValue(true, ['canales'], ['hidrografia'], ['territorio'])).toEqual([
      'territorio',
    ]);
    expect(displayedAccordionValue(true, ['canales'], ['hidrografia'])).toEqual([...LAYER_ACCORDION_ALL]);
    expect(displayedAccordionValue(false, ['canales'], ['hidrografia'])).toEqual(['canales']);
    expect(displayedAccordionValue(false, null, ['hidrografia'])).toEqual(['hidrografia']);
  });

  it('does not clobber stored sections while the search key is active', () => {
    expect(rememberAccordionChange(true, [...LAYER_ACCORDION_ALL], ['canales'])).toEqual(['canales']);
    expect(rememberAccordionChange(false, ['territorio'], ['canales'])).toEqual(['territorio']);
  });
});
