import { describe, expect, it } from 'vitest';

import { ALONG_LINE_LABEL_MIN_ZOOM } from '../../src/components/map2d/alongLineLabel';
import { ROAD_LABEL_MIN_ZOOM } from '../../src/components/map2d/roadLabelLayer';
import { MAP_DEFAULT_ZOOM } from '../../src/constants';

describe('CART-08 label minzoom vs opening camera', () => {
  it('road and canal names are on at the default map zoom', () => {
    expect(MAP_DEFAULT_ZOOM).toBe(11);
    expect(ROAD_LABEL_MIN_ZOOM).toBeLessThan(MAP_DEFAULT_ZOOM);
    expect(ALONG_LINE_LABEL_MIN_ZOOM).toBeLessThan(MAP_DEFAULT_ZOOM);
  });
});
