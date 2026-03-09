from uuid import uuid4
from unittest.mock import MagicMock, patch

from app.services.padron_service import PadronService, _sanitize_search


def _query(data):
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.order.return_value = q
    q.or_.return_value = q
    q.upsert.return_value = q
    q.execute.return_value = MagicMock(data=data)
    return q


def test_sanitize_search_removes_postgrest_special_chars():
    value = "  perez,.(test)[x]{y}  "
    assert _sanitize_search(value) == "pereztestxy"


def test_get_consorcistas_uses_sanitized_search_filter():
    consorcistas = _query([{"id": "c1", "apellido": "Perez"}])
    db = MagicMock()
    db.client.table.return_value = consorcistas

    with patch("app.services.padron_service.get_supabase_service", return_value=db):
        service = PadronService()

    result = service.get_consorcistas("perez,)")

    assert result[0]["apellido"] == "Perez"
    assert "perez" in consorcistas.or_.call_args.args[0]
    assert ",)" not in consorcistas.or_.call_args.args[0]


def test_import_consorcistas_csv_handles_success_and_errors():
    upsert_query = _query([])
    db = MagicMock()
    db.client.table.return_value = upsert_query

    with patch("app.services.padron_service.get_supabase_service", return_value=db):
        service = PadronService()

    csv_content = (
        "nombre,apellido,cuit,email,activo\n"
        "Juan,Perez,20123456781,juan@test.com,si\n"
        "Maria,,20222333444,maria@test.com,si\n"
        "Pedro,Gomez,,pedro@test.com,si\n"
    ).encode("utf-8")

    result = service.import_consorcistas("padron.csv", csv_content)

    assert result["processed"] == 3
    assert result["upserted"] == 1
    assert result["skipped"] == 2
    assert len(result["errors"]) == 2


def test_import_consorcistas_rejects_unsupported_extension():
    db = MagicMock()
    with patch("app.services.padron_service.get_supabase_service", return_value=db):
        service = PadronService()

    try:
        service.import_consorcistas("padron.txt", b"raw")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Formato no soportado" in str(exc)


def test_get_deudores_filters_out_paid_members():
    member_1 = str(uuid4())
    member_2 = str(uuid4())
    consorcistas = _query(
        [
            {"id": member_1, "apellido": "Perez"},
            {"id": member_2, "apellido": "Gomez"},
        ]
    )
    pagos = _query([{"consorcista_id": member_1}])

    db = MagicMock()
    db.client.table.side_effect = (
        lambda name: consorcistas if name == "consorcistas" else pagos
    )

    with patch("app.services.padron_service.get_supabase_service", return_value=db):
        service = PadronService()

    deudores = service.get_deudores(2026)
    assert len(deudores) == 1
    assert deudores[0]["id"] == member_2
