"""Server-side admin list filters for denuncias and sugerencias.

The admin UI sends ``search``, ``categoria`` and ``tipo``. Those params used
to be dropped by FastAPI, the unfiltered page came back, and the panel
re-filtered only that page. A match that lived past page 1 looked like
"no results". These tests hit the real routes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.denuncias.models import Denuncia, EstadoDenuncia
from app.domains.monitoring.models import EstadoSugerencia, Sugerencia

TOKEN = "TokenUnicoPaginaDos"
SUG_TOKEN = "MarcaUnicaSugerencia"


@pytest.fixture
def client(db: Session):
    """Operator identity on the test transaction, so seeded rows are visible."""
    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    test_client = TestClient(app)
    test_client.headers.update({"Host": "localhost"})
    yield test_client
    app.dependency_overrides.clear()


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _denuncia(
    db: Session,
    *,
    tipo: str,
    descripcion: str,
    created_at: datetime,
    estado: str = EstadoDenuncia.PENDIENTE,
    cuenca: str = "norte",
    deleted_at: datetime | None = None,
    contacto_email: str | None = None,
) -> Denuncia:
    row = Denuncia(
        tipo=tipo,
        descripcion=descripcion,
        latitud=-33.7,
        longitud=-63.9,
        cuenca=cuenca,
        estado=estado,
        contacto_email=contacto_email,
        created_at=created_at,
        deleted_at=deleted_at,
    )
    db.add(row)
    db.flush()
    return row


def _user(db: Session) -> uuid.UUID:
    from app.auth.models import User, UserRole

    user = User(
        email=f"filter-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password="fakehash",
        nombre="Op",
        apellido="Test",
        role=UserRole.OPERADOR,
    )
    db.add(user)
    db.flush()
    return user.id


def _sugerencia(
    db: Session,
    *,
    titulo: str,
    descripcion: str,
    created_at: datetime,
    usuario_id: uuid.UUID | None = None,
    categoria: str = "infraestructura",
) -> Sugerencia:
    row = Sugerencia(
        titulo=titulo,
        descripcion=descripcion,
        categoria=categoria,
        estado=EstadoSugerencia.PENDIENTE,
        usuario_id=usuario_id,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _get(client: TestClient, path: str, **params: object) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _seed_denuncias(db: Session) -> dict[str, Denuncia]:
    rows = {
        "noise_newest": _denuncia(
            db,
            tipo="camino_danado",
            descripcion="Ruido reciente en el camino de la parcela.",
            created_at=_at(2024, 4, 1),
        ),
        "noise_resuelto": _denuncia(
            db,
            tipo="camino_danado",
            descripcion="Ruido ya cerrado por el operador de turno.",
            created_at=_at(2024, 3, 1),
            estado=EstadoDenuncia.RESUELTO,
        ),
        "match_newer": _denuncia(
            db,
            tipo="desborde",
            descripcion=f"{TOKEN} en el canal norte, afectando el camino.",
            created_at=_at(2020, 6, 1),
            contacto_email="vecino-unico@example.com",
        ),
        "match_older": _denuncia(
            db,
            tipo="desborde",
            descripcion=f"Otra {TOKEN} aguas abajo del mismo tramo.",
            created_at=_at(2020, 5, 1),
        ),
        "match_otro": _denuncia(
            db,
            tipo="otro",
            descripcion=f"{TOKEN} de otro tipo, fuera del desborde.",
            created_at=_at(2020, 4, 1),
            cuenca="cuenca-marca-xyz",
        ),
        "deleted": _denuncia(
            db,
            tipo="desborde",
            descripcion=f"{TOKEN} borrada por el titular.",
            created_at=_at(2020, 3, 1),
            deleted_at=_at(2024, 1, 1),
        ),
    }
    return rows


def _seed_sugerencias(db: Session) -> dict[str, Sugerencia]:
    owner = _user(db)
    return {
        "noise_newest": _sugerencia(
            db,
            titulo="Ruido nuevo de la cuadrilla",
            descripcion="Nada que ver con la busqueda.",
            created_at=_at(2024, 4, 1),
        ),
        "noise_interna": _sugerencia(
            db,
            titulo="Ruido interno de comision",
            descripcion="Tampoco coincide con la marca.",
            created_at=_at(2024, 3, 1),
            usuario_id=owner,
        ),
        "match_ciudadana": _sugerencia(
            db,
            titulo=f"{SUG_TOKEN} lejana en el ramal",
            descripcion="Pedido de limpieza del tramo sur.",
            created_at=_at(2020, 2, 1),
            categoria="riego",
        ),
        "match_interna": _sugerencia(
            db,
            titulo=f"Otra {SUG_TOKEN} de la comision",
            descripcion="Seguimiento interno del mismo ramal.",
            created_at=_at(2020, 1, 1),
            usuario_id=owner,
            categoria="riego",
        ),
    }


class TestDenunciaListFilters:
    def test_search_returns_matches_that_live_past_page_one(self, client: TestClient, db: Session):
        rows = _seed_denuncias(db)

        first_page = _get(client, "/api/v2/denuncias", page=1, limit=1)
        assert first_page["total"] == 5
        assert first_page["pages"] == 5
        assert first_page["items"][0]["id"] == str(rows["noise_newest"].id)

        found = _get(
            client,
            "/api/v2/denuncias",
            page=1,
            limit=1,
            search=f"  {TOKEN.lower()}  ",
        )
        assert found["total"] == 3
        assert found["pages"] == 3
        assert found["page"] == 1
        assert found["items"][0]["id"] == str(rows["match_newer"].id)

        second = _get(
            client,
            "/api/v2/denuncias",
            page=2,
            limit=1,
            search=TOKEN.lower(),
        )
        assert second["total"] == 3
        assert second["pages"] == 3
        assert second["items"][0]["id"] == str(rows["match_older"].id)

    def test_tipo_and_categoria_filter_the_stored_tipo(self, client: TestClient, db: Session):
        rows = _seed_denuncias(db)

        by_tipo = _get(client, "/api/v2/denuncias", tipo="desborde", limit=10)
        assert by_tipo["total"] == 2
        assert {item["id"] for item in by_tipo["items"]} == {
            str(rows["match_newer"].id),
            str(rows["match_older"].id),
        }

        by_categoria = _get(client, "/api/v2/denuncias", categoria="desborde", limit=10)
        assert by_categoria["total"] == by_tipo["total"]
        assert by_categoria["pages"] == 1

        narrowed = _get(
            client,
            "/api/v2/denuncias",
            search=TOKEN.lower(),
            tipo="desborde",
            limit=10,
        )
        assert narrowed["total"] == 2
        assert str(rows["match_otro"].id) not in {item["id"] for item in narrowed["items"]}

    def test_unknown_categoria_is_applied(self, client: TestClient, db: Session):
        _seed_denuncias(db)

        empty = _get(client, "/api/v2/denuncias", categoria="no-existe", limit=10)
        assert empty["total"] == 0
        assert empty["pages"] == 0
        assert empty["items"] == []

    def test_status_alias_still_filters(self, client: TestClient, db: Session):
        rows = _seed_denuncias(db)

        resolved = _get(client, "/api/v2/denuncias", status="resuelto", limit=10)
        assert resolved["total"] == 1
        assert resolved["items"][0]["id"] == str(rows["noise_resuelto"].id)

    def test_search_matches_contacto_and_cuenca(self, client: TestClient, db: Session):
        rows = _seed_denuncias(db)

        by_email = _get(client, "/api/v2/denuncias", search="vecino-unico@example.com")
        assert by_email["total"] == 1
        assert by_email["items"][0]["id"] == str(rows["match_newer"].id)

        by_cuenca = _get(client, "/api/v2/denuncias", search="CUENCA-MARCA-XYZ")
        assert by_cuenca["total"] == 1
        assert by_cuenca["items"][0]["id"] == str(rows["match_otro"].id)


class TestSugerenciaListFilters:
    def test_search_returns_matches_that_live_past_page_one(self, client: TestClient, db: Session):
        rows = _seed_sugerencias(db)

        first_page = _get(client, "/api/v2/sugerencias", page=1, limit=1)
        assert first_page["total"] == 4
        assert first_page["pages"] == 4
        assert first_page["items"][0]["id"] == str(rows["noise_newest"].id)

        found = _get(
            client,
            "/api/v2/sugerencias",
            page=1,
            limit=1,
            search=SUG_TOKEN.lower(),
        )
        assert found["total"] == 2
        assert found["pages"] == 2
        assert found["items"][0]["id"] == str(rows["match_ciudadana"].id)

        second = _get(
            client,
            "/api/v2/sugerencias",
            page=2,
            limit=1,
            search=f"  {SUG_TOKEN.lower()} ",
        )
        assert second["total"] == 2
        assert second["pages"] == 2
        assert second["items"][0]["id"] == str(rows["match_interna"].id)

    def test_tipo_splits_ciudadana_and_interna(self, client: TestClient, db: Session):
        rows = _seed_sugerencias(db)

        ciudadanas = _get(client, "/api/v2/sugerencias", tipo="ciudadana", limit=10)
        assert ciudadanas["total"] == 2
        assert {item["id"] for item in ciudadanas["items"]} == {
            str(rows["noise_newest"].id),
            str(rows["match_ciudadana"].id),
        }

        internas = _get(
            client,
            "/api/v2/sugerencias",
            tipo="interna",
            search=SUG_TOKEN.lower(),
            limit=10,
        )
        assert internas["total"] == 1
        assert internas["pages"] == 1
        assert internas["items"][0]["id"] == str(rows["match_interna"].id)

    def test_unknown_tipo_is_applied(self, client: TestClient, db: Session):
        _seed_sugerencias(db)

        empty = _get(client, "/api/v2/sugerencias", tipo="fantasma", limit=10)
        assert empty["total"] == 0
        assert empty["pages"] == 0
        assert empty["items"] == []

    def test_categoria_still_filters_with_the_new_params(self, client: TestClient, db: Session):
        rows = _seed_sugerencias(db)

        riego = _get(client, "/api/v2/sugerencias", categoria="riego", limit=10)
        assert riego["total"] == 2
        assert {item["id"] for item in riego["items"]} == {
            str(rows["match_ciudadana"].id),
            str(rows["match_interna"].id),
        }
