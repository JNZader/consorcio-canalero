# Lower access-token lifetime from 8 h to 60 minutes (SEG-2)

Objective: bound the exposure window of a stolen bearer token to 60 minutes. Audit finding SEG-2 (`docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md`): the access JWT lived 8 hours while being practically irrevocable — ordinary logout, password reset, and token theft never touch outstanding JWTs; only `logout-all` / admin force-revoke (`revocation_epoch`) kill them early. Owner decision 2026-10-24: lower to 60 minutes. The refresh machinery (30-day rotating HttpOnly cookie, family replay-burn) carries session continuity transparently, so the user notices nothing. Branch: `audit-seg2-token-lifetime`. Tests: pytest in `gee-backend`.

## In

- `gee-backend/app/auth/dependencies.py` — `ACCESS_TOKEN_LIFETIME_SECONDS` 8 h → 60 min; comment rewritten to record the SEG-2 owner decision (2026-10-24) and why 60 min is safe (transparent refresh, replay-burn, epoch revocation still available for logout-all/admin force-revoke).
- `gee-backend/tests/unit/test_access_token_lifetime.py` — the pin updated from 8 h to 60 min, docstring records the reasoning (was pinning the old contract).
- `gee-backend/tests/new/test_auth_refresh_http.py` — new `test_login_access_token_expires_within_sixty_minutes`: logs in over HTTP, decodes the issued token through the app's real `get_jwt_strategy()`, asserts `exp` is in `(now+55 min, now+60 min]`. RED on unfixed code (`got exp=+480.0min`), green after.
- `consorcio-web/src/lib/auth/storage.ts` — SEC-04 accepted-risk comment said "the access token lives eight hours"; updated to 60 minutes with the SEG-2 reference. Comment only, no behavior change.

## Out

- `REFRESH_TOKEN_LIFETIME` (30 days) and the refresh cookie `max_age` — explicitly untouched; this change must not alter refresh-cookie semantics.
- `docs/RUNBOOK.md` §2.4 still describes the pre-F5-F "~15 min residual window" as open even though F5-F closed it — pre-existing staleness about a different change, not about the 8 h constant; left for a docs-only unit.
- `docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md` — historical audit record; never edited by fixes.
- Frontend behavior — verified no proactive refresh timer exists (`src/lib/api/core.ts` refreshes reactively on 401 with a single-flight promise); nothing hardcodes 8 h beyond the comment above. No FE code change needed.

## Consumers of the constant (verified)

`ACCESS_TOKEN_LIFETIME_SECONDS` is consumed only by `get_jwt_strategy()` (`app/auth/dependencies.py:323`) → `RevocableJWTStrategy.lifetime_seconds` → `write_token` → `generate_jwt`. Every access-token mint funnels through it: `/auth/jwt/login` (fastapi-users auth router), `/auth/jwt/login-with-refresh` (`router.py:109`), `/auth/jwt/refresh` (`router.py:185`), and the Google OAuth callback (`router.py:593`). No env override exists; `.env*` examples carry no token-lifetime setting.

## Log

L1. 2026-10-25. RED-CHECK on unfixed code: `pytest tests/new/test_auth_refresh_http.py::test_login_access_token_expires_within_sixty_minutes tests/unit/test_access_token_lifetime.py` → 2 failed (`AssertionError: access token exp must be within (now+55min, now+60min] — got exp=+480.0min`; `assert 28800 == (60 * 60)`). After the constant change: same command → 2 passed. (Correction per review RES2-005: this line originally said "4 passed"; the pinned-node command above collects exactly 2 items. The writer's 4 came from running BOTH files in full — the HTTP file has 3 tests plus the unit file's 1 — which is also green post-fix.)

L2. 2026-10-25. Deploy note (review RES2-003): access tokens minted BEFORE this deploy remain valid up to 8 h AFTER it — `revocation_epoch` is per-User and this change does not bump any epoch. The 60-minute window applies to post-deploy mints only; an auditor re-testing SEG-2 within hours of deploys can still observe old 8 h tokens. Optional hard cutover: rotate `JWT_SECRET` at deploy (refresh cookies are DB-backed random tokens, not JWTs, so sessions survive and silently re-mint at 60 min). CAVEAT (review REA2-002): `jwt_secret` ALSO signs the password-reset and email-verification tokens (`dependencies.py` UserManager secrets) — rotating it invalidates every pending reset/verify flow at deploy (users re-request; recoverable, but expect the support noise).
