import { describe, expect, it } from 'vitest';

import {
  REPORT_FLY_ESSENTIAL,
  readReportHighlightFromSearch,
} from '../../src/components/map2d/useReportHighlight';

describe('readReportHighlightFromSearch', () => {
  it('ignores camera permalinks without report=1', () => {
    expect(readReportHighlightFromSearch('?lat=-32.62&lng=-62.7&zoom=15')).toBeNull();
  });

  it('does not force motion on denuncia flyTo (A11Y-08)', () => {
    expect(REPORT_FLY_ESSENTIAL).toBe(false);
  });

  it('reads a denuncia pin only when report=1', () => {
    expect(readReportHighlightFromSearch('?report=1&lat=-32.62&lng=-62.7&zoom=15')).toEqual({
      lat: -32.62,
      lng: -62.7,
      zoom: 15,
    });
  });
});
