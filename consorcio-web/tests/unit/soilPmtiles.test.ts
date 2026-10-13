import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  SOIL_PMTILES_ARCHIVE_KEY,
  SOIL_PMTILES_PATH,
  ensureSoilPmtilesArchive,
  getSoilPmtilesArchiveKey,
  resetSoilPmtilesArchiveForTests,
  soilPmtilesMapUrl,
} from '../../src/lib/soilPmtiles';

describe('ensureSoilPmtilesArchive', () => {
  afterEach(() => {
    resetSoilPmtilesArchiveForTests();
    vi.unstubAllGlobals();
  });

  it('fetches the archive once without Range and registers FileSource key', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    });
    vi.stubGlobal('fetch', fetchMock);

    const key = await ensureSoilPmtilesArchive();
    await ensureSoilPmtilesArchive();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(SOIL_PMTILES_PATH);
    expect(fetchMock.mock.calls[0]?.[1]).toBeUndefined();
    expect(key).toBe(SOIL_PMTILES_ARCHIVE_KEY);
    expect(getSoilPmtilesArchiveKey()).toBe(SOIL_PMTILES_ARCHIVE_KEY);
    expect(soilPmtilesMapUrl(key)).toBe(`pmtiles://${SOIL_PMTILES_ARCHIVE_KEY}`);
  });
});
