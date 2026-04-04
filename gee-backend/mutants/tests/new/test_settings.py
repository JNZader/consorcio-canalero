"""Tests for the settings domain (models, repository, service, router)."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.settings.models import CategoriaSettings, SystemSettings
from app.domains.settings.repository import SettingsRepository
from app.domains.settings.schemas import (
    BrandingResponse,
    SettingResponse,
    SettingsByCategoryResponse,
    SettingUpdate,
)
from app.domains.settings.service import SettingsService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def repo() -> SettingsRepository:
    return SettingsRepository()


@pytest.fixture
def service(repo: SettingsRepository) -> SettingsService:
    return SettingsService(repository=repo)


def _make_setting(
    db: Session,
    repo: SettingsRepository,
    *,
    clave: str = "test/key",
    valor="test_value",
    categoria: str = "general",
    descripcion: str | None = "A test setting",
) -> SystemSettings:
    """Helper to insert a setting and return it."""
    setting = repo.upsert(
        db,
        clave=clave,
        valor=valor,
        categoria=categoria,
        descripcion=descripcion,
    )
    db.flush()
    return setting


# ──────────────────────────────────────────────
# MODEL TESTS
# ──────────────────────────────────────────────


class TestSystemSettingsModel:
    def test_repr(self, db: Session, repo: SettingsRepository):
        setting = _make_setting(db, repo, clave="general/nombre")
        assert "general/nombre" in repr(setting)
        assert "general" in repr(setting)

    def test_categoria_enum_values(self):
        assert CategoriaSettings.GENERAL.value == "general"
        assert CategoriaSettings.BRANDING.value == "branding"
        assert CategoriaSettings.TERRITORIO.value == "territorio"
        assert CategoriaSettings.ANALISIS.value == "analisis"
        assert CategoriaSettings.CONTACTO.value == "contacto"


# ──────────────────────────────────────────────
# REPOSITORY TESTS
# ──────────────────────────────────────────────


class TestSettingsRepository:
    def test_upsert_creates_new(self, db: Session, repo: SettingsRepository):
        setting = _make_setting(db, repo, clave="test/new")
        assert setting.id is not None
        assert setting.clave == "test/new"
        assert setting.valor == "test_value"

    def test_upsert_updates_existing(self, db: Session, repo: SettingsRepository):
        _make_setting(db, repo, clave="test/upsert", valor="old")
        updated = repo.upsert(
            db,
            clave="test/upsert",
            valor="new",
            categoria="general",
            descripcion="updated desc",
        )
        db.flush()
        assert updated.valor == "new"
        assert updated.descripcion == "updated desc"

    def test_get_by_key_found(self, db: Session, repo: SettingsRepository):
        _make_setting(db, repo, clave="test/find_me")
        result = repo.get_by_key(db, "test/find_me")
        assert result is not None
        assert result.clave == "test/find_me"

    def test_get_by_key_not_found(self, db: Session, repo: SettingsRepository):
        result = repo.get_by_key(db, "nonexistent/key")
        assert result is None

    def test_get_all(self, db: Session, repo: SettingsRepository):
        _make_setting(db, repo, clave="a/first", categoria="general")
        _make_setting(db, repo, clave="b/second", categoria="branding")
        results = repo.get_all(db)
        assert len(results) >= 2
        # Verify ordering: by category then key
        claves = [s.clave for s in results]
        assert claves.index("b/second") > claves.index("a/first")  # branding > general

    def test_get_by_category(self, db: Session, repo: SettingsRepository):
        _make_setting(db, repo, clave="branding/test1", categoria="branding")
        _make_setting(db, repo, clave="general/test2", categoria="general")
        branding = repo.get_by_category(db, "branding")
        claves = [s.clave for s in branding]
        assert "branding/test1" in claves
        assert "general/test2" not in claves

    def test_get_by_category_empty(self, db: Session, repo: SettingsRepository):
        results = repo.get_by_category(db, "contacto")
        # May or may not be empty depending on other tests, but should not error
        assert isinstance(results, list)

    def test_upsert_json_value(self, db: Session, repo: SettingsRepository):
        """Settings can store complex JSON values."""
        setting = _make_setting(
            db, repo, clave="test/json", valor={"nested": [1, 2, 3]}
        )
        assert setting.valor == {"nested": [1, 2, 3]}

    def test_upsert_preserves_descripcion_when_none(
        self, db: Session, repo: SettingsRepository
    ):
        """If descripcion is None on upsert, the original description is kept."""
        _make_setting(db, repo, clave="test/desc", descripcion="original")
        repo.upsert(
            db,
            clave="test/desc",
            valor="new_val",
            categoria="general",
            descripcion=None,
        )
        db.flush()
        result = repo.get_by_key(db, "test/desc")
        assert result is not None
        assert result.descripcion == "original"


# ──────────────────────────────────────────────
# SERVICE TESTS
# ──────────────────────────────────────────────


class TestSettingsService:
    def test_get_setting_returns_value(self, db: Session, service: SettingsService):
        _make_setting(db, service.repo, clave="svc/test", valor=42)
        assert service.get_setting(db, "svc/test") == 42

    def test_get_setting_returns_default(self, db: Session, service: SettingsService):
        result = service.get_setting(db, "nonexistent/key", default="fallback")
        assert result == "fallback"

    def test_get_setting_returns_none_default(
        self, db: Session, service: SettingsService
    ):
        result = service.get_setting(db, "nonexistent/key")
        assert result is None

    def test_get_setting_full(self, db: Session, service: SettingsService):
        _make_setting(db, service.repo, clave="svc/full")
        result = service.get_setting_full(db, "svc/full")
        assert result is not None
        assert isinstance(result, SystemSettings)

    def test_get_setting_full_not_found(self, db: Session, service: SettingsService):
        result = service.get_setting_full(db, "nonexistent/key")
        assert result is None

    def test_update_setting_success(self, db: Session, service: SettingsService):
        _make_setting(db, service.repo, clave="svc/update", valor="old")
        updated = service.update_setting(db, "svc/update", "new_value")
        assert updated is not None
        assert updated.valor == "new_value"

    def test_update_setting_not_found(self, db: Session, service: SettingsService):
        result = service.update_setting(db, "nonexistent/key", "value")
        assert result is None

    def test_update_setting_with_description(
        self, db: Session, service: SettingsService
    ):
        _make_setting(db, service.repo, clave="svc/desc_update", valor="v1")
        updated = service.update_setting(
            db, "svc/desc_update", "v2", descripcion="new desc"
        )
        assert updated is not None
        assert updated.descripcion == "new desc"

    def test_get_all_settings(self, db: Session, service: SettingsService):
        _make_setting(db, service.repo, clave="svc/all1")
        _make_setting(db, service.repo, clave="svc/all2")
        results = service.get_all_settings(db)
        assert len(results) >= 2

    def test_get_settings_by_category(self, db: Session, service: SettingsService):
        _make_setting(db, service.repo, clave="territorio/svc", categoria="territorio")
        results = service.get_settings_by_category(db, "territorio")
        assert any(s.clave == "territorio/svc" for s in results)


# ──────────────────────────────────────────────
# SEED DEFAULTS TESTS
# ──────────────────────────────────────────────


class TestSeedDefaults:
    def test_seed_creates_all_defaults(self, db: Session):
        created = SettingsService.seed_defaults(db)
        assert created >= 13  # We defined 13 default settings

        # Verify a few key settings exist
        repo = SettingsRepository()
        org = repo.get_by_key(db, "general/nombre_organizacion")
        assert org is not None
        assert org.valor == "Consorcio Canalero 10 de Mayo"

        bbox = repo.get_by_key(db, "territorio/aoi_bbox")
        assert bbox is not None
        assert bbox.valor == [-64.1, -33.9, -63.7, -33.5]

        threshold = repo.get_by_key(db, "analisis/flow_acc_threshold")
        assert threshold is not None
        assert threshold.valor == 1000

    def test_seed_is_idempotent(self, db: Session):
        """Running seed twice should not duplicate settings."""
        first = SettingsService.seed_defaults(db)
        second = SettingsService.seed_defaults(db)
        assert first >= 13
        assert second == 0  # All already exist

    def test_seed_preserves_existing_values(self, db: Session):
        """If a setting was modified, seeding should not overwrite it."""
        repo = SettingsRepository()
        repo.upsert(
            db,
            clave="general/nombre_organizacion",
            valor="Custom Name",
            categoria="general",
        )
        db.flush()

        SettingsService.seed_defaults(db)

        setting = repo.get_by_key(db, "general/nombre_organizacion")
        assert setting is not None
        assert setting.valor == "Custom Name"  # Not overwritten


# ──────────────────────────────────────────────
# SCHEMA TESTS
# ──────────────────────────────────────────────


class TestSettingsSchemas:
    def test_setting_response_from_orm(self, db: Session, repo: SettingsRepository):
        setting = _make_setting(db, repo, clave="schema/test")
        response = SettingResponse.model_validate(setting)
        assert response.clave == "schema/test"
        assert response.id is not None

    def test_setting_update_validation(self):
        update = SettingUpdate(valor={"key": "value"})
        assert update.valor == {"key": "value"}
        assert update.descripcion is None

    def test_setting_update_with_description(self):
        update = SettingUpdate(valor=42, descripcion="A number")
        assert update.valor == 42
        assert update.descripcion == "A number"

    def test_settings_by_category_response(self):
        response = SettingsByCategoryResponse(
            categoria="general", settings=[]
        )
        assert response.categoria == "general"
        assert response.settings == []

    def test_branding_response(self):
        branding = BrandingResponse(
            nombre_organizacion="Test Org",
            logo_url="/logo.png",
            color_primario="#FF0000",
            color_secundario="#00FF00",
        )
        assert branding.nombre_organizacion == "Test Org"
        assert branding.color_primario == "#FF0000"

    def test_branding_response_defaults_to_none(self):
        branding = BrandingResponse()
        assert branding.nombre_organizacion is None
        assert branding.logo_url is None


# ──────────────────────────────────────────────
# PUBLIC BRANDING ENDPOINT TESTS (unit-level)
# ──────────────────────────────────────────────


class TestPublicBranding:
    def test_branding_from_seeded_data(self, db: Session):
        """After seeding, branding values should be available."""
        SettingsService.seed_defaults(db)
        service = SettingsService()

        branding = BrandingResponse(
            nombre_organizacion=service.get_setting(
                db, "general/nombre_organizacion"
            ),
            logo_url=service.get_setting(db, "branding/logo_url"),
            color_primario=service.get_setting(db, "branding/color_primario"),
            color_secundario=service.get_setting(
                db, "branding/color_secundario"
            ),
        )
        assert branding.nombre_organizacion == "Consorcio Canalero 10 de Mayo"
        assert branding.logo_url == "/static/logo.png"
        assert branding.color_primario == "#1976D2"
        assert branding.color_secundario == "#424242"

    def test_branding_with_no_data(self, db: Session):
        """If no settings exist, branding returns None values."""
        service = SettingsService()
        branding = BrandingResponse(
            nombre_organizacion=service.get_setting(
                db, "general/nombre_organizacion"
            ),
            logo_url=service.get_setting(db, "branding/logo_url"),
            color_primario=service.get_setting(db, "branding/color_primario"),
            color_secundario=service.get_setting(
                db, "branding/color_secundario"
            ),
        )
        assert branding.nombre_organizacion is None
        assert branding.logo_url is None
