"""TEST-02: each pytest-xdist worker gets its own database name and catalog."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.config import settings
from tests.new.xdist_db import drop_worker_database, isolate_worker_database, worker_database_name


def test_worker_database_name_rejects_injection() -> None:
    assert worker_database_name("test_consorcio", "gw0") == "test_consorcio_gw0"
    with pytest.raises(ValueError):
        worker_database_name("test_consorcio", "gw0;drop")
    with pytest.raises(ValueError):
        worker_database_name("test_consorcio", "")


def test_isolate_without_a_worker_keeps_the_url() -> None:
    url, name = isolate_worker_database("postgresql://test:test@localhost/test_consorcio", None)
    assert url == "postgresql://test:test@localhost/test_consorcio"
    assert name is None


def test_worker_database_is_a_separate_empty_catalog() -> None:
    url, name = isolate_worker_database(settings.database_url, "gw99")
    assert name is not None and name.endswith("_gw99")
    assert name not in settings.database_url
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
            tables = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            ).scalar_one()
        assert tables == 0
    finally:
        engine.dispose()
        drop_worker_database(settings.database_url, name)
