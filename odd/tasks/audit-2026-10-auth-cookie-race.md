# audit-2026-10-auth-cookie-race

Fix review finding **RES2-002** (SEG-2 4R, resilience lens; materially
amplified by the just-approved 60-minute access tokens — the FE half of the
amplification is a separate, in-flight sibling unit on the frontend refresh
cadence).

Root cause: when two tabs hit `/auth/jwt/refresh` within the family's
`RACE_WINDOW`, the winner CAS-rotates and stamps the new cookie; the loser —
serialized behind the winner by the per-family advisory xact lock, so it
responds AFTER the winner — got a 401 whose response carried
`_clear_refresh_cookie` (`delete_cookie`). The shared browser cookie jar ends
up EMPTY despite a valid rotated token in the family: the winner tab keeps
working for up to 60 minutes, then dies on "missing refresh cookie" — a
forced logout up to an hour later, in a DIFFERENT tab than the race. The
family itself was correctly NOT burned (the grace window holds); the only
defect was the destructive cookie clear on a race loss. With an hourly
refresh cadence and two-tab users (~8 refresh boundaries/day), the reviewer
estimated the bug at order 10%/user-day.

## In

- [x] Minimal typed signal from `rotate()`: new `RotateFailure` enum
      (`INVALID` / `REPLAY` / `RACE_LOST`) in
      `gee-backend/app/auth/refresh_tokens.py`. `rotate()` now returns
      `tuple[str, RefreshToken] | RotateFailure` instead of collapsing every
      failure to `None`. The code did NOT distinguish race-loss from replay
      before (both exited through the same `return None` past the
      `should_burn` decision), so the enum is the new, minimal contract.
      All failure paths keep running the SAME SQL roundtrips (the timing
      side-channel equalization is untouched); the response body stays
      identical on every failure path — only the cookie directive differs.
- [x] Router fix (`gee-backend/app/auth/router.py`, refresh endpoint): the
      401 stands on every failure, but `delete_cookie` is now issued on
      `INVALID`/`REPLAY` only. On `RACE_LOST` the cookie survives so the
      loser tab's NEXT refresh (or any tab's) succeeds against the winner's
      rotated token. Comment cites the two-tab scenario and RES2-002;
      endpoint docstring documents the exception. Accepted residual
      (documented on the enum): the `Set-Cookie` header now differs between
      race-loss and genuine failures, which only reveals "the winning
      rotation committed within the last 5 s" — information the presenter
      already has from its own 401, and the family-alive grace window is the
      pre-existing reviewed design.
- [x] HTTP race test (RED-checked, `tests/new/test_auth_refresh_http.py`):
      winner refresh → 200 + rotated cookie; loser presents the SAME stale
      cookie explicitly (explicit `Cookie` header — verified to replace the
      httpx jar, modeling tab B's captured copy) → 401 whose response must
      NOT carry a `refresh_token` delete directive, and the family is not
      burned (a follow-up refresh with the jar's rotated token succeeds).
      Assertions target the response HEADER, not the httpx jar — httpx does
      not honour `Max-Age=0` deletes (verified), but every real browser
      does. RED on unfixed code: the loser's response carried the delete
      (`1 failed` verbatim in the validation log); GREEN after the fix.
- [x] HTTP genuine-failure pins (same file): (b) garbage cookie → 401 +
      delete directive still present; (c) replay past `RACE_WINDOW`
      (revoked row backdated via direct DB update, mirroring the unit
      tests' `_backdate`) → 401 + delete directive + family burned (the
      winner's rotated token is dead too). Both green before AND after the
      fix. Note: the reviewer's brief called these "existing pins" — no
      HTTP-level pins existed for either behavior (only unit-level pins in
      `test_refresh_token_rotation.py`); they are now pinned at HTTP level.
- [x] Unit pins migrated to the typed contract
      (`tests/new/test_refresh_token_rotation.py`): unknown token →
      `RotateFailure.INVALID`; both replay scenarios → `RotateFailure.REPLAY`;
      the two-tab race loser → `RotateFailure.RACE_LOST` (strengthened: the
      failure MODE is now pinned, not just "not None"); lock-timeout →
      `RotateFailure.INVALID` (fail-secure, cookie still cleared). The
      pinned BEHAVIOR of every pre-existing test is unchanged — only the
      failure-shape assertion moved from `is None` to the enum.
- [x] REVIEW FIX ROUNDS (4R lenses RELIABILITY/RESILIENCE/READABILITY —
      applied in-diff, same commit):
      - Flake guard (RELC-003): the HTTP race test monkeypatches
        `RACE_WINDOW` to 300 s — it pins the HEADER DISCRIMINATION, not the
        window value; a stalled CI runner can no longer flip the loser to
        REPLAY and false-fail.
      - Boundary epsilon pair (RELC-001): unit test pins RACE_LOST at
        window−0.5 s and REPLAY at window+0.5 s — a flipped comparison or a
        silently shrunk window now fails.
      - Logout-race pin (RELC-002): a refresh racing a <5 s-old logout-all
        sweep classifies RACE_LOST (fresh-stamp rule); enum docstring states
        the full trigger set, not just "winner rotated".
      - Import-time coupling assert (RESC-002):
        `_LOCK_TIMEOUT_MS <= RACE_WINDOW` asserted at module load with the
        reasoning — raising the lock timeout (the tempting brownout
        mitigation) would convert brownout race-losses into family burns.
      - Brownout ordering caveat (RESC-001): the router comment no longer
        overclaims "its Set-Cookie already landed" — the lock-timeout path
        can falsify it under degradation; recoverable-by-construction noted.
      - Observability (RESC-004): `RACE_LOST` logs at info (honest wording:
        "CAS lost to a fresh revocation stamp (tab race or logout sweep)")
        so the residual rate is visible in production.
      - Truth fixes (REACC-001/003): log line and inline test comment no
        longer assert "family alive, winner rotated" / "5 s window" in cases
        where the fresh-stamp rule fires without a live family.

## Out

- No change to `RACE_WINDOW` (5 s), the grace-window policy, the family-burn
  sweep, the advisory-lock protocol, or the timing equalization between the
  race-loss and replay SQL paths.
- Brownout residual (RESC-001): a loser whose lock TIMES OUT still gets the
  cookie cleared while the family may be alive — pre-existing path,
  recoverable (next refresh clears a genuinely dead family); accepted and
  now documented instead of overclaimed.
- No frontend changes here: the FE half of the SEG-2 60-minute-token
  amplification (SPA refresh cadence / retry handling, incl. the loser tab's
  own recovery — RESC-003) is the separate sibling unit (#608).
- `test_auth_gates.py` untouched (its `test_refresh_without_cookie_401`
  covers the missing-cookie 401, which never cleared and still doesn't).
- No e2e additions; no migration (wire behavior only, no schema change).

## Validation

`tests/new/ -k 'auth or token or refresh or login or oauth'` (FINAL state,
incl. both fix rounds): **216 passed, 6 skipped** (pre-existing
`TEST_LIVE_MARTIN` live-server skips), 4689 deselected. `ruff check` +
`ruff format` clean on all changed files.
