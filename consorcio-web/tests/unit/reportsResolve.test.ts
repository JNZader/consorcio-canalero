import { describe, expect, it } from 'vitest';

import { buildResolvePayload } from '../../src/lib/api/reportsResolve';

describe('buildResolvePayload', () => {
  it('builds canonical payload with resolved status', () => {
    const payload = buildResolvePayload('report-123', {
      status: 'resolved',
      comment: 'Incidente mitigado',
      resolved_by: 'operator-123',
    });

    expect(payload).toEqual({
      report_id: 'report-123',
      resolution: {
        status: 'resolved',
        comment: 'Incidente mitigado',
        resolved_by: 'operator-123',
      },
    });
  });

  it('keeps rejected status without resolved_by', () => {
    const payload = buildResolvePayload('report-321', {
      status: 'rejected',
      comment: 'No aplica',
    });

    expect(payload.report_id).toBe('report-321');
    expect(payload.resolution.status).toBe('rejected');
    expect(payload.resolution.resolved_by).toBeUndefined();
  });
});
