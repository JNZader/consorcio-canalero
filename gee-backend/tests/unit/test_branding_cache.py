"""The branding cache hands callers a private dict and keeps invalidations."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest

import app.domains.settings.service as settings_mod
from app.domains.settings.service import SettingsService

_VALUES = {
    "general/nombre_organizacion": "Consorcio",
    "branding/logo_url": "/static/logo.png",
    "branding/color_primario": "#1976D2",
    "branding/color_secundario": "#424242",
}
_PUBLIC = {
    "nombre_organizacion": "Consorcio",
    "logo_url": "/static/logo.png",
    "color_primario": "#1976D2",
    "color_secundario": "#424242",
}


class _Row:
    def __init__(self) -> None:
        self.valor: Any = "viejo"
        self.descripcion: str | None = None
        self.updated_at = datetime(2026, 11, 5, tzinfo=timezone.utc)


class _Repo:
    def __init__(self) -> None:
        self.row = _Row()

    def get_by_key(self, db: object, clave: str, *, for_update: bool = False) -> _Row:
        return self.row

    def upsert(
        self,
        db: object,
        *,
        clave: str,
        valor: Any,
        categoria: str,
        descripcion: str | None = None,
    ) -> _Row:
        self.row.valor = valor
        self.row.descripcion = descripcion
        return self.row


class _Db:
    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def refresh(self, setting: object) -> None:
        return None


@pytest.fixture(autouse=True)
def _reset_branding_cache():
    settings_mod._BRANDING_CACHE = None
    settings_mod._BRANDING_CACHE_TIME = 0.0
    settings_mod._BRANDING_CACHE_GENERATION = 0
    yield
    settings_mod._BRANDING_CACHE = None
    settings_mod._BRANDING_CACHE_TIME = 0.0
    settings_mod._BRANDING_CACHE_GENERATION = 0


def test_get_branding_returns_a_copy_of_the_cached_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get_setting(_db: object, key: str, default: object = None) -> object:
        calls.append(key)
        return _VALUES.get(key, default)

    service = SettingsService(repository=_Repo())
    monkeypatch.setattr(service, "get_setting", get_setting)

    first = service.get_branding(_Db())
    cached = settings_mod._BRANDING_CACHE
    assert first == _PUBLIC
    assert cached == _PUBLIC
    assert first is not cached

    first["nombre_organizacion"] = "mutado"
    second = service.get_branding(_Db())
    assert second == _PUBLIC
    assert second is not first
    assert second is not cached
    assert cached == _PUBLIC
    assert len(calls) == 4


def test_branding_cache_reloads_after_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get_setting(_db: object, key: str, default: object = None) -> object:
        calls.append(key)
        return _VALUES.get(key, default)

    service = SettingsService(repository=_Repo())
    monkeypatch.setattr(service, "get_setting", get_setting)
    service.get_branding(_Db())
    assert len(calls) == 4

    still_fresh = settings_mod._BRANDING_CACHE_TIME + settings_mod._BRANDING_CACHE_TTL - 0.001
    monkeypatch.setattr(settings_mod.time, "time", lambda: still_fresh)
    hit = service.get_branding(_Db())
    assert hit == _PUBLIC
    assert len(calls) == 4

    expired = settings_mod._BRANDING_CACHE_TIME + settings_mod._BRANDING_CACHE_TTL
    monkeypatch.setattr(settings_mod.time, "time", lambda: expired)
    service.get_branding(_Db())
    assert len(calls) == 8


def test_only_branding_and_general_writes_drop_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_mod, "write_audit_entry_sync", lambda *args, **kwargs: None)

    def get_setting(_db: object, key: str, default: object = None) -> object:
        return _VALUES.get(key, default)

    service = SettingsService(repository=_Repo())
    monkeypatch.setattr(service, "get_setting", get_setting)
    db = _Db()

    service.get_branding(db)
    kept = settings_mod._BRANDING_CACHE
    service.update_setting(db, "territorio/srid", 4326)
    assert settings_mod._BRANDING_CACHE is kept

    service.update_setting(db, "general/nombre_organizacion", "Otro")
    assert settings_mod._BRANDING_CACHE is None

    service.get_branding(db)
    service.upsert_setting(db, "branding/logo_url", "/otro.png", "branding")
    assert settings_mod._BRANDING_CACHE is None


def _in_flight_reader_loses_to(
    service: SettingsService, drop: Callable[[], None]
) -> dict[str, Any]:
    """Prime the cache, expire it, and drop it while a reload is in flight."""
    entered = threading.Event()
    release = threading.Event()
    arm = {"block": False}
    calls: list[str] = []
    errors: list[BaseException] = []
    holder: dict[str, Any] = {}

    def get_setting(_db: object, key: str, default: object = None) -> object:
        calls.append(key)
        if arm["block"]:
            arm["block"] = False
            entered.set()
            if not release.wait(5):
                raise TimeoutError("reader was not released")
        return _VALUES.get(key, default)

    service.get_setting = get_setting
    db = _Db()
    service.get_branding(db)
    settings_mod._BRANDING_CACHE_TIME = 0.0
    arm["block"] = True

    def run() -> None:
        try:
            holder["branding"] = service.get_branding(db)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        drop()
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert errors == []
    assert settings_mod._BRANDING_CACHE is None
    holder["calls"] = calls
    return holder


def test_update_setting_invalidation_beats_an_in_flight_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings_mod, "write_audit_entry_sync", lambda *args, **kwargs: None)
    service = SettingsService(repository=_Repo())

    def drop() -> None:
        updated = service.update_setting(_Db(), "branding/color_primario", "#010101")
        assert updated is not None
        assert updated.valor == "#010101"

    holder = _in_flight_reader_loses_to(service, drop)
    assert holder["branding"] == _PUBLIC
    assert len(holder["calls"]) == 8
    holder["branding"]["nombre_organizacion"] = "mutado"

    fresh = service.get_branding(_Db())
    assert fresh == _PUBLIC
    assert fresh is not settings_mod._BRANDING_CACHE
    assert settings_mod._BRANDING_CACHE == _PUBLIC
    assert len(holder["calls"]) == 12


def test_upsert_setting_invalidation_beats_an_in_flight_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SettingsService(repository=_Repo())

    def drop() -> None:
        service.upsert_setting(
            _Db(),
            "general/nombre_organizacion",
            "Otro nombre",
            "general",
        )

    holder = _in_flight_reader_loses_to(service, drop)
    assert holder["branding"] == _PUBLIC
    assert settings_mod._BRANDING_CACHE_GENERATION == 1

    service.get_branding(_Db())
    assert settings_mod._BRANDING_CACHE == _PUBLIC
    assert settings_mod._BRANDING_CACHE_GENERATION == 1
