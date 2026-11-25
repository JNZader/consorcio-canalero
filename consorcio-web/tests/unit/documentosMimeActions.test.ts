import { describe, expect, it } from 'vitest';
import { canOpenInTab } from '../../src/lib/documentos/mimeActions';

describe('canOpenInTab', () => {
  it.each([
    ['application/pdf', true],
    ['application/pdf; charset=binary', true],
    ['image/jpeg', true],
    ['image/jpg', true],
    ['image/png', true],
    ['text/html', false],
    ['application/vnd.google-earth.kmz', false],
    [
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      false,
    ],
    ['application/x-tex', false],
    ['application/msword', false],
    ['', false],
    [null, false],
    [undefined, false],
  ])('mime %s → openable=%s', (mime, expected) => {
    expect(canOpenInTab(mime)).toBe(expected);
  });
});
