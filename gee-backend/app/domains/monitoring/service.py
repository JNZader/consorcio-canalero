"""Business-logic layer for the monitoring domain."""

import json
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.monitoring.models import AnalisisGee, Sugerencia
from app.domains.monitoring.repository import MonitoringRepository
from app.domains.monitoring.schemas import SugerenciaCreate, SugerenciaUpdate
from app.shared.submission_limit import (
    enforce_submission_limit,
    get_submission_status,
)


class MonitoringService:
    """Orchestrates repository calls with business rules."""

    # Batch 5 (2026-04-20): the frontend `public/waterways/canales_existentes.geojson`
    # was retired along with the `waterways_canales_existentes` layer slot —
    # Pilar Azul's `useCanales` now serves all 43 canales from the static
    # `public/capas/canales/*` assets. The `incorporar-canal` POST endpoint
    # still persists to the BACKEND dataset (kept as the authoritative store of
    # admin-incorporated sugerencias). The frontend-side mirror file is NO
    # LONGER WRITTEN — the modal's "Incorporar a Canales existentes" UI still
    # works, but the reference map now reads from `useCanales().relevados`
    # (see `SuggestionDetailModal.tsx`).
    _BACKEND_WATERWAYS_CANDIDATES = (
        Path("/app/data/waterways/canales_existentes.geojson"),
        Path(__file__).resolve().parents[4]
        / "gee-backend/data/waterways/canales_existentes.geojson",
    )

    def __init__(self, repository: MonitoringRepository | None = None) -> None:
        self.repo = repository or MonitoringRepository()

    def _resolve_existing_path(self, candidates: tuple[Path, ...]) -> Path | None:
        for path in candidates:
            if path.exists():
                return path
        return None

    def _load_feature_collection(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parsing
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo leer el dataset oficial de canales: {path}",
            ) from exc

        if payload.get("type") != "FeatureCollection":
            raise HTTPException(
                status_code=500,
                detail=f"El dataset oficial de canales no es un FeatureCollection: {path}",
            )

        payload.setdefault("features", [])
        return payload

    def _write_feature_collection(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)

    def _build_channel_features_from_sugerencia(
        self, sugerencia: Sugerencia
    ) -> list[dict[str, Any]]:
        geometry = sugerencia.geometry or {}
        features: list[dict[str, Any]] = []

        for index, feature in enumerate(geometry.get("features", []), start=1):
            if feature.get("geometry", {}).get("type") != "LineString":
                continue
            properties = dict(feature.get("properties") or {})
            properties.update(
                {
                    "id": f"canales-existentes-sugerencia-{sugerencia.id}-{index}",
                    "name": properties.get("name") or sugerencia.titulo,
                    "source": "sugerencia_incorporada",
                    "sugerencia_id": str(sugerencia.id),
                }
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": feature.get("geometry"),
                    "properties": properties,
                }
            )

        return features

    def _persist_incorporated_channel(self, sugerencia: Sugerencia) -> None:
        backend_path = self._resolve_existing_path(self._BACKEND_WATERWAYS_CANDIDATES)
        if backend_path is None:
            raise HTTPException(
                status_code=500,
                detail="No se encontró el dataset oficial de canales existentes",
            )

        payload = self._load_feature_collection(backend_path)
        existing_features = payload.get("features", [])
        sugerencia_id = str(sugerencia.id)
        already_present = any(
            (feature.get("properties") or {}).get("sugerencia_id") == sugerencia_id
            for feature in existing_features
        )

        if not already_present:
            existing_features.extend(self._build_channel_features_from_sugerencia(sugerencia))
            payload["features"] = existing_features
            self._write_feature_collection(backend_path, payload)

    def _get_persisted_sugerencia_ids(self) -> set[str]:
        backend_path = self._resolve_existing_path(self._BACKEND_WATERWAYS_CANDIDATES)
        if backend_path is None:
            return set()

        payload = self._load_feature_collection(backend_path)
        return {
            str((feature.get("properties") or {}).get("sugerencia_id"))
            for feature in payload.get("features", [])
            if (feature.get("properties") or {}).get("sugerencia_id")
        }

    # ── SUGERENCIAS ────────────────────────────

    def get_sugerencia(self, db: Session, sugerencia_id: uuid.UUID) -> Sugerencia:
        sugerencia = self.repo.get_sugerencia_by_id(db, sugerencia_id)
        if sugerencia is None:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
        return sugerencia

    def list_sugerencias(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        estado: Optional[str] = None,
        categoria: Optional[str] = None,
    ) -> tuple[list[Sugerencia], int]:
        return self.repo.get_all_sugerencias(
            db,
            page=page,
            limit=limit,
            estado_filter=estado,
            categoria_filter=categoria,
        )

    def list_sugerencias_by_user(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Sugerencia], int]:
        """Citizen-owned paginated list — used by `GET /sugerencias/mine`."""
        return self.repo.get_all_sugerencias_by_user(db, user_id=user_id, page=page, limit=limit)

    def create_sugerencia(
        self,
        db: Session,
        data: SugerenciaCreate,
        *,
        usuario_id: Optional[uuid.UUID] = None,
    ) -> Sugerencia:
        if usuario_id is not None:
            enforce_submission_limit(
                db,
                model=Sugerencia,
                user_id_attr=Sugerencia.usuario_id,
                user_id=usuario_id,
            )
        sugerencia = self.repo.create_sugerencia(db, data, usuario_id=usuario_id)
        db.commit()
        db.refresh(sugerencia)
        return sugerencia

    def get_rate_limit_status(self, db: Session, user_id: uuid.UUID) -> dict:
        """Quota left for a citizen — used by `GET /sugerencias/rate-limit`."""
        return get_submission_status(
            db,
            model=Sugerencia,
            user_id_attr=Sugerencia.usuario_id,
            user_id=user_id,
        )

    def update_sugerencia(
        self,
        db: Session,
        sugerencia_id: uuid.UUID,
        data: SugerenciaUpdate,
    ) -> Sugerencia:
        sugerencia = self.repo.update_sugerencia(db, sugerencia_id, data)
        if sugerencia is None:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
        db.commit()
        db.refresh(sugerencia)
        return sugerencia

    def get_sugerencias_stats(self, db: Session) -> dict[str, Any]:
        return self.repo.get_sugerencias_stats(db)

    def get_proxima_reunion(self, db: Session) -> list[Sugerencia]:
        return self.repo.get_proxima_reunion(db)

    def agendar_sugerencia(
        self,
        db: Session,
        sugerencia_id: uuid.UUID,
        *,
        fecha_reunion: Optional[date],
    ) -> Sugerencia:
        """
        Set or clear `Sugerencia.fecha_reunion`. Idempotent overwrite —
        passing `None` clears the field, which is how the admin UI
        "unschedules" a sugerencia. Other fields are left untouched.
        """
        sugerencia = self.get_sugerencia(db, sugerencia_id)
        sugerencia.fecha_reunion = fecha_reunion
        db.flush()
        db.commit()
        db.refresh(sugerencia)
        return sugerencia

    # The previous `incorporate_sugerencia_as_channel` workflow lived
    # here together with the matching `POST /sugerencias/{id}/incorporar-canal`
    # endpoint. It was retired on 2026-04-29 — the operator handles
    # implementation tracking by changing `estado → implementada` and
    # writing a `respuesta`, no need for a side-channel that mutated
    # the GeoJSON file at runtime.

    # ── ANALYSES ───────────────────────────────

    def get_analysis(self, db: Session, analysis_id: uuid.UUID) -> AnalisisGee:
        analysis = self.repo.get_analysis_by_id(db, analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="Analisis no encontrado")
        return analysis

    def list_analyses(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 20,
        tipo: Optional[str] = None,
    ) -> tuple[list[AnalisisGee], int]:
        return self.repo.get_analysis_history(db, page=page, limit=limit, tipo_filter=tipo)

    def save_analysis(self, db: Session, data: dict[str, Any]) -> AnalisisGee:
        analysis = self.repo.save_analysis(db, data)
        db.commit()
        db.refresh(analysis)
        return analysis

    # ── DASHBOARD ──────────────────────────────

    def get_dashboard_stats(self, db: Session) -> dict[str, Any]:
        return self.repo.get_dashboard_stats(db)
