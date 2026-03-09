from datetime import date

from app.services.monitoring_service import AlertConfig, MonitoringService


def _build_service() -> MonitoringService:
    service = MonitoringService.__new__(MonitoringService)
    service.alert_config = AlertConfig()
    service.cuencas = {"candil": object()}
    return service


def test_generate_alerts_from_results_creates_and_sorts_alerts():
    service = _build_service()

    alerts = service._generate_alerts_from_results(
        cuencas_result={
            "cuencas": {
                "norte": {
                    "resumen": {
                        "porcentaje_problematico": 25.0,
                        "area_anegada_ha": 120,
                        "area_con_agua_ha": 20,
                    }
                },
                "ml": {
                    "resumen": {
                        "porcentaje_problematico": 12.0,
                        "area_anegada_ha": 30,
                        "area_con_agua_ha": 5,
                    }
                },
            }
        },
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )

    assert len(alerts) == 2
    assert alerts[0]["severidad"] == "alta"
    assert alerts[0]["cuenca"] == "norte"
    assert alerts[1]["severidad"] == "media"


def test_get_monitoring_summary_reuses_existing_results_without_extra_calls(monkeypatch):
    service = _build_service()

    classify_calls = {"count": 0}

    def fake_classify(*args, **kwargs):
        classify_calls["count"] += 1
        return {
            "area_total_ha": 1000,
            "clases": {"cultivo_sano": {"hectareas": 800}},
            "resumen": {
                "area_productiva_ha": 800,
                "area_problematica_ha": 200,
                "porcentaje_problematico": 20,
            },
        }

    monkeypatch.setattr(service, "classify_parcels", fake_classify)
    monkeypatch.setattr(
        service,
        "classify_parcels_by_cuenca",
        lambda **kwargs: {"ranking_criticidad": [{"cuenca": "norte", "porcentaje_problematico": 20}]},
    )
    monkeypatch.setattr(
        service,
        "_generate_alerts_from_results",
        lambda **kwargs: [{"tipo": "area_critica", "severidad": "alta"}],
    )

    summary = service.get_monitoring_summary(days_back=15)

    assert classify_calls["count"] == 1
    assert summary["estado_general"]["area_total_ha"] == 1000
    assert summary["total_alertas"] == 1
    assert summary["cuencas_criticas"][0]["cuenca"] == "norte"


def test_get_monitoring_summary_returns_error_when_classification_fails(monkeypatch):
    service = _build_service()
    monkeypatch.setattr(
        service,
        "classify_parcels",
        lambda **kwargs: {"error": "No se encontraron imagenes"},
    )

    result = service.get_monitoring_summary(days_back=30)
    assert result == {"error": "No se encontraron imagenes"}


def test_detect_changes_builds_trend_from_period_comparison(monkeypatch):
    service = _build_service()

    def fake_classify(*, start_date, **kwargs):
        if start_date == date(2026, 1, 1):
            return {
                "resumen": {"porcentaje_problematico": 10},
                "clases": {
                    "cultivo_sano": {"hectareas": 50, "porcentaje": 50},
                    "rastrojo": {"hectareas": 20, "porcentaje": 20},
                    "agua_superficie": {"hectareas": 5, "porcentaje": 5},
                    "lote_anegado": {"hectareas": 5, "porcentaje": 5},
                },
            }
        return {
            "resumen": {"porcentaje_problematico": 24},
            "clases": {
                "cultivo_sano": {"hectareas": 40, "porcentaje": 40},
                "rastrojo": {"hectareas": 16, "porcentaje": 16},
                "agua_superficie": {"hectareas": 12, "porcentaje": 12},
                "lote_anegado": {"hectareas": 12, "porcentaje": 12},
            },
        }

    monkeypatch.setattr(service, "classify_parcels", fake_classify)

    result = service.detect_changes(
        date1_start=date(2026, 1, 1),
        date1_end=date(2026, 1, 31),
        date2_start=date(2026, 2, 1),
        date2_end=date(2026, 2, 28),
        layer_name="norte",
    )

    assert result["tendencia"]["codigo"] == "empeoramiento_significativo"
    assert result["cambios_por_clase"]["agua_superficie"]["diferencia_pct"] == 7


def test_generate_alerts_includes_change_alert_when_reference_is_provided(monkeypatch):
    service = _build_service()

    monkeypatch.setattr(
        service,
        "classify_parcels_by_cuenca",
        lambda **kwargs: {
            "cuencas": {
                "candil": {
                    "resumen": {
                        "porcentaje_problematico": 8,
                        "area_anegada_ha": 10,
                        "area_con_agua_ha": 4,
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        service,
        "detect_changes",
        lambda **kwargs: {"tendencia": {"cambio_total_pct": 7.2}},
    )

    response = service.generate_alerts(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        reference_start=date(2026, 1, 1),
        reference_end=date(2026, 1, 31),
    )

    assert response["total_alertas"] == 1
    assert response["alertas"][0]["tipo"] == "incremento_anegamiento"
    assert response["alertas"][0]["severidad"] == "alta"
