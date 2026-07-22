import { describe, expect, it } from 'vitest';

import { createDashboardJsonExport } from '../../src/components/admin/adminDashboardExport';

describe('admin dashboard JSON export', () => {
  it('serializes the real dashboard payload as application/json with a .json filename', async () => {
    const payload = {
      ranking_cuencas: [{ cuenca: 'norte', area_anegada_ha: 12.5 }],
      generated_at: '2026-07-18T12:00:00Z',
    };

    const result = createDashboardJsonExport(payload, new Date('2026-07-18T12:00:00.000Z'));

    expect(result.filename).toBe('datos_dashboard_2026-07-18.json');
    expect(result.filename.endsWith('.pdf')).toBe(false);
    expect(result.blob.type).toBe('application/json');
    expect(JSON.parse(await result.blob.text())).toEqual(payload);
  });
});
