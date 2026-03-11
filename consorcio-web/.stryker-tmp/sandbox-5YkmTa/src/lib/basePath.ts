// @ts-nocheck
const BASE_URL = import.meta.env.BASE_URL;

const NORMALIZED_BASE_URL = BASE_URL.endsWith('/') ? BASE_URL : `${BASE_URL}/`;

/**
 * Prefixes app-relative paths with Vite BASE_URL.
 */
export function withBasePath(path: string): string {
  const normalizedPath = path.startsWith('/') ? path.slice(1) : path;
  return `${NORMALIZED_BASE_URL}${normalizedPath}`;
}
