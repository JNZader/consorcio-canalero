const STORAGE_KEY = 'cc-map-search-recent';
const LIMIT = 8;
let memory: string[] = [];

function readStore(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readRecentSearches(): string[] {
  const store = readStore();
  if (!store) return memory;
  try {
    const raw = store.getItem(STORAGE_KEY);
    if (raw == null) return memory;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return memory;
    memory = parsed.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
    return memory;
  } catch {
    return memory;
  }
}

export function rememberSearch(query: string): string[] {
  const trimmed = query.trim();
  if (trimmed.length < 2) return readRecentSearches();
  const next = [trimmed, ...readRecentSearches().filter((item) => item !== trimmed)].slice(0, LIMIT);
  memory = next;
  const store = readStore();
  if (store) {
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* private mode */
    }
  }
  return next;
}
