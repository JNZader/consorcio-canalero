// @ts-nocheck
export type ResolveStatus = 'resolved' | 'rejected';

export interface ResolveInput {
  status: ResolveStatus;
  comment: string;
  resolved_by?: string;
}

export interface ResolvePayload {
  report_id: string;
  resolution: ResolveInput;
}

export function buildResolvePayload(id: string, resolution: ResolveInput): ResolvePayload {
  return {
    report_id: id,
    resolution,
  };
}
