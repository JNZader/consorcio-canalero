import { describe, expect, it } from 'vitest';

import { WATERWAY_DEFS } from '../../src/hooks/useWaterways';

describe('WATERWAY_DEFS cartography (CART-03)', () => {
  it('distinguishes river, canal and arroyo by width and dash', () => {
    const rio = WATERWAY_DEFS.find((item) => item.id === 'rio_tercero');
    const canal = WATERWAY_DEFS.find((item) => item.id === 'canal_desviador');
    const arroyo = WATERWAY_DEFS.find((item) => item.id === 'arroyo_algodon');
    expect(rio?.style.weight).toBe(3);
    expect(rio?.style.dashArray).toBeUndefined();
    expect(canal?.style.weight).toBe(2);
    expect(canal?.style.dashArray).toBe('4,2');
    expect(arroyo?.style.weight).toBe(1.5);
    expect(arroyo?.style.dashArray).toBe('2,2');
  });
});
