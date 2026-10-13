import { describe, expect, it } from 'vitest';

import { shouldRetryQuery } from '../../src/lib/queryRetry';

describe('shouldRetryQuery', () => {
  it('does not retry 429 from API Error message', () => {
    expect(shouldRetryQuery(0, new Error('API Error: 429'))).toBe(false);
  });

  it('does not retry other 4xx', () => {
    expect(shouldRetryQuery(0, new Error('API Error: 404'))).toBe(false);
    expect(shouldRetryQuery(0, { status: 401 })).toBe(false);
  });

  it('retries 5xx until three failures', () => {
    expect(shouldRetryQuery(0, new Error('API Error: 503'))).toBe(true);
    expect(shouldRetryQuery(2, { status: 500 })).toBe(true);
    expect(shouldRetryQuery(3, { status: 500 })).toBe(false);
  });

  it('retries network errors without a status', () => {
    expect(shouldRetryQuery(0, new Error('Failed to fetch'))).toBe(true);
  });
});
