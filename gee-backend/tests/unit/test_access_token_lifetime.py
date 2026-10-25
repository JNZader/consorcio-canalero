"""Access JWT lifetime — 60 minutes; the refresh cookie carries the session.

Audit finding SEG-2 (owner decision 2026-10-24): the previous 8-hour
"workday token" left a leaked Authorization header fully valid for up
to 8 hours, because ordinary logout, password reset, and token theft
never touch outstanding JWTs — only logout-all / admin force-revoke
(``revocation_epoch``) kill them early. Lowered to 60 minutes: the
rotating refresh cookie (30-day HttpOnly, family replay-burn) keeps
sessions alive transparently, so the shorter access window costs the
user nothing. The end-to-end ``exp`` bound lives in
``tests/new/test_auth_refresh_http.py``.
"""

from app.auth.dependencies import ACCESS_TOKEN_LIFETIME_SECONDS


def test_access_token_lasts_sixty_minutes() -> None:
    assert ACCESS_TOKEN_LIFETIME_SECONDS == 60 * 60
