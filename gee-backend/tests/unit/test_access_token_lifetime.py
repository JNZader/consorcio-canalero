"""Access JWT lifetime — operator sessions last a workday, not 15 minutes."""

from app.auth.dependencies import ACCESS_TOKEN_LIFETIME_SECONDS


def test_access_token_lasts_eight_hours() -> None:
    assert ACCESS_TOKEN_LIFETIME_SECONDS == 8 * 60 * 60
