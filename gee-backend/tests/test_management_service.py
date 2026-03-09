from uuid import uuid4
from unittest.mock import MagicMock, patch

from app.services.management_service import ManagementService


def _query(data):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.order.return_value = q
    q.insert.return_value = q
    q.update.return_value = q
    q.single.return_value = q
    q.execute.return_value = MagicMock(data=data)
    return q


def test_add_tramite_avance_updates_state_and_timestamp():
    insert_query = _query([{"id": "av-1"}])
    update_query = _query([])

    db = MagicMock()
    db.client.table.side_effect = lambda name: {
        "tramite_avances": insert_query,
        "tramites": update_query,
    }[name]

    with patch("app.services.management_service.get_supabase_service", return_value=db):
        service = ManagementService()

    result = service.add_tramite_avance(
        {"tramite_id": "t-1", "titulo_avance": "Reunion", "nuevo_estado": "aprobado"}
    )

    assert result["id"] == "av-1"
    payload = update_query.update.call_args.args[0]
    assert payload["estado"] == "aprobado"
    assert "ultima_actualizacion" in payload


def test_add_seguimiento_updates_target_table_based_on_entity_type():
    insert_query = _query([{"id": "seg-1"}])
    denuncias_query = _query([])
    sugerencias_query = _query([])

    db = MagicMock()
    db.client.table.side_effect = lambda name: {
        "gestion_seguimiento": insert_query,
        "denuncias": denuncias_query,
        "sugerencias": sugerencias_query,
    }[name]

    with patch("app.services.management_service.get_supabase_service", return_value=db):
        service = ManagementService()

    service.add_seguimiento(
        {"entidad_id": "d1", "entidad_tipo": "reporte", "estado_nuevo": "resuelto"}
    )
    assert denuncias_query.update.called

    service.add_seguimiento(
        {
            "entidad_id": "s1",
            "entidad_tipo": "sugerencia",
            "estado_nuevo": "en_revision",
        }
    )
    assert sugerencias_query.update.called


def test_get_agenda_detalle_maps_nested_references_field():
    agenda_query = _query(
        [
            {
                "id": "i1",
                "titulo": "Tema 1",
                "agenda_referencias": [{"entidad_tipo": "reporte", "entidad_id": "r1"}],
            }
        ]
    )
    db = MagicMock()
    db.client.table.return_value = agenda_query

    with patch("app.services.management_service.get_supabase_service", return_value=db):
        service = ManagementService()

    result = service.get_agenda_detalle(uuid4())
    assert result[0]["referencias"][0]["entidad_id"] == "r1"
    assert "agenda_referencias" not in result[0]


def test_add_agenda_item_batch_inserts_references():
    insert_item_query = _query([{"id": "item-1", "titulo": "Tema"}])
    insert_refs_query = _query([])
    db = MagicMock()
    db.client.table.side_effect = lambda name: {
        "agenda_items": insert_item_query,
        "agenda_referencias": insert_refs_query,
    }[name]

    with patch("app.services.management_service.get_supabase_service", return_value=db):
        service = ManagementService()

    result = service.add_agenda_item(
        uuid4(),
        {"titulo": "Tema", "descripcion": "Detalle", "orden": 1},
        [{"entidad_tipo": "reporte", "entidad_id": "r1"}],
    )

    assert result["id"] == "item-1"
    refs_payload = insert_refs_query.insert.call_args.args[0]
    assert refs_payload[0]["agenda_item_id"] == "item-1"
