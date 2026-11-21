"""Focused pure-python unit tests for the ``app.auth.refresh_tokens`` mutation target.

Exercises every branch (constants, hashing, token minting, expiry/replay lookup,
per-family advisory locking with lock-timeout fail-secure, CAS rotate winner +
client-drift audit + race-loss vs replay burn, and bounded multi-pass revoke-all)
with mocked AsyncSession objects so cosmic-ray runs fast with zero database.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError

from app.auth import refresh_tokens
from app.auth.refresh_tokens import (
    _LOCK_NOT_AVAILABLE_SQLSTATE,
    _LOCK_TIMEOUT_MS,
    _REVOKE_ALL_LOCK_MAX_ITERS,
    RACE_WINDOW,
    REFRESH_TOKEN_LIFETIME,
    RotateFailure,
    _hash_token,
    _is_lock_timeout,
    _lock_family,
    _new_raw_token,
    find_active,
    issue_token,
    revoke_all_for_user,
    revoke_family,
    rotate,
)


def _compile_sql(stmt: object) -> str:
    return str(
        stmt.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _session_mock(execute_side_effect=None) -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    if execute_side_effect is None:
        session.execute = AsyncMock()
    else:
        session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


def _scalar_result(value: object) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none.return_value = value
    return res


def _first_result(value: object) -> MagicMock:
    res = MagicMock()
    res.first.return_value = value
    return res


def _all_result(rows: list[object]) -> MagicMock:
    res = MagicMock()
    res.all.return_value = rows
    return res


def _rowcount_result(rowcount: int | None) -> MagicMock:
    return SimpleNamespace(rowcount=rowcount)


def _user(user_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=user_id or uuid.uuid4())


class TestConstantsAndHelpers:
    def test_contract_constants(self) -> None:
        assert REFRESH_TOKEN_LIFETIME == timedelta(days=30)
        assert _LOCK_TIMEOUT_MS == 5000
        assert _LOCK_NOT_AVAILABLE_SQLSTATE == "55P03"
        assert _REVOKE_ALL_LOCK_MAX_ITERS == 10
        assert RACE_WINDOW == timedelta(seconds=5)
        assert RotateFailure.INVALID.value == "invalid"
        assert RotateFailure.REPLAY.value == "replay"
        assert RotateFailure.RACE_LOST.value == "race_lost"

    def test_is_lock_timeout_matches_only_sqlstate_55p03(self) -> None:
        err_match = DBAPIError.__new__(DBAPIError)
        err_match.orig = SimpleNamespace(sqlstate="55P03")  # type: ignore[assignment]
        assert _is_lock_timeout(err_match) is True

        err_deadlock = DBAPIError.__new__(DBAPIError)
        err_deadlock.orig = SimpleNamespace(sqlstate="40P01")  # type: ignore[assignment]
        assert _is_lock_timeout(err_deadlock) is False

        err_no_orig = DBAPIError.__new__(DBAPIError)
        err_no_orig.orig = None
        assert _is_lock_timeout(err_no_orig) is False

        err_no_sqlstate = DBAPIError.__new__(DBAPIError)
        err_no_sqlstate.orig = Exception("plain")
        assert _is_lock_timeout(err_no_sqlstate) is False

    def test_hash_and_new_raw_token(self) -> None:
        assert _hash_token("secret-token") == hashlib.sha256(b"secret-token").hexdigest()
        assert len(_hash_token("secret-token")) == 64
        assert _hash_token("secret-token") != _hash_token("other-token")

        t1 = _new_raw_token()
        t2 = _new_raw_token()
        assert isinstance(t1, str)
        assert len(t1) == 43
        assert t1 != t2


class TestIssueToken:
    def test_issue_token_commits_and_refreshes_by_default(self) -> None:
        session = _session_mock()
        user = _user()

        raw, row = asyncio.run(
            issue_token(
                session,
                user=user,  # type: ignore[arg-type]
                user_agent="A" * 300,
                client_ip="9" * 90,
            )
        )

        session.add.assert_called_once_with(row)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(row)
        session.flush.assert_not_awaited()
        assert row.user_id == user.id
        assert row.token_hash == _hash_token(raw)
        assert isinstance(row.family_id, uuid.UUID)
        assert row.revoked is False
        assert row.expires_at - row.created_at == timedelta(days=30)
        assert row.user_agent == "A" * 255
        assert row.client_ip == "9" * 64

    def test_issue_token_flush_path_and_empty_metadata_to_none(self) -> None:
        session = _session_mock()
        user = _user()
        fid = uuid.uuid4()

        _raw, row = asyncio.run(
            issue_token(
                session,
                user=user,  # type: ignore[arg-type]
                family_id=fid,
                user_agent="",
                client_ip="",
                commit=False,
            )
        )

        session.add.assert_called_once_with(row)
        session.flush.assert_awaited_once()
        session.commit.assert_not_awaited()
        session.refresh.assert_not_awaited()
        assert row.family_id == fid
        assert row.user_agent is None
        assert row.client_ip is None


class TestFindActive:
    def test_returns_none_when_missing_in_db(self) -> None:
        session = _session_mock([_scalar_result(None)])
        assert asyncio.run(find_active(session, "raw-missing")) is None
        sql = _compile_sql(session.execute.call_args.args[0])
        assert f"refresh_tokens.token_hash = '{_hash_token('raw-missing')}'" in sql

    def test_returns_revoked_row_even_if_expired_for_replay_signal(self) -> None:
        row = SimpleNamespace(
            revoked=True,
            expires_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
        )
        session = _session_mock([_scalar_result(row)])
        assert asyncio.run(find_active(session, "raw-revoked")) is row

    def test_returns_none_when_expired_or_at_exact_expiry_boundary(self) -> None:
        fixed_now = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
        row_equal = SimpleNamespace(revoked=False, expires_at=fixed_now)
        session = _session_mock([_scalar_result(row_equal)])
        with patch.object(refresh_tokens, "datetime") as dt_mock:
            dt_mock.now.return_value = fixed_now
            assert asyncio.run(find_active(session, "raw-boundary")) is None

        row_expired = SimpleNamespace(
            revoked=False,
            expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session2 = _session_mock([_scalar_result(row_expired)])
        assert asyncio.run(find_active(session2, "raw-expired")) is None

    def test_returns_row_when_active_and_unexpired(self) -> None:
        row = SimpleNamespace(
            revoked=False,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=10),
        )
        session = _session_mock([_scalar_result(row)])
        assert asyncio.run(find_active(session, "raw-ok")) is row


class TestLocksAndRevokeFamily:
    def test_lock_family_sets_local_timeout_then_advisory_lock(self) -> None:
        session = _session_mock([None, None])
        fid = uuid.uuid4()
        asyncio.run(_lock_family(session, fid))

        assert session.execute.await_count == 2
        timeout_stmt = str(session.execute.call_args_list[0].args[0])
        lock_stmt = _compile_sql(session.execute.call_args_list[1].args[0])
        assert "SET LOCAL lock_timeout = '5000'" in timeout_stmt
        assert "pg_advisory_xact_lock" in lock_stmt
        assert "hashtext" in lock_stmt
        assert str(fid) in lock_stmt

    def test_revoke_family_locks_updates_commits_and_returns_count(self) -> None:
        fid = uuid.uuid4()
        session = _session_mock([None, None, _rowcount_result(4)])
        count = asyncio.run(revoke_family(session, fid))

        assert count == 4
        session.commit.assert_awaited_once()
        update_sql = _compile_sql(session.execute.call_args_list[2].args[0])
        assert f"refresh_tokens.family_id = '{fid}'" in update_sql
        assert "refresh_tokens.revoked IS false" in update_sql
        assert "SET revoked=true" in update_sql

    def test_revoke_family_handles_none_and_missing_rowcount(self) -> None:
        session_none = _session_mock([None, None, _rowcount_result(None)])
        assert asyncio.run(revoke_family(session_none, uuid.uuid4())) == 0
        session_missing = _session_mock([None, None, SimpleNamespace()])
        assert asyncio.run(revoke_family(session_missing, uuid.uuid4())) == 0


class TestRotate:
    def test_unknown_token_returns_invalid_without_locking(self) -> None:
        session = _session_mock([_first_result(None)])
        result = asyncio.run(
            rotate(session, raw_token="missing", user=_user())  # type: ignore[arg-type]
        )
        assert result is RotateFailure.INVALID
        assert session.execute.await_count == 1
        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

    def test_lock_timeout_55p03_rolls_back_and_returns_invalid(self) -> None:
        fid = uuid.uuid4()
        lock_err = DBAPIError.__new__(DBAPIError)
        lock_err.orig = SimpleNamespace(sqlstate="55P03")  # type: ignore[assignment]

        session = _session_mock([_first_result(SimpleNamespace(family_id=fid)), None, lock_err])
        result = asyncio.run(
            rotate(session, raw_token="tok", user=_user())  # type: ignore[arg-type]
        )
        assert result is RotateFailure.INVALID
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    def test_non_timeout_db_error_re_raises(self) -> None:
        fid = uuid.uuid4()
        deadlock = DBAPIError.__new__(DBAPIError)
        deadlock.orig = SimpleNamespace(sqlstate="40P01")  # type: ignore[assignment]

        session = _session_mock([_first_result(SimpleNamespace(family_id=fid)), None, deadlock])
        with pytest.raises(DBAPIError):
            asyncio.run(rotate(session, raw_token="tok", user=_user()))  # type: ignore[arg-type]
        session.rollback.assert_not_awaited()

    def test_winner_same_client_skips_audit_and_commits_successor(self) -> None:
        fid = uuid.uuid4()
        user = _user()
        stored_ua = "U" * 255
        stored_ip = "I" * 64
        winner = SimpleNamespace(
            id=uuid.uuid4(), family_id=fid, user_agent=stored_ua, client_ip=stored_ip
        )
        session = _session_mock(
            [
                _first_result(SimpleNamespace(family_id=fid)),
                None,
                None,
                _first_result(winner),
            ]
        )

        with patch.object(refresh_tokens, "write_audit_entry_async", new=AsyncMock()) as audit_mock:
            out = asyncio.run(
                rotate(
                    session,
                    raw_token="old-tok",
                    user=user,  # type: ignore[arg-type]
                    user_agent=("U" * 255) + "tail",
                    client_ip=("I" * 64) + "99",
                )
            )

        assert isinstance(out, tuple)
        new_raw, new_row = out
        assert new_raw != "old-tok"
        assert new_row.family_id == fid
        assert new_row.user_id == user.id
        audit_mock.assert_not_awaited()
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(new_row)

        lookup_sql = _compile_sql(session.execute.call_args_list[0].args[0])
        assert f"refresh_tokens.token_hash = '{_hash_token('old-tok')}'" in lookup_sql

        cas_sql = _compile_sql(session.execute.call_args_list[3].args[0])
        assert f"refresh_tokens.token_hash = '{_hash_token('old-tok')}'" in cas_sql
        assert "refresh_tokens.revoked IS false" in cas_sql
        assert f"refresh_tokens.user_id = '{user.id}'" in cas_sql
        assert "refresh_tokens.expires_at > " in cas_sql
        assert "SET revoked=true" in cas_sql

    def test_winner_empty_vs_none_normalization_does_not_audit(self) -> None:
        fid = uuid.uuid4()
        winner = SimpleNamespace(id=uuid.uuid4(), family_id=fid, user_agent=None, client_ip=None)
        session = _session_mock(
            [
                _first_result(SimpleNamespace(family_id=fid)),
                None,
                None,
                _first_result(winner),
            ]
        )
        with patch.object(refresh_tokens, "write_audit_entry_async", new=AsyncMock()) as audit_mock:
            out = asyncio.run(
                rotate(
                    session,
                    raw_token="tok",
                    user=_user(),  # type: ignore[arg-type]
                    user_agent="",
                    client_ip="",
                )
            )
        assert isinstance(out, tuple)
        audit_mock.assert_not_awaited()

    @pytest.mark.parametrize(
        ("old_ua", "new_ua", "old_ip", "new_ip", "expected_changed"),
        [
            ("Firefox", "Chrome", "10.0.0.1", "10.0.0.1", "changed=ua "),
            ("Firefox", "Firefox", "10.0.0.1", "10.0.0.2", "changed=ip "),
            ("Firefox", "Chrome", "10.0.0.1", "10.0.0.2", "changed=ua+ip "),
        ],
    )
    def test_winner_client_drift_logs_audit_and_still_rotates(
        self,
        old_ua: str,
        new_ua: str,
        old_ip: str,
        new_ip: str,
        expected_changed: str,
    ) -> None:
        fid = uuid.uuid4()
        user = _user()
        winner = SimpleNamespace(
            id=uuid.uuid4(), family_id=fid, user_agent=old_ua, client_ip=old_ip
        )
        session = _session_mock(
            [
                _first_result(SimpleNamespace(family_id=fid)),
                None,
                None,
                _first_result(winner),
            ]
        )
        with patch.object(refresh_tokens, "write_audit_entry_async", new=AsyncMock()) as audit_mock:
            out = asyncio.run(
                rotate(
                    session,
                    raw_token="tok",
                    user=user,  # type: ignore[arg-type]
                    user_agent=new_ua,
                    client_ip=new_ip,
                )
            )
        assert isinstance(out, tuple)
        audit_mock.assert_awaited_once()
        kwargs = audit_mock.call_args.kwargs
        assert kwargs["user_id"] == user.id
        assert kwargs["action"] == "refresh.rotate.client-change"
        assert expected_changed in kwargs["resource"]
        assert f"family_id={fid}" in kwargs["resource"]
        assert kwargs["client_ip"] == new_ip

    @pytest.mark.parametrize(
        "replay_row",
        [
            None,
            SimpleNamespace(revoked=False, revoked_at=None, family_id=uuid.uuid4()),
        ],
    )
    def test_cas_loser_unrevoked_or_missing_returns_invalid(self, replay_row: object) -> None:
        fid = uuid.uuid4()
        session = _session_mock(
            [
                _first_result(SimpleNamespace(family_id=fid)),
                None,
                None,
                _first_result(None),
                _scalar_result(replay_row),
            ]
        )
        res = asyncio.run(rotate(session, raw_token="tok", user=_user()))  # type: ignore[arg-type]
        assert res is RotateFailure.INVALID
        session.commit.assert_awaited_once()
        assert session.execute.await_count == 5

    def test_cas_loser_old_revocation_burns_family_and_returns_replay(self) -> None:
        fid = uuid.uuid4()
        old_revoked_at = datetime.now(tz=timezone.utc) - timedelta(seconds=10)
        replay_row = SimpleNamespace(revoked=True, revoked_at=old_revoked_at, family_id=fid)
        session = _session_mock(
            [
                _first_result(SimpleNamespace(family_id=fid)),
                None,
                None,
                _first_result(None),
                _scalar_result(replay_row),
                None,
            ]
        )
        res = asyncio.run(rotate(session, raw_token="tok", user=_user()))  # type: ignore[arg-type]
        assert res is RotateFailure.REPLAY
        session.commit.assert_awaited_once()
        replay_lookup_sql = _compile_sql(session.execute.call_args_list[4].args[0])
        assert f"refresh_tokens.token_hash = '{_hash_token('tok')}'" in replay_lookup_sql
        burn_sql = _compile_sql(session.execute.call_args_list[5].args[0])
        assert f"refresh_tokens.family_id = '{fid}'" in burn_sql
        assert "refresh_tokens.revoked IS false" in burn_sql
        assert "SET revoked=true" in burn_sql
        assert "false" not in burn_sql.split("WHERE", 1)[1].lower().replace("revoked is false", "")

    def test_cas_loser_none_revoked_at_burns_legacy_row_as_replay(self) -> None:
        fid = uuid.uuid4()
        replay_row = SimpleNamespace(revoked=True, revoked_at=None, family_id=fid)
        session = _session_mock(
            [
                _first_result(SimpleNamespace(family_id=fid)),
                None,
                None,
                _first_result(None),
                _scalar_result(replay_row),
                None,
            ]
        )
        res = asyncio.run(rotate(session, raw_token="tok", user=_user()))  # type: ignore[arg-type]
        assert res is RotateFailure.REPLAY

    def test_cas_loser_recent_or_exact_race_window_spares_family(self) -> None:
        fid = uuid.uuid4()
        fixed_now = datetime(2026, 11, 21, 12, 0, 10, tzinfo=timezone.utc)
        exact_boundary = fixed_now - RACE_WINDOW
        replay_row = SimpleNamespace(revoked=True, revoked_at=exact_boundary, family_id=fid)
        session = _session_mock(
            [
                _first_result(SimpleNamespace(family_id=fid)),
                None,
                None,
                _first_result(None),
                _scalar_result(replay_row),
                None,
            ]
        )
        with patch.object(refresh_tokens, "datetime") as dt_mock:
            dt_mock.now.return_value = fixed_now
            res = asyncio.run(rotate(session, raw_token="tok", user=_user()))  # type: ignore[arg-type]
        assert res is RotateFailure.RACE_LOST
        session.commit.assert_awaited_once()
        noop_sql = _compile_sql(session.execute.call_args_list[5].args[0])
        assert "false" in noop_sql.lower()


class TestRevokeAllForUser:
    def test_locks_families_in_sorted_order_skips_held_and_does_not_commit(self) -> None:
        uid = uuid.uuid4()
        fid1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        fid2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
        fid3 = uuid.UUID("00000000-0000-0000-0000-000000000003")

        # Iteration 1 finds [fid2, fid1], locks fid1 then fid2 (2 execute calls each = 4)
        # Iteration 2 finds [fid1, fid3], locks only fid3 (2 execute calls)
        # Iteration 3 finds [] -> stops -> final user-wide UPDATE
        session = _session_mock(
            [
                _all_result([(fid2,), (fid1,)]),
                None,
                None,
                None,
                None,
                _all_result([(fid1,), (fid3,)]),
                None,
                None,
                _all_result([]),
                _rowcount_result(5),
            ]
        )

        count = asyncio.run(revoke_all_for_user(session, uid))
        assert count == 5
        session.commit.assert_not_awaited()
        select_sql = _compile_sql(session.execute.call_args_list[0].args[0])
        assert f"refresh_tokens.user_id = '{uid}'" in select_sql
        assert "refresh_tokens.revoked IS false" in select_sql
        lock1_sql = _compile_sql(session.execute.call_args_list[2].args[0])
        lock2_sql = _compile_sql(session.execute.call_args_list[4].args[0])
        assert str(fid1) in lock1_sql
        assert str(fid2) in lock2_sql
        final_update_sql = _compile_sql(session.execute.call_args_list[9].args[0])
        assert f"refresh_tokens.user_id = '{uid}'" in final_update_sql
        assert "refresh_tokens.revoked IS false" in final_update_sql
        assert "SET revoked=true" in final_update_sql

    def test_respects_max_iterations_cap_and_returns_zero_for_none_and_missing_rowcount(
        self,
    ) -> None:
        uid = uuid.uuid4()
        calls = 0

        async def _execute(stmt: object) -> object:
            nonlocal calls
            calls += 1
            sql = str(stmt)
            if sql.lstrip().upper().startswith("UPDATE"):
                return _rowcount_result(None)
            if "pg_advisory_xact_lock" in sql or "SET LOCAL" in sql:
                return None
            # Fresh unseen family on every SELECT pass to pressure the loop cap.
            return _all_result([(uuid.uuid4(),)])

        session = _session_mock()
        session.execute = AsyncMock(side_effect=_execute)
        count = asyncio.run(revoke_all_for_user(session, uid))

        assert count == 0
        # 10 iterations * 3 calls (select + set timeout + xact lock) + 1 final UPDATE = 31 calls
        assert calls == _REVOKE_ALL_LOCK_MAX_ITERS * 3 + 1

        # Missing rowcount attribute still defaults cleanly to 0
        session_missing = _session_mock([_all_result([]), SimpleNamespace()])
        assert asyncio.run(revoke_all_for_user(session_missing, uid)) == 0
