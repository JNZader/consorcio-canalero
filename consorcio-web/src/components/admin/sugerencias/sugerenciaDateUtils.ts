/**
 * Parse an ISO calendar date string (`YYYY-MM-DD`) in the local timezone rather
 * than UTC midnight, preventing off-by-one day shifts in negative UTC offsets.
 */
export function parseLocalIsoDate(raw: string | Date | null | undefined): Date | null {
  if (!raw) return null;
  if (raw instanceof Date) return Number.isNaN(raw.getTime()) ? null : raw;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw.trim());
  if (match) {
    const year = Number(match[1]);
    const month = Number(match[2]) - 1;
    const day = Number(match[3]);
    return new Date(year, month, day);
  }
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * Format a `Date` using local calendar year/month/day as `YYYY-MM-DD`.
 */
export function formatLocalIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
