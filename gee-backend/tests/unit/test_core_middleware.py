"""Focused JWT compatibility contracts for application middleware."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import jwt
import pytest

from app.core import middleware


REPO_ROOT = Path(__file__).resolve().parents[2]
JWT_SECRET = "middleware-test-secret-64-bytes-minimum-0123456789-abcdefghijklmnopqrstuvwxyz"
USER_ID = "5c03fbd4-4b6f-4ee4-8d7a-02b13a305bf4"


@pytest.fixture(autouse=True)
def _use_known_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        middleware,
        "settings",
        SimpleNamespace(jwt_secret=JWT_SECRET),
    )


def _claims(*, expires_in: timedelta = timedelta(minutes=5)) -> dict[str, Any]:
    return {
        "sub": USER_ID,
        "exp": datetime.now(timezone.utc) + expires_in,
    }


def _authorization(token: str) -> str:
    return f"Bearer {token}"


def test_extract_user_id_accepts_valid_hs256_token() -> None:
    token = jwt.encode(_claims(), JWT_SECRET, algorithm="HS256")

    assert middleware._extract_user_id_from_token(_authorization(token)) == USER_ID


def test_extract_user_id_rejects_invalid_signature_without_raising() -> None:
    token = jwt.encode(
        _claims(),
        "different-signing-secret-at-least-32-characters",
        algorithm="HS256",
    )

    assert middleware._extract_user_id_from_token(_authorization(token)) is None


def test_extract_user_id_rejects_expired_token_without_raising() -> None:
    token = jwt.encode(
        _claims(expires_in=timedelta(seconds=-1)),
        JWT_SECRET,
        algorithm="HS256",
    )

    assert middleware._extract_user_id_from_token(_authorization(token)) is None


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_extract_user_id_rejects_algorithms_outside_hs256_allowlist(
    algorithm: str,
) -> None:
    token = jwt.encode(_claims(), JWT_SECRET, algorithm=algorithm)

    assert middleware._extract_user_id_from_token(_authorization(token)) is None


def test_extract_user_id_rejects_unsigned_none_algorithm() -> None:
    token = jwt.encode(_claims(), key="", algorithm="none")

    assert middleware._extract_user_id_from_token(_authorization(token)) is None


def test_extract_user_id_preserves_claim_rejection_and_missing_subject_behavior() -> None:
    unexpected_audience = jwt.encode(
        {**_claims(), "aud": ["unexpected-audience"]},
        JWT_SECRET,
        algorithm="HS256",
    )
    missing_subject = jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        JWT_SECRET,
        algorithm="HS256",
    )

    assert middleware._extract_user_id_from_token(_authorization(unexpected_audience)) is None
    assert middleware._extract_user_id_from_token(_authorization(missing_subject)) is None


def test_pyjwt_is_direct_and_python_jose_stack_is_absent_from_manifests() -> None:
    production = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    development = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    geo = (REPO_ROOT / "requirements-geo.txt").read_text(encoding="utf-8")
    middleware_source = (REPO_ROOT / "app/core/middleware.py").read_text(encoding="utf-8")
    manifests = "\n".join((production, development, geo)).lower()

    assert "PyJWT[crypto]>=2.11.0,<3.0.0" in production
    assert "python-jose" not in manifests
    assert "types-python-jose" not in manifests
    assert "ecdsa" not in manifests
    assert "from jose import" not in middleware_source
    assert "from jwt import PyJWTError" in middleware_source
