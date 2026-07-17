"""Focused unit tests for the mutation targets — service-layer logic.

These tests power the cosmic-ray gate. They are deliberately:
  - Pure-python (no DB, no FastAPI app boot, no testcontainers).
  - Fast (the whole file runs in under 1s on a cold venv).
  - Branch-dense (each conditional path in the targeted modules is
    exercised at least once, ideally twice — happy + sad — so a
    flipped operator or short-circuit mutation fails immediately).

Targets configured in ``.cosmic-ray.toml``:
  - ``app/domains/denuncias/service.py``
  - ``app/domains/monitoring/service.py``
  - ``app/domains/tramites/schemas.py``  (also covered by
    ``tests/test_tramites_schema.py``)
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.domains.denuncias.models import EstadoDenuncia
from app.domains.denuncias.service import DenunciaService
from app.domains.monitoring.service import MonitoringService


# ===========================================================================
# DenunciaService
# ===========================================================================


def _make_denuncia_service():
    repo = MagicMock()
    return DenunciaService(repository=repo), repo


def _denuncia_stub(**overrides):
    """Plain attribute bag matching the columns we touch in the service."""

    class _D:
        pass

    d = _D()
    d.id = overrides.get("id", uuid.uuid4())
    d.estado = overrides.get("estado", EstadoDenuncia.PENDIENTE)
    d.user_id = overrides.get("user_id", uuid.uuid4())
    d.tipo = overrides.get("tipo", "desborde")
    d.descripcion = overrides.get("descripcion", "x" * 30)
    return d


class TestDenunciaServiceGetById:
    def test_returns_row_when_found(self):
        svc, repo = _make_denuncia_service()
        d = _denuncia_stub()
        repo.get_by_id.return_value = d

        result = svc.get_by_id(db=MagicMock(), denuncia_id=d.id)

        assert result is d
        repo.get_by_id.assert_called_once()

    def test_raises_404_when_not_found(self):
        svc, repo = _make_denuncia_service()
        repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_by_id(db=MagicMock(), denuncia_id=uuid.uuid4())

        assert exc.value.status_code == 404
        assert "no encontrada" in exc.value.detail.lower()


class TestDenunciaServiceList:
    def test_list_passes_filters_to_repo(self):
        svc, repo = _make_denuncia_service()
        repo.get_all.return_value = ([], 0)

        svc.list_denuncias(
            db=MagicMock(),
            page=3,
            limit=50,
            estado="resuelta",
            cuenca="cuenca_1",
        )

        repo.get_all.assert_called_once()
        kwargs = repo.get_all.call_args.kwargs
        assert kwargs["page"] == 3
        assert kwargs["limit"] == 50
        assert kwargs["estado_filter"] == "resuelta"
        assert kwargs["cuenca_filter"] == "cuenca_1"

    def test_list_by_user_passes_user_id(self):
        svc, repo = _make_denuncia_service()
        repo.get_all_by_user.return_value = ([], 0)
        user_id = uuid.uuid4()

        svc.list_by_user(db=MagicMock(), user_id=user_id, page=2, limit=10)

        repo.get_all_by_user.assert_called_once()
        kwargs = repo.get_all_by_user.call_args.kwargs
        assert kwargs["user_id"] == user_id
        assert kwargs["page"] == 2
        assert kwargs["limit"] == 10


class TestDenunciaServiceCreate:
    def test_enforces_submission_limit_when_user_id_given(self, monkeypatch):
        svc, repo = _make_denuncia_service()
        repo.create.return_value = _denuncia_stub()

        enforce_called = []

        def fake_enforce(db, *, model, user_id_attr, user_id):
            enforce_called.append(user_id)

        monkeypatch.setattr(
            "app.domains.denuncias.service.enforce_submission_limit",
            fake_enforce,
        )

        db = MagicMock()
        uid = uuid.uuid4()
        svc.create(db, MagicMock(), user_id=uid)

        assert enforce_called == [uid], "enforce_submission_limit MUST run when a user_id is passed"
        db.commit.assert_called_once()

    def test_skips_submission_limit_when_user_id_is_none(self, monkeypatch):
        svc, repo = _make_denuncia_service()
        repo.create.return_value = _denuncia_stub()

        enforce_called = []

        def fake_enforce(db, *, model, user_id_attr, user_id):
            enforce_called.append(user_id)

        monkeypatch.setattr(
            "app.domains.denuncias.service.enforce_submission_limit",
            fake_enforce,
        )

        svc.create(MagicMock(), MagicMock(), user_id=None)

        assert enforce_called == [], (
            "enforce_submission_limit MUST be skipped for anonymous create "
            "(legacy compatibility — the router rejects anonymous now, but "
            "the service still tolerates user_id=None)"
        )


class TestDenunciaServiceUpdate:
    """The state-transition guard is the most mutation-prone code in
    this module (lots of boolean ops and dict lookups)."""

    def test_no_estado_change_skips_historial(self, monkeypatch):
        svc, repo = _make_denuncia_service()
        d = _denuncia_stub(estado="pendiente")
        repo.get_by_id.return_value = d
        repo.update.return_value = d

        # Stop submission limit + transitions noise from leaking in
        monkeypatch.setattr(
            "app.domains.denuncias.service.VALID_TRANSITIONS",
            {"pendiente": {"en_revision"}},
        )

        payload = MagicMock()
        payload.estado = None
        payload.comentario = None

        svc.update(MagicMock(), d.id, payload, operator_id=uuid.uuid4())

        repo.add_historial.assert_not_called()
        repo.update.assert_called_once()

    def test_same_estado_skips_historial(self):
        svc, repo = _make_denuncia_service()
        d = _denuncia_stub(estado="pendiente")
        repo.get_by_id.return_value = d
        repo.update.return_value = d

        payload = MagicMock()
        payload.estado = "pendiente"  # identical to current
        payload.comentario = None

        svc.update(MagicMock(), d.id, payload, operator_id=uuid.uuid4())

        repo.add_historial.assert_not_called()

    def test_valid_transition_records_historial(self, monkeypatch):
        svc, repo = _make_denuncia_service()
        d = _denuncia_stub(estado="pendiente")
        repo.get_by_id.return_value = d
        repo.update.return_value = d

        monkeypatch.setattr(
            "app.domains.denuncias.service.VALID_TRANSITIONS",
            {"pendiente": {"en_revision"}},
        )
        payload = MagicMock()
        payload.estado = "en_revision"
        payload.comentario = "Pasa a revisión"
        op_id = uuid.uuid4()

        db = MagicMock()
        svc.update(db, d.id, payload, operator_id=op_id)

        repo.add_historial.assert_called_once()
        kwargs = repo.add_historial.call_args.kwargs
        assert kwargs["denuncia_id"] == d.id
        assert kwargs["estado_anterior"] == "pendiente"
        assert kwargs["estado_nuevo"] == "en_revision"
        assert kwargs["comentario"] == "Pasa a revisión"
        assert kwargs["usuario_id"] == op_id
        # 3vr Sonnet HIGH: the ``db.commit()`` at the bottom of
        # ``update()`` would otherwise survive a mutation that drops
        # the line — without this assertion the test passes even if
        # the commit goes missing.
        db.commit.assert_called_once()

    def test_invalid_transition_raises_400(self, monkeypatch):
        svc, repo = _make_denuncia_service()
        d = _denuncia_stub(estado="pendiente")
        repo.get_by_id.return_value = d

        monkeypatch.setattr(
            "app.domains.denuncias.service.VALID_TRANSITIONS",
            {"pendiente": {"en_revision"}},  # does NOT include "resuelta"
        )
        payload = MagicMock()
        payload.estado = "resuelta"
        payload.comentario = None

        with pytest.raises(HTTPException) as exc:
            svc.update(MagicMock(), d.id, payload, operator_id=uuid.uuid4())

        assert exc.value.status_code == 400
        assert "pendiente" in exc.value.detail
        assert "resuelta" in exc.value.detail
        repo.add_historial.assert_not_called()
        repo.update.assert_not_called()

    def test_unknown_source_estado_disallows_all_transitions(self, monkeypatch):
        """If current state isn't in VALID_TRANSITIONS, EVERY target is
        invalid — covered by the ``set()`` fallback default."""
        svc, repo = _make_denuncia_service()
        d = _denuncia_stub(estado="UNKNOWN_STATE")
        repo.get_by_id.return_value = d

        monkeypatch.setattr(
            "app.domains.denuncias.service.VALID_TRANSITIONS",
            {"pendiente": {"en_revision"}},
        )
        payload = MagicMock()
        payload.estado = "en_revision"
        payload.comentario = None

        with pytest.raises(HTTPException) as exc:
            svc.update(MagicMock(), d.id, payload, operator_id=uuid.uuid4())

        assert exc.value.status_code == 400


# ===========================================================================
# MonitoringService — feature-collection helpers (file I/O isolated)
# ===========================================================================


def _make_monitoring_service():
    repo = MagicMock()
    return MonitoringService(repository=repo), repo


class TestMonitoringServiceGetSugerencia:
    def test_returns_row_when_found(self):
        svc, repo = _make_monitoring_service()
        s = object()
        repo.get_sugerencia_by_id.return_value = s

        assert svc.get_sugerencia(MagicMock(), uuid.uuid4()) is s

    def test_raises_404_when_not_found(self):
        svc, repo = _make_monitoring_service()
        repo.get_sugerencia_by_id.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_sugerencia(MagicMock(), uuid.uuid4())

        assert exc.value.status_code == 404


class TestMonitoringServiceAgendar:
    def test_sets_fecha_reunion(self):
        svc, repo = _make_monitoring_service()
        sugerencia = MagicMock()
        sugerencia.fecha_reunion = None
        repo.get_sugerencia_by_id.return_value = sugerencia

        target = date(2026, 6, 1)
        result = svc.agendar_sugerencia(MagicMock(), uuid.uuid4(), fecha_reunion=target)

        assert sugerencia.fecha_reunion == target
        assert result is sugerencia

    def test_clears_fecha_reunion_with_none(self):
        svc, repo = _make_monitoring_service()
        sugerencia = MagicMock()
        sugerencia.fecha_reunion = date(2026, 6, 1)
        repo.get_sugerencia_by_id.return_value = sugerencia

        svc.agendar_sugerencia(MagicMock(), uuid.uuid4(), fecha_reunion=None)

        assert sugerencia.fecha_reunion is None


class TestMonitoringServiceUpdateSugerencia:
    def test_raises_404_when_not_found(self):
        svc, repo = _make_monitoring_service()
        repo.update_sugerencia.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.update_sugerencia(MagicMock(), uuid.uuid4(), MagicMock())

        assert exc.value.status_code == 404

    def test_returns_updated_row(self):
        svc, repo = _make_monitoring_service()
        s = MagicMock()
        repo.update_sugerencia.return_value = s

        result = svc.update_sugerencia(MagicMock(), uuid.uuid4(), MagicMock())
        assert result is s


class TestMonitoringServiceGetAnalysis:
    def test_returns_row_when_found(self):
        svc, repo = _make_monitoring_service()
        a = object()
        repo.get_analysis_by_id.return_value = a

        assert svc.get_analysis(MagicMock(), uuid.uuid4()) is a

    def test_raises_404_when_not_found(self):
        svc, repo = _make_monitoring_service()
        repo.get_analysis_by_id.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_analysis(MagicMock(), uuid.uuid4())

        assert exc.value.status_code == 404


class TestMonitoringServiceFeatureHelpers:
    """File-collection helpers ``_load_feature_collection`` and
    ``_build_channel_features_from_sugerencia`` carry most of the
    branching logic — perfect mutation surface."""

    def test_load_invalid_payload_raises_500(self, tmp_path):
        svc, _ = _make_monitoring_service()
        path = tmp_path / "bad.geojson"
        path.write_text("not even json", encoding="utf-8")

        with pytest.raises(HTTPException) as exc:
            svc._load_feature_collection(path)

        assert exc.value.status_code == 500

    def test_load_rejects_non_feature_collection(self, tmp_path):
        svc, _ = _make_monitoring_service()
        path = tmp_path / "wrong.geojson"
        path.write_text('{"type": "Feature"}', encoding="utf-8")

        with pytest.raises(HTTPException) as exc:
            svc._load_feature_collection(path)

        assert exc.value.status_code == 500
        assert "FeatureCollection" in exc.value.detail

    def test_load_minimal_valid_collection(self, tmp_path):
        svc, _ = _make_monitoring_service()
        path = tmp_path / "ok.geojson"
        path.write_text(
            '{"type": "FeatureCollection", "features": []}',
            encoding="utf-8",
        )
        payload = svc._load_feature_collection(path)
        assert payload["type"] == "FeatureCollection"
        assert payload["features"] == []

    def test_load_collection_without_features_key_gets_default(self, tmp_path):
        """``setdefault('features', [])`` must be applied — a payload
        without the key should not crash callers."""
        svc, _ = _make_monitoring_service()
        path = tmp_path / "headless.geojson"
        path.write_text('{"type": "FeatureCollection"}', encoding="utf-8")
        payload = svc._load_feature_collection(path)
        assert payload["features"] == []

    def test_build_features_filters_non_linestring(self):
        svc, _ = _make_monitoring_service()
        sug = MagicMock()
        sug.id = uuid.uuid4()
        sug.titulo = "Sug título"
        sug.geometry = {
            "features": [
                {"geometry": {"type": "Point", "coordinates": [0, 0]}},
                {"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},
            ]
        }

        feats = svc._build_channel_features_from_sugerencia(sug)
        # ONLY the LineString survived
        assert len(feats) == 1
        assert feats[0]["geometry"]["type"] == "LineString"

    def test_build_features_includes_sugerencia_id_property(self):
        svc, _ = _make_monitoring_service()
        sug = MagicMock()
        sug.id = uuid.uuid4()
        sug.titulo = "Sug título"
        sug.geometry = {
            "features": [
                {
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    "properties": {"name": "Canal A"},
                }
            ]
        }

        feats = svc._build_channel_features_from_sugerencia(sug)
        assert feats[0]["properties"]["sugerencia_id"] == str(sug.id)
        # Original name preserved (only filled-in defaults override empties)
        assert feats[0]["properties"]["name"] == "Canal A"
        assert feats[0]["properties"]["source"] == "sugerencia_incorporada"
        # Auto-generated id uses the sugerencia + index
        assert feats[0]["properties"]["id"].startswith(f"canales-existentes-sugerencia-{sug.id}-")

    def test_build_features_empty_geometry(self):
        """Defensive: a sugerencia without geometry returns an empty
        list, not a KeyError."""
        svc, _ = _make_monitoring_service()
        sug = MagicMock()
        sug.id = uuid.uuid4()
        sug.titulo = "Empty"
        sug.geometry = None

        feats = svc._build_channel_features_from_sugerencia(sug)
        assert feats == []

    def test_build_features_uses_titulo_when_no_name(self):
        """``properties.name`` falls back to ``sugerencia.titulo`` when
        the input has no ``name``."""
        svc, _ = _make_monitoring_service()
        sug = MagicMock()
        sug.id = uuid.uuid4()
        sug.titulo = "Sug título 42"
        sug.geometry = {
            "features": [
                {
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    # no ``properties`` at all
                }
            ]
        }

        feats = svc._build_channel_features_from_sugerencia(sug)
        assert feats[0]["properties"]["name"] == "Sug título 42"


class TestMonitoringServiceResolveExistingPath:
    def test_returns_first_match(self, tmp_path):
        svc, _ = _make_monitoring_service()
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        b.write_text("{}")
        result = svc._resolve_existing_path((a, b))
        assert result == b

    def test_returns_none_when_no_match(self, tmp_path):
        svc, _ = _make_monitoring_service()
        result = svc._resolve_existing_path(
            (tmp_path / "missing-1.json", tmp_path / "missing-2.json")
        )
        assert result is None


class TestMonitoringServicePersistChannel:
    def test_no_double_insert_for_same_sugerencia(self, tmp_path, monkeypatch):
        """``_persist_incorporated_channel`` must be idempotent — a
        sugerencia already in the dataset should not be appended again.
        """
        svc, _ = _make_monitoring_service()
        target_path = tmp_path / "canales.geojson"
        sug_id = uuid.uuid4()
        target_path.write_text(
            '{"type": "FeatureCollection", "features": ['
            '{"type": "Feature", "geometry": {"type": "LineString", "coordinates":[[0,0],[1,1]]}, '
            f'"properties": {{"sugerencia_id": "{sug_id}"}}}}'
            "]}",
            encoding="utf-8",
        )

        monkeypatch.setattr(
            svc,
            "_BACKEND_WATERWAYS_CANDIDATES",
            (target_path,),
        )

        sug = MagicMock()
        sug.id = sug_id
        sug.titulo = "ya estoy"
        sug.geometry = {
            "features": [{"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}]
        }

        svc._persist_incorporated_channel(sug)

        # File untouched — still exactly one feature.
        payload_after = target_path.read_text(encoding="utf-8")
        assert payload_after.count('"sugerencia_id":') == 1

    def test_raises_500_when_dataset_missing(self, tmp_path, monkeypatch):
        svc, _ = _make_monitoring_service()
        monkeypatch.setattr(svc, "_BACKEND_WATERWAYS_CANDIDATES", (tmp_path / "missing.geojson",))
        sug = MagicMock()
        sug.id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc:
            svc._persist_incorporated_channel(sug)
        assert exc.value.status_code == 500


class TestMonitoringServiceGetPersistedIds:
    def test_returns_empty_set_when_no_dataset(self, tmp_path, monkeypatch):
        svc, _ = _make_monitoring_service()
        monkeypatch.setattr(svc, "_BACKEND_WATERWAYS_CANDIDATES", (tmp_path / "absent.geojson",))
        assert svc._get_persisted_sugerencia_ids() == set()

    def test_extracts_ids_from_features(self, tmp_path, monkeypatch):
        svc, _ = _make_monitoring_service()
        target = tmp_path / "canales.geojson"
        target.write_text(
            '{"type": "FeatureCollection", "features": ['
            '{"type": "Feature", "properties": {"sugerencia_id": "AAA"}},'
            '{"type": "Feature", "properties": {"sugerencia_id": "BBB"}},'
            '{"type": "Feature", "properties": {}}'
            "]}",
            encoding="utf-8",
        )
        monkeypatch.setattr(svc, "_BACKEND_WATERWAYS_CANDIDATES", (target,))

        ids = svc._get_persisted_sugerencia_ids()
        assert ids == {"AAA", "BBB"}
