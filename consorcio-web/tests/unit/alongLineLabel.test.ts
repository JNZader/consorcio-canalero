import { describe, expect, it } from 'vitest';

import {
  ALONG_LINE_LABEL_MIN_ZOOM,
  CANAL_LABEL_TEXT_FIELD,
  buildAlongLineLabelLayer,
} from '../../src/components/map2d/alongLineLabel';

describe('buildAlongLineLabelLayer', () => {
  it('places canal codigo/nombre along the line like roads', () => {
    const layer = buildAlongLineLabelLayer({
      id: 'canales_relevados-label',
      source: 'canales_relevados',
      textField: CANAL_LABEL_TEXT_FIELD,
    });
    expect(layer.type).toBe('symbol');
    expect(layer.minzoom).toBe(ALONG_LINE_LABEL_MIN_ZOOM);
    expect(layer.layout?.['symbol-placement']).toBe('line');
    expect(layer.layout?.['text-field']).toEqual(['coalesce', ['get', 'codigo'], ['get', 'nombre']]);
    expect(layer.paint?.['text-color']).toBe('#ffffff');
  });
});
