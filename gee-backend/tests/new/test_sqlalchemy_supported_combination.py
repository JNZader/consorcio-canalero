"""BE-12: the SQLAlchemy 2.1 override is a pinned, tested combination.

fastapi-users-db-sqlalchemy 7.0.0 still declares ``sqlalchemy<2.1``. We keep
2.1 because the User model does not use ``MappedAsDataclass``, which is the
break tracked in fastapi-users#1441. The three versions below are the
combination this tree supports. Bump them together.
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from sqlalchemy.orm import MappedAsDataclass

from app.auth.models import User

BACKEND = Path(__file__).resolve().parents[2]


def test_override_and_lock_pin_the_same_sqlalchemy() -> None:
    override = (BACKEND / "overrides.txt").read_text(encoding="utf-8")
    lock = (BACKEND / "requirements.lock").read_text(encoding="utf-8")
    dev_lock = (BACKEND / "requirements-dev.lock").read_text(encoding="utf-8")

    assert "sqlalchemy[asyncio]==2.1.6" in override
    assert "sqlalchemy==2.1.6" in lock
    assert "sqlalchemy==2.1.6" in dev_lock
    assert "fastapi-users==15.0.5" in lock
    assert "fastapi-users-db-sqlalchemy==7.0.0" in lock


def test_installed_versions_match_the_supported_combination() -> None:
    assert version("sqlalchemy") == "2.1.6"
    assert version("fastapi-users") == "15.0.5"
    assert version("fastapi-users-db-sqlalchemy") == "7.0.0"


def test_user_model_is_not_a_mapped_dataclass() -> None:
    assert not issubclass(User, MappedAsDataclass)
    assert "__dataclass_fields__" not in User.__dict__
