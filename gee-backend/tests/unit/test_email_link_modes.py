from app.shared.email import build_reset_email, build_verification_email


def test_one_time_code_links_use_code_query_parameter() -> None:
    verify = build_verification_email(
        "VERIFY42",
        "https://consorcio.example",
        query_parameter="code",
    )
    reset = build_reset_email(
        "RESET42",
        "https://consorcio.example",
        query_parameter="code",
    )

    for body in (verify["body_text"], verify["body_html"]):
        assert "/verify-email?code=VERIFY42" in body
        assert "/verify-email?token=" not in body
    for body in (reset["body_text"], reset["body_html"]):
        assert "/reset-password?code=RESET42" in body
        assert "/reset-password?token=" not in body


def test_legacy_jwt_links_use_token_query_parameter() -> None:
    verify = build_verification_email(
        "legacy.verify.jwt",
        "https://consorcio.example",
        query_parameter="token",
    )
    reset = build_reset_email(
        "legacy.reset.jwt",
        "https://consorcio.example",
        query_parameter="token",
    )

    for body in (verify["body_text"], verify["body_html"]):
        assert "/verify-email?token=legacy.verify.jwt" in body
        assert "/verify-email?code=" not in body
    for body in (reset["body_text"], reset["body_html"]):
        assert "/reset-password?token=legacy.reset.jwt" in body
        assert "/reset-password?code=" not in body
