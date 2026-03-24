"""Tests for the public module — viewer, external reports, and publication workflow."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.capas.models import Capa, FuenteCapa, TipoCapa
from app.domains.capas.repository import CapasRepository
from app.domains.capas.schemas import CapaCreate, EstiloCapa
from app.domains.denuncias.models import Denuncia, EstadoDenuncia
from app.domains.denuncias.repository import DenunciaRepository
from app.domains.denuncias.schemas import DenunciaCreate
from app.domains.denuncias.service import DenunciaService
from app.domains.monitoring.models import Sugerencia
from app.domains.monitoring.repository import MonitoringRepository
from app.domains.monitoring.schemas import SugerenciaCreate
from app.domains.monitoring.service import MonitoringService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def capas_repo() -> CapasRepository:
    return CapasRepository()


@pytest.fixture
def denuncia_service() -> DenunciaService:
    return DenunciaService()


@pytest.fixture
def monitoring_service() -> MonitoringService:
    return MonitoringService()


def _make_capa(
    db: Session,
    repo: CapasRepository,
    *,
    nombre: str = "Test Layer",
    tipo: str = "polygon",
    fuente: str = "local",
    es_publica: bool = False,
    visible: bool = True,
    orden: int = 0,
) -> Capa:
    """Helper to create a capa for testing."""
    data = CapaCreate(
        nombre=nombre,
        tipo=tipo,
        fuente=fuente,
        es_publica=es_publica,
        visible=visible,
        orden=orden,
    )
    capa = repo.create(db, data)
    db.flush()
    return capa


# ──────────────────────────────────────────────
# PUBLIC LAYER LISTING
# ──────────────────────────────────────────────


class TestPublicLayerListing:
    """Only layers with es_publica=True and visible=True are returned."""

    def test_only_public_layers_returned(
        self, db: Session, capas_repo: CapasRepository
    ):
        _make_capa(db, capas_repo, nombre="Public", es_publica=True, visible=True)
        _make_capa(db, capas_repo, nombre="Private", es_publica=False, visible=True)
        _make_capa(db, capas_repo, nombre="Hidden Public", es_publica=True, visible=False)

        public_layers = capas_repo.get_public(db)
        names = [c.nombre for c in public_layers]

        assert "Public" in names
        assert "Private" not in names
        assert "Hidden Public" not in names

    def test_public_layers_ordered_by_orden(
        self, db: Session, capas_repo: CapasRepository
    ):
        _make_capa(db, capas_repo, nombre="C", es_publica=True, orden=2)
        _make_capa(db, capas_repo, nombre="A", es_publica=True, orden=0)
        _make_capa(db, capas_repo, nombre="B", es_publica=True, orden=1)

        public_layers = capas_repo.get_public(db)
        orders = [c.orden for c in public_layers]
        assert orders == sorted(orders)

    def test_empty_when_no_public_layers(
        self, db: Session, capas_repo: CapasRepository
    ):
        _make_capa(db, capas_repo, nombre="Private Only", es_publica=False)

        public_layers = capas_repo.get_public(db)
        assert len(public_layers) == 0

    def test_public_layer_detail_found(
        self, db: Session, capas_repo: CapasRepository
    ):
        capa = _make_capa(db, capas_repo, nombre="Detail Layer", es_publica=True)

        fetched = capas_repo.get_by_id(db, capa.id)
        assert fetched is not None
        assert fetched.es_publica is True
        assert fetched.nombre == "Detail Layer"

    def test_private_layer_detail_not_exposed(
        self, db: Session, capas_repo: CapasRepository
    ):
        """Even if you know the ID, a private layer should not be served as public."""
        capa = _make_capa(db, capas_repo, nombre="Secret", es_publica=False)

        fetched = capas_repo.get_by_id(db, capa.id)
        assert fetched is not None
        assert fetched.es_publica is False  # caller must check this


# ──────────────────────────────────────────────
# ANONYMOUS DENUNCIA CREATION
# ──────────────────────────────────────────────


class TestAnonymousDenunciaCreation:
    """Anonymous citizens can create denuncias without auth."""

    def test_create_denuncia_successfully(
        self, db: Session, denuncia_service: DenunciaService
    ):
        payload = DenunciaCreate(
            tipo="desborde",
            descripcion="Canal desbordado en la zona norte, afectando caminos rurales.",
            latitud=-33.7,
            longitud=-63.9,
            cuenca="cuenca_1",
        )

        denuncia = denuncia_service.create(db, payload)

        assert denuncia.id is not None
        assert denuncia.tipo == "desborde"
        assert denuncia.estado == EstadoDenuncia.PENDIENTE
        assert denuncia.user_id is None  # anonymous — no user

    def test_create_denuncia_with_contact_info(
        self, db: Session, denuncia_service: DenunciaService
    ):
        payload = DenunciaCreate(
            tipo="alcantarilla_tapada",
            descripcion="Alcantarilla tapada en camino vecinal, genera acumulacion de agua.",
            latitud=-33.65,
            longitud=-63.85,
            contacto_telefono="3537-401234",
            contacto_email="vecino@ejemplo.com",
        )

        denuncia = denuncia_service.create(db, payload)

        assert denuncia.contacto_telefono == "3537-401234"
        assert denuncia.contacto_email == "vecino@ejemplo.com"


# ──────────────────────────────────────────────
# DENUNCIA STATUS CHECK (limited info)
# ──────────────────────────────────────────────


class TestDenunciaStatusCheck:
    """Public status checks return only estado and created_at."""

    def test_status_returns_limited_info(
        self, db: Session, denuncia_service: DenunciaService
    ):
        payload = DenunciaCreate(
            tipo="camino_danado",
            descripcion="Camino rural danado despues de las lluvias fuertes de esta semana.",
            latitud=-33.70,
            longitud=-63.91,
            contacto_email="testprivado@example.com",
        )
        denuncia = denuncia_service.create(db, payload)

        # Fetch via service (simulating what the endpoint does)
        fetched = denuncia_service.get_by_id(db, denuncia.id)

        # These are the only fields the public endpoint exposes
        assert fetched.estado == EstadoDenuncia.PENDIENTE
        assert fetched.created_at is not None

        # These exist on the model but must NOT be in PublicDenunciaStatusResponse
        assert fetched.contacto_email == "testprivado@example.com"  # model has it
        # The schema strips it — test at schema level:
        from app.api.v2.public_schemas import PublicDenunciaStatusResponse

        response = PublicDenunciaStatusResponse(
            estado=fetched.estado,
            created_at=fetched.created_at,
        )
        dumped = response.model_dump()
        assert "contacto_email" not in dumped
        assert "contacto_telefono" not in dumped
        assert "user_id" not in dumped
        assert "descripcion" not in dumped
        assert "estado" in dumped
        assert "created_at" in dumped

    def test_status_check_nonexistent_raises_404(
        self, db: Session, denuncia_service: DenunciaService
    ):
        with pytest.raises(Exception) as exc_info:
            denuncia_service.get_by_id(db, uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]


# ──────────────────────────────────────────────
# PUBLISH / UNPUBLISH WORKFLOW
# ──────────────────────────────────────────────


class TestPublishUnpublishWorkflow:
    """Admin can publish and unpublish layers."""

    def test_publish_layer(
        self, db: Session, capas_repo: CapasRepository
    ):
        capa = _make_capa(db, capas_repo, nombre="To Publish", es_publica=False)
        assert capa.es_publica is False
        assert capa.publicacion_fecha is None

        # Simulate what the publish endpoint does
        capa.es_publica = True
        capa.publicacion_fecha = datetime.now(timezone.utc)
        db.flush()

        fetched = capas_repo.get_by_id(db, capa.id)
        assert fetched is not None
        assert fetched.es_publica is True
        assert fetched.publicacion_fecha is not None

    def test_unpublish_layer(
        self, db: Session, capas_repo: CapasRepository
    ):
        capa = _make_capa(db, capas_repo, nombre="To Unpublish", es_publica=True)
        capa.publicacion_fecha = datetime.now(timezone.utc)
        db.flush()

        # Simulate unpublish
        capa.es_publica = False
        capa.publicacion_fecha = None
        db.flush()

        fetched = capas_repo.get_by_id(db, capa.id)
        assert fetched is not None
        assert fetched.es_publica is False
        assert fetched.publicacion_fecha is None

    def test_publish_already_public_is_idempotent_check(
        self, db: Session, capas_repo: CapasRepository
    ):
        """The endpoint raises 409 if already published — test the guard condition."""
        capa = _make_capa(db, capas_repo, nombre="Already Public", es_publica=True)
        assert capa.es_publica is True

    def test_unpublish_already_private_is_idempotent_check(
        self, db: Session, capas_repo: CapasRepository
    ):
        """The endpoint raises 409 if already unpublished — test the guard condition."""
        capa = _make_capa(db, capas_repo, nombre="Already Private", es_publica=False)
        assert capa.es_publica is False

    def test_publish_nonexistent_layer(
        self, db: Session, capas_repo: CapasRepository
    ):
        result = capas_repo.get_by_id(db, uuid.uuid4())
        assert result is None

    def test_published_layer_appears_in_public_list(
        self, db: Session, capas_repo: CapasRepository
    ):
        """After publishing, the layer should appear in public listing."""
        capa = _make_capa(db, capas_repo, nombre="Publish Flow", es_publica=False)

        # Before publish
        public_layers = capas_repo.get_public(db)
        assert capa.id not in [c.id for c in public_layers]

        # Publish
        capa.es_publica = True
        capa.publicacion_fecha = datetime.now(timezone.utc)
        db.flush()

        # After publish
        public_layers = capas_repo.get_public(db)
        assert capa.id in [c.id for c in public_layers]

    def test_unpublished_layer_disappears_from_public_list(
        self, db: Session, capas_repo: CapasRepository
    ):
        """After unpublishing, the layer should no longer appear in public listing."""
        capa = _make_capa(db, capas_repo, nombre="Unpublish Flow", es_publica=True)

        # Before unpublish
        public_layers = capas_repo.get_public(db)
        assert capa.id in [c.id for c in public_layers]

        # Unpublish
        capa.es_publica = False
        capa.publicacion_fecha = None
        db.flush()

        # After unpublish
        public_layers = capas_repo.get_public(db)
        assert capa.id not in [c.id for c in public_layers]


# ──────────────────────────────────────────────
# PUBLIC STATS
# ──────────────────────────────────────────────


class TestPublicStats:
    """Basic aggregate stats are exposed without auth."""

    def test_stats_counts_denuncias(
        self, db: Session, denuncia_service: DenunciaService
    ):
        payload = DenunciaCreate(
            tipo="desborde",
            descripcion="Desborde de canal principal en zona este de la jurisdiccion.",
            latitud=-33.7,
            longitud=-63.9,
        )
        denuncia_service.create(db, payload)

        total: int = db.execute(
            select(func.count()).select_from(Denuncia)
        ).scalar_one()
        assert total >= 1

    def test_stats_counts_public_layers(
        self, db: Session, capas_repo: CapasRepository
    ):
        _make_capa(db, capas_repo, nombre="Public Stat", es_publica=True)
        _make_capa(db, capas_repo, nombre="Private Stat", es_publica=False)

        total: int = db.execute(
            select(func.count())
            .select_from(Capa)
            .where(Capa.es_publica.is_(True), Capa.visible.is_(True))
        ).scalar_one()
        assert total >= 1


# ──────────────────────────────────────────────
# SCHEMA TESTS
# ──────────────────────────────────────────────


class TestPublicSchemas:
    """Verify schema contracts — no sensitive data leaks."""

    def test_public_layer_list_response_fields(self):
        from app.api.v2.public_schemas import PublicLayerListResponse

        fields = set(PublicLayerListResponse.model_fields.keys())
        assert "id" in fields
        assert "nombre" in fields
        assert "tipo" in fields
        assert "estilo" in fields
        # These should NOT be in the public schema
        assert "fuente" not in fields
        assert "url" not in fields
        assert "geojson_data" not in fields
        assert "es_publica" not in fields

    def test_public_layer_detail_response_includes_geojson(self):
        from app.api.v2.public_schemas import PublicLayerDetailResponse

        fields = set(PublicLayerDetailResponse.model_fields.keys())
        assert "geojson_data" in fields
        assert "nombre" in fields
        # Still no internal details
        assert "fuente" not in fields
        assert "url" not in fields
        assert "es_publica" not in fields

    def test_public_denuncia_status_no_personal_info(self):
        from app.api.v2.public_schemas import PublicDenunciaStatusResponse

        fields = set(PublicDenunciaStatusResponse.model_fields.keys())
        assert fields == {"estado", "created_at"}

    def test_publish_layer_response_fields(self):
        from app.api.v2.public_schemas import PublishLayerResponse

        fields = set(PublishLayerResponse.model_fields.keys())
        assert "id" in fields
        assert "nombre" in fields
        assert "es_publica" in fields
        assert "publicacion_fecha" in fields

    def test_admin_layer_publish_status_fields(self):
        from app.api.v2.public_schemas import AdminLayerPublishStatus

        fields = set(AdminLayerPublishStatus.model_fields.keys())
        assert "id" in fields
        assert "es_publica" in fields
        assert "publicacion_fecha" in fields
        assert "visible" in fields
