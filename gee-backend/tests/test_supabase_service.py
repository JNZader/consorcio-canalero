from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.supabase_service import SupabaseService


def _service_with_client(client: MagicMock) -> SupabaseService:
    service = SupabaseService.__new__(SupabaseService)
    service.client = client
    return service


def test_save_analysis_maps_payload_and_serializes_stats():
    client = MagicMock()
    query = MagicMock()
    query.insert.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "analysis-1"}])
    client.table.return_value = query

    service = _service_with_client(client)

    result = service.save_analysis(
        {
            "parametros": {
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "threshold": -18,
                "cuencas": ["norte"],
            },
            "hectareas_inundadas": 22,
            "porcentaje_area": 2.5,
            "caminos_afectados": 7,
            "stats_cuencas": {"norte": {"hectareas": 12}},
            "imagenes_procesadas": 9,
        }
    )

    assert result == {"id": "analysis-1"}
    inserted_payload = query.insert.call_args.args[0]
    assert inserted_payload["umbral_db"] == -18
    assert inserted_payload["cuencas_analizadas"] == ["norte"]
    assert "norte" in inserted_payload["stats_cuencas"]


def test_reorder_layers_falls_back_to_upsert_when_rpc_fails():
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = RuntimeError("missing rpc")
    upsert_query = MagicMock()
    upsert_query.upsert.return_value = upsert_query
    upsert_query.execute.return_value = SimpleNamespace(data=[{"id": "l1"}])
    client.table.return_value = upsert_query

    service = _service_with_client(client)

    ok = service.reorder_layers([{"id": "l1", "orden": 1}, {"id": "l2", "orden": 2}])

    assert ok is True
    upsert_query.upsert.assert_called_once()


def test_get_reports_stats_uses_rpc_when_available():
    client = MagicMock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(
        data=[{"pendiente": 2, "en_revision": 3, "resuelto": 4, "rechazado": 1, "total": 10}]
    )
    service = _service_with_client(client)

    stats = service.get_reports_stats()

    assert stats["total"] == 10
    assert stats["en_revision"] == 3


def test_get_reports_stats_falls_back_to_count_queries():
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = RuntimeError("rpc unavailable")

    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.limit.return_value = query
    query.execute.side_effect = [
        SimpleNamespace(count=1),
        SimpleNamespace(count=2),
        SimpleNamespace(count=3),
        SimpleNamespace(count=4),
    ]
    client.table.return_value = query

    service = _service_with_client(client)
    stats = service.get_reports_stats()

    assert stats == {
        "pendiente": 1,
        "en_revision": 2,
        "resuelto": 3,
        "rechazado": 4,
        "total": 10,
    }


def test_update_report_sets_resuelto_at_and_writes_history_on_status_change():
    client = MagicMock()
    denuncias_query = MagicMock()
    denuncias_query.update.return_value = denuncias_query
    denuncias_query.eq.return_value = denuncias_query
    denuncias_query.execute.return_value = SimpleNamespace(data=[{"id": "rep-1", "estado": "resuelto"}])

    history_query = MagicMock()
    history_query.insert.return_value = history_query
    history_query.execute.return_value = SimpleNamespace(data=[{"id": "h-1"}])

    def table_side_effect(name: str):
        if name == "denuncias":
            return denuncias_query
        if name == "denuncias_historial":
            return history_query
        raise AssertionError(name)

    client.table.side_effect = table_side_effect

    service = _service_with_client(client)
    service.get_report = MagicMock(return_value={"estado": "pendiente"})

    result = service.update_report(
        "rep-1",
        {"estado": "resuelto", "notas_internas": "cerrado"},
        admin_id="admin-1",
    )

    assert result["estado"] == "resuelto"
    updated_payload = denuncias_query.update.call_args.args[0]
    assert updated_payload["estado"] == "resuelto"
    assert "resuelto_at" in updated_payload
    history_payload = history_query.insert.call_args.args[0]
    assert history_payload["estado_anterior"] == "pendiente"
    assert history_payload["estado_nuevo"] == "resuelto"


def test_get_analysis_history_applies_status_filter_and_pagination():
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.range.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "a-1"}], count=7)
    client.table.return_value = query

    service = _service_with_client(client)
    result = service.get_analysis_history(page=2, limit=3, status="completed")

    assert result["items"] == [{"id": "a-1"}]
    assert result["total"] == 7
    assert result["page"] == 2
    assert result["limit"] == 3
    query.eq.assert_called_with("status", "completed")
    query.range.assert_called_with(3, 5)


def test_get_report_returns_none_when_not_found():
    client = MagicMock()
    report_query = MagicMock()
    report_query.select.return_value = report_query
    report_query.eq.return_value = report_query
    report_query.single.return_value = report_query
    report_query.execute.return_value = SimpleNamespace(data=None)
    client.table.return_value = report_query

    service = _service_with_client(client)

    assert service.get_report("missing") is None


def test_get_new_reports_since_days_returns_count():
    client = MagicMock()
    query = MagicMock()
    query.select.return_value = query
    query.gte.return_value = query
    query.limit.return_value = query
    query.execute.return_value = SimpleNamespace(count=11)
    client.table.return_value = query

    service = _service_with_client(client)

    assert service.get_new_reports_since_days(days=14) == 11


def test_get_dashboard_stats_uses_defaults_when_no_latest_analysis():
    service = SupabaseService.__new__(SupabaseService)
    service.get_latest_analysis = MagicMock(return_value=None)
    service.get_reports_stats = MagicMock(return_value={"pendiente": 1, "total": 1})
    service.get_new_reports_since_days = MagicMock(return_value=2)

    stats = service.get_dashboard_stats()

    assert stats["ultimo_analisis"]["fecha"] is None
    assert stats["ultimo_analisis"]["hectareas_inundadas"] == 0
    assert stats["denuncias_nuevas_semana"] == 2
    assert stats["denuncias"]["pendiente"] == 1
