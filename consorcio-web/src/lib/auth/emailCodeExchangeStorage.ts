export type EmailCodePurpose = 'verify' | 'reset';

export interface EmailCodeExchangeRecord {
  code: string;
  purpose: EmailCodePurpose;
  exchangeId: string;
}

export const EMAIL_CODE_EXCHANGE_STORAGE_KEYS = {
  reset: 'consorcio_email_code_exchange_reset',
  verify: 'consorcio_email_code_exchange_verify',
} as const satisfies Record<EmailCodePurpose, string>;

type BrowserStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function getSessionStorage(): BrowserStorage | null {
  if (typeof window === 'undefined') return null;

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isEmailCodePurpose(value: unknown): value is EmailCodePurpose {
  return value === 'verify' || value === 'reset';
}

function isEmailCodeExchangeRecord(value: unknown): value is EmailCodeExchangeRecord {
  if (typeof value !== 'object' || value === null) return false;

  const record = value as Record<string, unknown>;
  return (
    typeof record.code === 'string' &&
    isEmailCodePurpose(record.purpose) &&
    typeof record.exchangeId === 'string' &&
    UUID_V4_PATTERN.test(record.exchangeId)
  );
}

function readRecord(
  storage: BrowserStorage,
  purpose: EmailCodePurpose
): EmailCodeExchangeRecord | null {
  const raw = storage.getItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS[purpose]);
  if (!raw) return null;

  try {
    const value: unknown = JSON.parse(raw);
    return isEmailCodeExchangeRecord(value) ? value : null;
  } catch {
    return null;
  }
}

function createRecord(code: string, purpose: EmailCodePurpose): EmailCodeExchangeRecord {
  return {
    code,
    purpose,
    exchangeId: globalThis.crypto.randomUUID(),
  };
}

export function getOrCreateEmailCodeExchange(
  code: string,
  purpose: EmailCodePurpose
): EmailCodeExchangeRecord {
  const storage = getSessionStorage();

  if (storage) {
    try {
      const stored = readRecord(storage, purpose);
      if (stored?.code === code && stored.purpose === purpose) {
        return stored;
      }
    } catch {
      // Storage access can fail in privacy modes; continue without persistence.
    }
  }

  const record = createRecord(code, purpose);
  if (!storage) return record;

  try {
    storage.setItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS[purpose], JSON.stringify(record));
  } catch {
    // Best effort: the current page can still use the generated exchange ID.
  }

  return record;
}

export function clearEmailCodeExchange(record: EmailCodeExchangeRecord): void {
  const storage = getSessionStorage();
  if (!storage) return;

  try {
    const stored = readRecord(storage, record.purpose);
    if (
      stored?.code === record.code &&
      stored.purpose === record.purpose &&
      stored.exchangeId === record.exchangeId
    ) {
      storage.removeItem(EMAIL_CODE_EXCHANGE_STORAGE_KEYS[record.purpose]);
    }
  } catch {
    // Clearing retry metadata is best effort when browser storage is unavailable.
  }
}
