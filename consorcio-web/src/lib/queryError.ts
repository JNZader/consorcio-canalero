/**
 * QueryError — the error type thrown by the API core on non-2xx responses.
 *
 * It lives in this leaf module (not in `query.ts`) because two layers that
 * must not depend on each other both need it: `api/core.ts` throws it and
 * `queryRetry.ts` reads `statusCode` from it to decide whether a failure is
 * worth retrying. Importing `query.ts` from the API core would close the
 * cycle core.ts → query.ts → api/index.ts → core.ts, so the class is defined
 * here and re-exported from `query.ts` to preserve its historical import path.
 *
 * FE-3: before this wiring the core threw plain `Error`s whose message came
 * from the backend payload (e.g. FastAPI's `HTTPException(detail="...")`).
 * Those messages carry no status, so `httpStatusFromError` could only rely on
 * the `API Error: NNN` fallback — which string details skip — and the retry
 * policy retried permanent 4xx failures (403/404/409) three times with
 * backoff.
 */
export class QueryError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly endpoint?: string
  ) {
    super(message);
    this.name = 'QueryError';
  }
}
