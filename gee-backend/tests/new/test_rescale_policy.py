"""Pure unit tests for the bounded rescale policy (hardening H1).

These exercise the single source of truth in ``app.domains.geo.rescale_policy``
without any HTTP surface, so they run regardless of whether rio-tiler is
installed. They pin the contract that the public proxy and the geo-worker both
consume: validation returns 4xx for malformed/unsupported input, and the
cache-key token is always a bounded short string (never a raw float).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domains.geo import rescale_policy as policy


def _assert_400(fn, *args):
    with pytest.raises(HTTPException) as exc:
        fn(*args)
    assert exc.value.status_code == 400


# ── valid canonical pairs (precip_normal) ────────────────────────────────────


def test_valid_monthly_pair_is_accepted_and_canonical():
    out = policy.validate_rescale("precip_normal", 0.0, 200.0)
    assert out == (0.0, 200.0)


def test_valid_annual_pair_is_accepted_and_canonical():
    out = policy.validate_rescale("precip_normal", 0.0, 1800.0)
    assert out == (0.0, 1800.0)


def test_no_rescale_returns_none_preserving_default():
    assert policy.validate_rescale("precip_normal", None, None) is None
    assert policy.validate_rescale("dem_raw", None, None) is None


# ── both-or-neither ──────────────────────────────────────────────────────────


def test_only_min_supplied_is_rejected():
    _assert_400(policy.validate_rescale, "precip_normal", 0.0, None)


def test_only_max_supplied_is_rejected():
    _assert_400(policy.validate_rescale, "precip_normal", None, 200.0)


# ── equal / inverted ranges ──────────────────────────────────────────────────


def test_equal_range_is_rejected():
    _assert_400(policy.validate_rescale, "precip_normal", 200.0, 200.0)


def test_inverted_range_is_rejected():
    _assert_400(policy.validate_rescale, "precip_normal", 200.0, 0.0)


# ── non-finite values ────────────────────────────────────────────────────────


def test_nan_is_rejected():
    _assert_400(policy.validate_rescale, "precip_normal", float("nan"), 200.0)
    _assert_400(policy.validate_rescale, "precip_normal", 0.0, float("nan"))


def test_infinity_is_rejected():
    _assert_400(policy.validate_rescale, "precip_normal", float("-inf"), 200.0)
    _assert_400(policy.validate_rescale, "precip_normal", 0.0, float("inf"))


# ── unsupported pairs / layers ───────────────────────────────────────────────


def test_unsupported_pair_for_precip_normal_is_rejected():
    _assert_400(policy.validate_rescale, "precip_normal", 0.0, 100.0)


def test_any_rescale_on_non_whitelisted_layer_is_rejected():
    _assert_400(policy.validate_rescale, "dem_raw", 0.0, 200.0)
    _assert_400(policy.validate_rescale, "twi", 0.0, 13.0)


# ── cache-key token is always bounded (never a raw float) ────────────────────


@pytest.mark.parametrize(
    "rmin,rmax,expected",
    [
        (None, None, "-"),
        (0.0, 200.0, "m"),
        (0.0, 1800.0, "a"),
        (0.0, 100.0, "-"),  # unsupported pair
        (200.0, 0.0, "-"),  # inverted
        (200.0, 200.0, "-"),  # equal
        (float("nan"), 200.0, "-"),  # non-finite
        (0.0, float("inf"), "-"),  # non-finite
        (1e9, 2e9, "-"),  # arbitrary attacker floats
    ],
)
def test_cache_token_is_always_bounded(rmin, rmax, expected):
    assert policy.rescale_cache_token(rmin, rmax) == expected


def test_cache_token_never_contains_raw_float():
    for rmin, rmax in [(1.23456789, 9.87654321), (float("inf"), 5.0), (-3.5, 3.5)]:
        token = policy.rescale_cache_token(rmin, rmax)
        assert token in {"-", "m", "a"}


# ── worker render resolution degrades safely to default ──────────────────────


def test_resolved_rescale_returns_canonical_pair():
    assert policy.resolved_rescale("precip_normal", 0.0, 200.0) == (0.0, 200.0)
    assert policy.resolved_rescale("precip_normal", 0.0, 1800.0) == (0.0, 1800.0)


def test_resolved_rescale_is_none_for_unsupported_or_missing():
    assert policy.resolved_rescale("precip_normal", 0.0, 100.0) is None
    assert policy.resolved_rescale("precip_normal", None, None) is None
    assert policy.resolved_rescale("dem_raw", 0.0, 200.0) is None
    assert policy.resolved_rescale("precip_normal", float("nan"), 5.0) is None
