/**
 * Shared formatting utilities for the Consorcio Canalero application.
 */

/**
 * Get month format based on format type (avoids nested ternary).
 */
function getMonthFormat(format: 'short' | 'medium' | 'long'): '2-digit' | 'short' | 'long' {
  if (format === 'short') return '2-digit';
  if (format === 'long') return 'long';
  return 'short';
}

/**
 * Format a date string or Date object to a localized Spanish date string.
 * @param date - The date to format (string, Date, or null/undefined)
 * @param options - Additional formatting options
 * @returns Formatted date string or fallback value
 */
export function formatDate(
  date: string | Date | null | undefined,
  options: {
    includeTime?: boolean;
    fallback?: string;
    format?: 'short' | 'medium' | 'long';
  } = {}
): string {
  const { includeTime = false, fallback = '-', format = 'medium' } = options;

  if (!date) return fallback;

  try {
    const dateObj = typeof date === 'string' ? new Date(date) : date;

    if (Number.isNaN(dateObj.getTime())) return fallback;

    const dateOptions: Intl.DateTimeFormatOptions = {
      year: 'numeric',
      month: getMonthFormat(format),
      day: 'numeric',
    };

    if (includeTime) {
      dateOptions.hour = '2-digit';
      dateOptions.minute = '2-digit';
    }

    return dateObj.toLocaleDateString('es-AR', dateOptions);
  } catch {
    return fallback;
  }
}

/**
 * Format a date for input fields (YYYY-MM-DD format).
 * @param date - The date to format
 * @returns Date string in YYYY-MM-DD format
 */
export function formatDateForInput(date: Date | string | null | undefined): string {
  if (!date) return '';

  try {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    if (Number.isNaN(dateObj.getTime())) return '';

    return dateObj.toISOString().split('T')[0];
  } catch {
    return '';
  }
}

/**
 * Format a relative time string (e.g., "hace 2 horas").
 * @param date - The date to format
 * @returns Relative time string in Spanish
 */
export function formatRelativeTime(date: string | Date | null | undefined): string {
  if (!date) return '-';

  try {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    if (Number.isNaN(dateObj.getTime())) return '-';

    const now = new Date();
    const diffMs = now.getTime() - dateObj.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Ahora mismo';
    if (diffMins < 60) return `Hace ${diffMins} ${diffMins === 1 ? 'minuto' : 'minutos'}`;
    if (diffHours < 24) return `Hace ${diffHours} ${diffHours === 1 ? 'hora' : 'horas'}`;
    if (diffDays < 7) return `Hace ${diffDays} ${diffDays === 1 ? 'dia' : 'dias'}`;

    return formatDate(dateObj, { format: 'medium' });
  } catch {
    return '-';
  }
}

/**
 * Format a number with thousands separators.
 * @param value - The number to format
 * @param decimals - Number of decimal places
 * @returns Formatted number string
 */
export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return '-';

  return value.toLocaleString('es-AR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Format hectares with proper suffix.
 * @param value - The value in hectares
 * @returns Formatted string with "ha" suffix
 */
export function formatHectares(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return `${formatNumber(value)} ha`;
}

/**
 * Format a percentage value.
 * @param value - The percentage value (0-100)
 * @param decimals - Number of decimal places
 * @returns Formatted percentage string
 */
export function formatPercentage(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return '-';
  return `${formatNumber(value, decimals)}%`;
}

/**
 * Format a date with custom options for display.
 * @param date - The date to format
 * @param options - Intl.DateTimeFormatOptions to use
 * @returns Formatted date string
 */
export function formatDateCustom(
  date: string | Date | null | undefined,
  options: Intl.DateTimeFormatOptions,
  fallback = '-'
): string {
  if (!date) return fallback;

  try {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    if (Number.isNaN(dateObj.getTime())) return fallback;

    return dateObj.toLocaleDateString('es-AR', options);
  } catch {
    return fallback;
  }
}

/**
 * Format a date with time for display.
 * @param date - The date to format
 * @returns Formatted date and time string
 */
export function formatDateTime(date: string | Date | null | undefined, fallback = '-'): string {
  if (!date) return fallback;

  try {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    if (Number.isNaN(dateObj.getTime())) return fallback;

    return dateObj.toLocaleString('es-AR');
  } catch {
    return fallback;
  }
}
