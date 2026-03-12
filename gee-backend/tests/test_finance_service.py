from unittest.mock import MagicMock, patch

from app.services.finance_service import FinanceService


def _query_with_data(data):
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.gte.return_value = query
    query.lte.return_value = query
    query.insert.return_value = query
    query.update.return_value = query
    query.upsert.return_value = query
    query.execute.return_value = MagicMock(data=data)
    return query


def test_get_categorias_and_fuentes_are_deduplicated_sorted():
    gastos_query = _query_with_data(
        [
            {"categoria": "obras"},
            {"categoria": "combustible"},
            {"categoria": "obras"},
            {"categoria": ""},
        ]
    )
    ingresos_query = _query_with_data(
        [{"fuente": "subsidio"}, {"fuente": "otros"}, {"fuente": "subsidio"}]
    )

    db = MagicMock()
    db.client.table.side_effect = lambda name: (
        gastos_query if name == "gastos" else ingresos_query
    )

    with patch("app.services.finance_service.get_supabase_service", return_value=db):
        service = FinanceService()

    assert service.get_categorias() == ["combustible", "obras"]
    assert service.get_fuentes_ingreso() == ["otros", "subsidio"]


def test_create_and_update_map_legacy_comprobante_field():
    write_query = _query_with_data(
        [{"id": "g1", "comprobante_url": "https://cdn/x.pdf"}]
    )

    db = MagicMock()
    db.client.table.return_value = write_query

    with patch("app.services.finance_service.get_supabase_service", return_value=db):
        service = FinanceService()

    created = service.create_gasto(
        {"descripcion": "x", "comprobante": "https://cdn/x.pdf"}
    )
    updated = service.update_ingreso("i1", {"comprobante": "https://cdn/y.pdf"})

    assert created["comprobante_url"] == "https://cdn/x.pdf"
    assert updated["comprobante_url"] == "https://cdn/x.pdf"
    assert (
        write_query.insert.call_args.args[0]["comprobante_url"] == "https://cdn/x.pdf"
    )
    assert (
        write_query.update.call_args.args[0]["comprobante_url"] == "https://cdn/y.pdf"
    )


def test_budget_execution_by_category_merges_projected_and_real_values():
    presupuestos = _query_with_data([{"id": "pres-1"}])
    items = _query_with_data(
        [
            {"categoria": "obras", "monto_previsto": 1000},
            {"categoria": "combustible", "monto_previsto": 500},
        ]
    )
    gastos = _query_with_data(
        [
            {"categoria": "obras", "monto": 700},
            {"categoria": "maquinaria", "monto": 300},
        ]
    )

    db = MagicMock()
    db.client.table.side_effect = lambda name: {
        "presupuestos": presupuestos,
        "presupuesto_items": items,
        "gastos": gastos,
    }[name]

    with patch("app.services.finance_service.get_supabase_service", return_value=db):
        service = FinanceService()

    result = service.get_budget_execution_by_category(2026)
    by_rubro = {row["rubro"]: row for row in result}

    assert by_rubro["obras"] == {"rubro": "obras", "proyectado": 1000.0, "real": 700.0}
    assert by_rubro["combustible"] == {
        "rubro": "combustible",
        "proyectado": 500.0,
        "real": 0,
    }
    assert by_rubro["maquinaria"] == {
        "rubro": "maquinaria",
        "proyectado": 0,
        "real": 300.0,
    }


def test_balance_summary_uses_rpc_and_falls_back_when_missing():
    ingresos_operativos = _query_with_data([{"monto": 200}, {"monto": 50}])
    rpc_query = MagicMock()
    rpc_query.execute.return_value = MagicMock(
        data=[{"total_ingresos": 1000, "total_gastos": 400}]
    )

    db = MagicMock()
    db.client.table.return_value = ingresos_operativos
    db.client.rpc.return_value = rpc_query

    with patch("app.services.finance_service.get_supabase_service", return_value=db):
        service = FinanceService()

    rpc_result = service.get_balance_summary(2026)
    assert rpc_result["total_ingresos"] == 1250.0
    assert rpc_result["total_gastos"] == 400.0
    assert rpc_result["balance"] == 850.0

    cuotas_query = _query_with_data([{"monto": 100}, {"monto": 40}])
    gastos_query = _query_with_data([{"monto": 60}])
    db.client.rpc.side_effect = RuntimeError("rpc unavailable")
    db.client.table.side_effect = lambda name: {
        "ingresos": ingresos_operativos,
        "cuotas_pagos": cuotas_query,
        "gastos": gastos_query,
    }[name]

    fallback_result = service.get_balance_summary(2026)
    assert fallback_result["total_ingresos"] == 390
    assert fallback_result["total_gastos"] == 60
    assert fallback_result["balance"] == 330


def test_upload_finance_comprobante_returns_public_url():
    storage_bucket = MagicMock()
    storage_bucket.get_public_url.return_value = "https://cdn/comprobantes/gasto/x.pdf"

    storage = MagicMock()
    storage.from_.return_value = storage_bucket

    db = MagicMock()
    db.client.storage = storage

    with patch("app.services.finance_service.get_supabase_service", return_value=db):
        service = FinanceService()

    result = service.upload_finance_comprobante(
        content=b"%PDF-1.4 content",
        content_type="application/pdf",
        record_type="gasto",
        extension="pdf",
    )

    assert result["url"] == "https://cdn/comprobantes/gasto/x.pdf"
    assert result["filename"].startswith("gasto/")
    storage_bucket.upload.assert_called_once()
