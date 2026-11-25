import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchAuthenticatedFileMock = vi.hoisted(() => vi.fn());

vi.mock('../../src/lib/api/core', () => ({
  LONG_TIMEOUT: 60000,
  fetchAuthenticatedFile: fetchAuthenticatedFileMock,
}));

import {
  documentosArchivoEndpoint,
  downloadDocumentosArchivo,
  openDocumentosArchivo,
} from '../../src/lib/documentos/download';

describe('documentos download helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('builds opaque-id paths without filenames', () => {
    expect(documentosArchivoEndpoint('codist-p-ach', 'codist-p-ach__p-ach-pdf')).toBe(
      '/documentos/codist-p-ach/archivo/codist-p-ach__p-ach-pdf'
    );
  });

  it('downloadDocumentosArchivo uses fetchAuthenticatedFile + LONG_TIMEOUT + anchor', async () => {
    const blob = new Blob(['%PDF'], { type: 'application/pdf' });
    fetchAuthenticatedFileMock.mockResolvedValue({
      blob,
      filename: 'p-ach.pdf',
      contentType: 'application/pdf',
    });

    const createObjectUrlSpy = vi.fn(() => 'blob:doc');
    const revokeObjectUrlSpy = vi.fn();
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: createObjectUrlSpy,
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: revokeObjectUrlSpy,
    });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const created: HTMLAnchorElement[] = [];
    const orig = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = orig(tag);
      if (tag.toLowerCase() === 'a') created.push(el as HTMLAnchorElement);
      return el;
    });

    await downloadDocumentosArchivo('codist-p-ach', 'codist-p-ach__p-ach-pdf', 'fallback.pdf');

    expect(fetchAuthenticatedFileMock).toHaveBeenCalledWith(
      '/documentos/codist-p-ach/archivo/codist-p-ach__p-ach-pdf',
      { timeout: 60000 }
    );
    expect(createObjectUrlSpy).toHaveBeenCalledWith(blob);
    expect(created[0]?.download).toBe('p-ach.pdf');
    expect(clickSpy).toHaveBeenCalledTimes(1);

    vi.restoreAllMocks();
  });

  it('openDocumentosArchivo opens a blob tab for PDF and refuses KMZ', async () => {
    fetchAuthenticatedFileMock.mockResolvedValue({
      blob: new Blob(['%PDF'], { type: 'application/pdf' }),
      filename: 'x.pdf',
      contentType: 'application/pdf',
    });
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(() => 'blob:pdf'),
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });

    await openDocumentosArchivo('d1', 'f1', 'application/pdf');
    expect(openSpy).toHaveBeenCalledWith('blob:pdf', '_blank', 'noopener,noreferrer');

    await expect(
      openDocumentosArchivo('d1', 'f1', 'application/vnd.google-earth.kmz')
    ).rejects.toThrow(/descargar/i);

    vi.restoreAllMocks();
  });
});
