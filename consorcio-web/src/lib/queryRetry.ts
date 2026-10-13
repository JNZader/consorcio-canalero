function httpStatusFromError(error: unknown): number | null {
  if (typeof error === 'object' && error !== null && 'status' in error) {
    const status = (error as { status: unknown }).status;
    if (typeof status === 'number' && Number.isFinite(status)) {
      return status;
    }
  }
  if (error instanceof Error) {
    const match = error.message.match(/API Error: (\d+)/);
    if (match) {
      return Number.parseInt(match[1], 10);
    }
  }
  return null;
}

/** TanStack Query default: retry server errors, never 429 or other 4xx. */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  const status = httpStatusFromError(error);
  if (status === 429) {
    return false;
  }
  if (status !== null && status >= 400 && status < 500) {
    return false;
  }
  return failureCount < 3;
}
