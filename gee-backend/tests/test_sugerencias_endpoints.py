from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_create_public_suggestion_requires_contact(client):
    response = client.post(
        "/api/v1/sugerencias/public",
        json={
            "titulo": "Canal en mal estado",
            "descripcion": "Se requiere mantenimiento urgente en el tramo norte",
            "contacto_verificado": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONTACT_REQUIRED"


def test_create_public_suggestion_enforces_daily_limit(client):
    rate_query = MagicMock()
    rate_query.select.return_value = rate_query
    rate_query.eq.return_value = rate_query
    rate_query.gte.return_value = rate_query
    rate_query.execute.return_value = SimpleNamespace(count=3)

    supabase = MagicMock()
    supabase.table.return_value = rate_query

    with patch(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", return_value=supabase
    ):
        response = client.post(
            "/api/v1/sugerencias/public",
            json={
                "titulo": "Canal en mal estado",
                "descripcion": "Se requiere mantenimiento urgente en el tramo norte",
                "contacto_email": "vecino@example.com",
                "contacto_verificado": True,
            },
        )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


def test_create_public_suggestion_requires_verified_contact(client):
    response = client.post(
        "/api/v1/sugerencias/public",
        json={
            "titulo": "Canal en mal estado",
            "descripcion": "Se requiere mantenimiento urgente en el tramo norte",
            "contacto_email": "vecino@example.com",
            "contacto_verificado": False,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONTACT_NOT_VERIFIED"


def test_create_public_suggestion_persists_suggestion_submission_and_history(client):
    rate_query = MagicMock()
    rate_query.select.return_value = rate_query
    rate_query.eq.return_value = rate_query
    rate_query.gte.return_value = rate_query
    rate_query.execute.return_value = SimpleNamespace(count=1)

    create_query = MagicMock()
    create_query.insert.return_value = create_query
    create_query.execute.return_value = SimpleNamespace(data=[{"id": "sug-1"}])

    submission_query = MagicMock()
    submission_query.insert.return_value = submission_query
    submission_query.execute.return_value = SimpleNamespace(data=[{"id": "sub-1"}])

    history_query = MagicMock()
    history_query.insert.return_value = history_query
    history_query.execute.return_value = SimpleNamespace(data=[{"id": "hist-1"}])

    supabase = MagicMock()
    supabase.table.side_effect = [
        rate_query,
        create_query,
        submission_query,
        history_query,
    ]

    with patch(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", return_value=supabase
    ):
        response = client.post(
            "/api/v1/sugerencias/public",
            json={
                "titulo": "Canal en mal estado",
                "descripcion": "Se requiere mantenimiento urgente en el tramo norte",
                "contacto_email": "vecino@example.com",
                "contacto_verificado": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "sug-1"
    assert payload["remaining_today"] == 1


def test_public_limit_requires_contact(client):
    response = client.get("/api/v1/sugerencias/public/limit")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONTACT_REQUIRED"


def test_public_limit_accepts_phone_and_returns_remaining(client):
    rate_query = MagicMock()
    rate_query.select.return_value = rate_query
    rate_query.eq.return_value = rate_query
    rate_query.gte.return_value = rate_query
    rate_query.execute.return_value = SimpleNamespace(count=2)

    supabase = MagicMock()
    supabase.table.return_value = rate_query

    with patch(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", return_value=supabase
    ):
        response = client.get("/api/v1/sugerencias/public/limit?telefono=3534123456")

    assert response.status_code == 200
    assert response.json()["remaining"] == 1


def test_get_sugerencias_stats_counts_by_status_and_type(
    client, mock_auth, auth_headers
):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.side_effect = [
        SimpleNamespace(count=2),
        SimpleNamespace(count=3),
        SimpleNamespace(count=4),
        SimpleNamespace(count=1),
        SimpleNamespace(count=5),
        SimpleNamespace(count=6),
    ]

    supabase = MagicMock()
    supabase.table.return_value = query

    with patch(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", return_value=supabase
    ):
        response = client.get("/api/v1/sugerencias/stats", headers=auth_headers)

    assert response.status_code == 200
    stats = response.json()
    assert stats["pendiente"] == 2
    assert stats["en_agenda"] == 3
    assert stats["tratado"] == 4
    assert stats["descartado"] == 1
    assert stats["ciudadanas"] == 5
    assert stats["internas"] == 6
    assert stats["total"] == 10


def test_get_sugerencias_list_applies_filters_and_pagination(
    client, mock_auth, auth_headers
):
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "tipo": "interna",
        "titulo": "Tema",
        "descripcion": "Descripcion valida",
        "categoria": None,
        "contacto_nombre": None,
        "contacto_email": None,
        "estado": "pendiente",
        "prioridad": "alta",
        "fecha_reunion": None,
        "notas_comision": None,
        "resolucion": None,
        "cuenca_id": "norte",
        "autor_id": None,
        "created_at": "2026-03-01T10:00:00Z",
        "updated_at": "2026-03-01T10:00:00Z",
    }

    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.return_value = SimpleNamespace(data=[row], count=1)

    supabase = MagicMock()
    supabase.table.return_value = query

    with patch(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", return_value=supabase
    ):
        response = client.get(
            "/api/v1/sugerencias?page=2&limit=5&tipo=interna&estado=pendiente&prioridad=alta&cuenca_id=norte",
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    query.range.assert_called_once_with(5, 9)


def test_update_sugerencia_rejects_empty_payload(client, admin_auth, auth_headers):
    existing_query = MagicMock()
    existing_query.select.return_value = existing_query
    existing_query.eq.return_value = existing_query
    existing_query.single.return_value = existing_query
    existing_query.execute.return_value = SimpleNamespace(
        data={"estado": "pendiente", "prioridad": "normal"}
    )

    supabase = MagicMock()
    supabase.table.return_value = existing_query

    with patch(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", return_value=supabase
    ):
        response = client.put(
            "/api/v1/sugerencias/11111111-1111-1111-1111-111111111111",
            headers=auth_headers,
            json={},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NO_UPDATE_DATA"


def test_agendar_sugerencia_returns_not_found_when_update_returns_empty(
    client, admin_auth, auth_headers
):
    update_query = MagicMock()
    update_query.update.return_value = update_query
    update_query.eq.return_value = update_query
    update_query.execute.return_value = SimpleNamespace(data=[])

    supabase = MagicMock()
    supabase.table.return_value = update_query

    with patch(
        "app.api.v1.endpoints.sugerencias.get_supabase_client", return_value=supabase
    ):
        response = client.post(
            "/api/v1/sugerencias/11111111-1111-1111-1111-111111111111/agendar",
            headers=auth_headers,
            json={"fecha_reunion": "2026-03-15"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SUGGESTION_NOT_FOUND"
