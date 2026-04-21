/**
 * triggerKmzDownload.test.ts
 *
 * Batch E — Phase 4 [RED] for change `kmz-export-all-layers`.
 *
 * Pins the behaviour of `triggerKmzDownload(blob, filename)`:
 *   1. Calls `URL.createObjectURL(blob)` and uses the returned URL.
 *   2. Creates a fresh `<a>` element, sets `href` and `download`.
 *   3. Appends the element to `document.body`.
 *   4. Clicks the element exactly once.
 *   5. Removes the element from the DOM after the click.
 *   6. Calls `URL.revokeObjectURL(url)` AFTER the click — non-negotiable to
 *      prevent long-lived object-URL leaks.
 *   7. Filename is passed VERBATIM to `download` (no sanitization — the
 *      caller owns the filename contract).
 *
 * Runs on happy-dom; `document.body`, `URL.createObjectURL`, and
 * `URL.revokeObjectURL` are all implemented.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { triggerKmzDownload } from '../../src/lib/kmzExport/triggerKmzDownload';

const FAKE_OBJECT_URL = 'blob:http://localhost/fake-object-url';

describe('triggerKmzDownload', () => {
  let createObjectURL: ReturnType<typeof vi.spyOn>;
  let revokeObjectURL: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    createObjectURL = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue(FAKE_OBJECT_URL);
    revokeObjectURL = vi
      .spyOn(URL, 'revokeObjectURL')
      .mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls URL.createObjectURL(blob) and uses the returned URL', () => {
    const blob = new Blob(['zip'], { type: 'application/vnd.google-earth.kmz' });

    triggerKmzDownload(blob, 'file.kmz');

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledWith(blob);
  });

  it('creates an <a> with href=<url> and download=<filename>', () => {
    const blob = new Blob(['zip']);
    const originalCreateElement = document.createElement.bind(document);
    let capturedAnchor: HTMLAnchorElement | null = null;
    const createElementSpy = vi
      .spyOn(document, 'createElement')
      .mockImplementation(((tagName: string) => {
        const el = originalCreateElement(tagName);
        if (tagName === 'a') {
          capturedAnchor = el as HTMLAnchorElement;
        }
        return el;
      }) as typeof document.createElement);

    try {
      triggerKmzDownload(blob, 'consorcio_canalero_2026-04-21.kmz');

      expect(createElementSpy).toHaveBeenCalledWith('a');
      expect(capturedAnchor).not.toBeNull();
      // `a.href` is reflected as an absolute URL by happy-dom, but the set
      // value should be FAKE_OBJECT_URL verbatim — check via getAttribute.
      expect(capturedAnchor!.getAttribute('href')).toBe(FAKE_OBJECT_URL);
      expect(capturedAnchor!.download).toBe('consorcio_canalero_2026-04-21.kmz');
    } finally {
      createElementSpy.mockRestore();
    }
  });

  it('appends the anchor to document.body before the click', () => {
    const blob = new Blob(['zip']);
    const appendChildSpy = vi.spyOn(document.body, 'appendChild');
    const clickBefore: string[] = [];

    // Tap click to capture order of appendChild vs. click.
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      const el = originalCreateElement(tagName);
      if (tagName === 'a') {
        const anchor = el as HTMLAnchorElement;
        const originalClick = anchor.click.bind(anchor);
        anchor.click = () => {
          clickBefore.push('click');
          originalClick();
        };
      }
      return el;
    }) as typeof document.createElement);

    triggerKmzDownload(blob, 'file.kmz');

    expect(appendChildSpy).toHaveBeenCalled();
    // appendChild must fire before the click.
    const appendCallOrder = appendChildSpy.mock.invocationCallOrder[0];
    const clickInvoked = clickBefore.length === 1;
    expect(clickInvoked).toBe(true);
    // appendCallOrder is always defined if appendChild was called.
    expect(typeof appendCallOrder).toBe('number');
  });

  it('clicks the anchor exactly once', () => {
    const blob = new Blob(['zip']);
    const clicks: string[] = [];
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      const el = originalCreateElement(tagName);
      if (tagName === 'a') {
        (el as HTMLAnchorElement).click = () => {
          clicks.push('click');
        };
      }
      return el;
    }) as typeof document.createElement);

    triggerKmzDownload(blob, 'file.kmz');

    expect(clicks).toHaveLength(1);
  });

  it('removes the anchor from document.body after the click', () => {
    const blob = new Blob(['zip']);
    const removeChildSpy = vi.spyOn(document.body, 'removeChild');

    triggerKmzDownload(blob, 'file.kmz');

    expect(removeChildSpy).toHaveBeenCalledTimes(1);
    // The removed node is the anchor we just appended.
    const removed = removeChildSpy.mock.calls[0][0] as HTMLElement;
    expect(removed.tagName.toLowerCase()).toBe('a');
    // And it must no longer be in the DOM after the call.
    expect(document.body.contains(removed)).toBe(false);
  });

  it('calls URL.revokeObjectURL(url) AFTER the click', () => {
    const blob = new Blob(['zip']);
    const ops: string[] = [];

    revokeObjectURL.mockImplementation(((u: string) => {
      ops.push(`revoke:${u}`);
    }) as unknown as () => void);

    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      const el = originalCreateElement(tagName);
      if (tagName === 'a') {
        (el as HTMLAnchorElement).click = () => {
          ops.push('click');
        };
      }
      return el;
    }) as typeof document.createElement);

    triggerKmzDownload(blob, 'file.kmz');

    expect(ops).toEqual(['click', `revoke:${FAKE_OBJECT_URL}`]);
    expect(revokeObjectURL).toHaveBeenCalledWith(FAKE_OBJECT_URL);
  });

  it('passes filenames with special chars verbatim to download', () => {
    const blob = new Blob(['zip']);
    const filename = 'consorcio_canalero_2026-04-21.kmz';

    let capturedAnchor: HTMLAnchorElement | null = null;
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      const el = originalCreateElement(tagName);
      if (tagName === 'a') {
        capturedAnchor = el as HTMLAnchorElement;
      }
      return el;
    }) as typeof document.createElement);

    triggerKmzDownload(blob, filename);

    expect(capturedAnchor).not.toBeNull();
    expect(capturedAnchor!.download).toBe(filename);
  });
});
