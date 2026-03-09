from app.services.pdf_service import PDFService, get_pdf_service


def _assert_pdf(buffer):
    raw = buffer.getvalue()
    assert raw.startswith(b"%PDF")
    assert len(raw) > 500


def test_generate_emergency_and_agenda_pdfs():
    service = PDFService()

    emergency = service.create_emergency_report(
        {
            "cuenca": "Candil",
            "stats": [
                {"nombre": "Candil", "ha": 1000, "pct": 12, "estado": "Alerta"},
                {"nombre": "ML", "ha": 500, "pct": 5, "estado": "Normal"},
            ],
            "recent_maintenance": [
                {
                    "fecha": "2026-03-01",
                    "nombre": "Puente Norte",
                    "tarea": "Limpieza",
                    "estado": "Completado",
                }
            ],
        }
    )
    _assert_pdf(emergency)

    agenda = service.create_agenda_pdf(
        {"titulo": "Reunion Ordinaria", "fecha_reunion": "2026-03-09", "lugar": "Sede"},
        [
            {
                "titulo": "Tema 1",
                "descripcion": "Revisar canales",
                "referencias": [
                    {
                        "entidad_tipo": "reporte",
                        "entidad_id": "abcde12345",
                        "metadata": {"label": "Reporte Ruta 9"},
                    }
                ],
            }
        ],
    )
    _assert_pdf(agenda)


def test_generate_asset_tramite_resolution_and_integral_pdfs():
    service = PDFService()

    ficha = service.create_asset_ficha_pdf(
        {
            "nombre": "Alcantarilla Sur",
            "tipo": "alcantarilla",
            "estado_actual": "regular",
            "cuenca": "candil",
            "latitud": -33.1,
            "longitud": -63.2,
        },
        [
            {
                "fecha": "2026-03-01T10:00:00Z",
                "tipo_tarea": "limpieza",
                "operario_nombre": "Juan",
                "descripcion": "Retiro de sedimentos",
            }
        ],
    )
    _assert_pdf(ficha)

    tramite = service.create_tramite_summary_pdf(
        {"numero_expediente": "EXP-123", "titulo": "Canal principal", "estado": "en_revision"},
        [
            {
                "fecha": "2026-03-01T10:00:00Z",
                "titulo_avance": "Inspeccion",
                "comentario": "Se realizo visita tecnica",
            }
        ],
    )
    _assert_pdf(tramite)

    resolution = service.create_report_resolution_pdf(
        {
            "id": "abcdef123456",
            "categoria": "desborde",
            "ubicacion_texto": "Ruta provincial 3",
        },
        [
            {
                "fecha": "2026-03-05T10:00:00Z",
                "comentario_publico": "Se destapo alcantarilla",
            },
            {"fecha": "2026-03-06T10:00:00Z", "comentario_publico": ""},
        ],
    )
    _assert_pdf(resolution)

    integral = service.create_general_impact_report_pdf(
        {
            "satelite": [{"nombre": "Candil", "pct": 8, "estado": "Normal"}],
            "cuencas_data": {
                "candil": {"reportes_count": 2, "sugerencias_count": 1},
            },
        }
    )
    _assert_pdf(integral)


def test_get_pdf_service_returns_singleton_instance():
    first = get_pdf_service()
    second = get_pdf_service()
    assert first is second
