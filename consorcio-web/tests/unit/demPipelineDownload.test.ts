import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getAccessTokenMock, hasLocalLogoutTombstoneMock } = vi.hoisted(() => ({
  getAccessTokenMock: vi.fn(),
  hasLocalLogoutTombstoneMock: vi.fn(() => false),
}));

vi.mock('../../src/lib/auth/index', () => ({
  authAdapter: {
    getAccessToken: getAccessTokenMock,
    replaceAccessToken: vi.fn(),
    clearTokens: vi.fn(),
  },
}));

vi.mock('../../src/lib/auth/storage', () => ({
  hasLocalLogoutTombstone: hasLocalLogoutTombstoneMock,
}));

import { clearAuthTokenCache, fetchAuthenticatedFile } from '../../src/lib/api/core';
import { demPipelineApi } from '../../src/lib/api/demPipeline';

describe('authenticated DEM layer download (C15)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearAuthTokenCache();
    hasLocalLogoutTombstoneMock.mockReturnValue(false);
    getAccessTokenMock.mockResolvedValue('secret-jwt-token');
  });

  it('sends Bearer authorization and extracts filename from Content-Disposition', async () => {
    const expectedBlob = new Blob(['geotiff-bytes'], { type: 'image/tiff' });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({
        'content-disposition': 'attachment; filename="twi_cuenca_norte.tif"',
      }),
      blob: async () => expectedBlob,
    });
    vi.stubGlobal('fetch', fetchMock);

    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const createObjectUrlSpy = vi.fn(() => 'blob:mock-url');
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
    const createdLinks: HTMLAnchorElement[] = [];
    const origCreateElement = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      const el = origCreateElement(tagName);
      if (tagName.toLowerCase() === 'a') {
        createdLinks.push(el as HTMLAnchorElement);
      }
      return el;
    });

    await demPipelineApi.downloadLayerFile('layer-42', 'fallback.tif');

    expect(openSpy).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      demPipelineApi.getLayerFileUrl('layer-42'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer secret-jwt-token',
        }),
      })
    );
    expect(createObjectUrlSpy).toHaveBeenCalledWith(expectedBlob);
    expect(createdLinks[0]?.download).toBe('twi_cuenca_norte.tif');
    expect(clickSpy).toHaveBeenCalledTimes(1);

    vi.restoreAllMocks();
  });

  it('parses RFC 5987 UTF-8 filenames in fetchAuthenticatedFile', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({
        'content-disposition': "attachment; filename*=UTF-8''capa%20h%C3%ADdrica.geojson",
      }),
      blob: async () => new Blob(['{}']),
    });
    vi.stubGlobal('fetch', fetchMock);

    const { filename } = await fetchAuthenticatedFile('/geo/layers/layer-7/file');
    expect(filename).toBe('capa hídrica.geojson');

    vi.unstubAllGlobals();
  });
});
