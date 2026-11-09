import { afterEach, describe, expect, it } from 'vitest';

import {
  consumeMapPreferredView,
  MAP_PREFERRED_VIEW_KEY,
  setMapPreferredView,
} from '../../src/lib/mapPreferredView';

describe('mapPreferredView', () => {
  afterEach(() => {
    sessionStorage.removeItem(MAP_PREFERRED_VIEW_KEY);
  });

  it('stores and consumes a one-shot preferred view', () => {
    setMapPreferredView('comparison');
    expect(sessionStorage.getItem(MAP_PREFERRED_VIEW_KEY)).toBe('comparison');
    expect(consumeMapPreferredView()).toBe('comparison');
    expect(consumeMapPreferredView()).toBeNull();
  });

  it('ignores unknown values', () => {
    sessionStorage.setItem(MAP_PREFERRED_VIEW_KEY, 'nope');
    expect(consumeMapPreferredView()).toBeNull();
  });
});
