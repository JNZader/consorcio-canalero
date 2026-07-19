import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  EMAIL_CODE_EXCHANGE_STORAGE_KEYS,
  clearEmailCodeExchange,
  getOrCreateEmailCodeExchange,
} from '../../src/lib/auth/emailCodeExchangeStorage';

const FIRST_UUID = '11111111-1111-4111-8111-111111111111';
const SECOND_UUID = '22222222-2222-4222-8222-222222222222';
const THIRD_UUID = '33333333-3333-4333-8333-333333333333';

describe('email code exchange storage', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reuses the UUID for the same code and purpose after a reload', () => {
    const randomUUID = vi
      .spyOn(globalThis.crypto, 'randomUUID')
      .mockReturnValueOnce(FIRST_UUID)
      .mockReturnValueOnce(SECOND_UUID);

    const first = getOrCreateEmailCodeExchange('VERIFY42', 'verify');
    const afterReload = getOrCreateEmailCodeExchange('VERIFY42', 'verify');

    expect(afterReload).toEqual(first);
    expect(randomUUID).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify)).toBe(
      JSON.stringify(first)
    );
  });

  it('uses a fresh UUID when the code or purpose changes', () => {
    vi.spyOn(globalThis.crypto, 'randomUUID')
      .mockReturnValueOnce(FIRST_UUID)
      .mockReturnValueOnce(SECOND_UUID)
      .mockReturnValueOnce(THIRD_UUID);

    const original = getOrCreateEmailCodeExchange('RESET001', 'reset');
    const changedCode = getOrCreateEmailCodeExchange('RESET002', 'reset');
    const changedPurpose = getOrCreateEmailCodeExchange('RESET002', 'verify');

    expect(original.exchangeId).toBe(FIRST_UUID);
    expect(changedCode.exchangeId).toBe(SECOND_UUID);
    expect(changedPurpose.exchangeId).toBe(THIRD_UUID);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).toBe(
      JSON.stringify(changedCode)
    );
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.verify)).toBe(
      JSON.stringify(changedPurpose)
    );
  });

  it('replaces corrupt storage and clears only the matching record', () => {
    vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(FIRST_UUID);
    window.sessionStorage.setItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset, '{not-json');

    const record = getOrCreateEmailCodeExchange('RESET001', 'reset');

    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).toBe(
      JSON.stringify(record)
    );
    clearEmailCodeExchange({ ...record, exchangeId: SECOND_UUID });
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).not.toBeNull();
    clearEmailCodeExchange(record);
    expect(window.sessionStorage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS.reset)).toBeNull();
  });

  it('degrades safely when sessionStorage is unavailable', () => {
    const sessionStorage = window.sessionStorage;
    vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(FIRST_UUID);
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      get: () => {
        throw new Error('storage disabled');
      },
    });

    try {
      expect(getOrCreateEmailCodeExchange('VERIFY42', 'verify')).toEqual({
        code: 'VERIFY42',
        purpose: 'verify',
        exchangeId: FIRST_UUID,
      });
      expect(() =>
        clearEmailCodeExchange({
          code: 'VERIFY42',
          purpose: 'verify',
          exchangeId: FIRST_UUID,
        })
      ).not.toThrow();
    } finally {
      Object.defineProperty(window, 'sessionStorage', {
        configurable: true,
        value: sessionStorage,
      });
    }
  });
});
