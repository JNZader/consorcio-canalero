"""Business-logic layer for the monitoring domain."""

import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.monitoring.models import AnalisisGee, Sugerencia
from app.domains.monitoring.repository import MonitoringRepository
from app.domains.monitoring.schemas import SugerenciaCreate, SugerenciaUpdate


class MonitoringService:
    """Orchestrates repository calls with business rules."""

    _BACKEND_WATERWAYS_CANDIDATES = (
        Path("/app/data/waterways/canales_existentes.geojson"),
        Path(__file__).resolve().parents[4] / "gee-backend/data/waterways/canales_existentes.geojson",
    )
    _FRONTEND_WATERWAYS_CANDIDATES = (
        Path("/app/public/waterways/canales_existentes.geojson"),
        Path(__file__).resolve().parents[4] / "consorcio-web/public/waterways/canales_existentes.geojson",
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

            frontend_path = self._resolve_existing_path(self._FRONTEND_WATERWAYS_CANDIDATES)
            if frontend_path is not None:
                self._write_feature_collection(frontend_path, payload)

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

    def create_sugerencia(
        self, db: Session, data: SugerenciaCreate
    ) -> Sugerencia:
        sugerencia = self.repo.create_sugerencia(db, data)
        db.commit()
        db.refresh(sugerencia)
        return sugerencia

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

    def incorporate_sugerencia_as_channel(
        self, db: Session, sugerencia_id: uuid.UUID
    ) -> Sugerencia:
        sugerencia = self.get_sugerencia(db, sugerencia_id)
        if not sugerencia.geometry:
            raise HTTPException(
                status_code=400,
                detail="La sugerencia no tiene geometría para incorporar",
            )

        self._persist_incorporated_channel(sugerencia)
        sugerencia.estado = "implementada"
        sugerencia.respuesta = (
            "Incorporada manualmente a la capa oficial de canales existentes"
        )
        db.flush()
        db.commit()
        db.refresh(sugerencia)
        return sugerencia

    def get_incorporated_channel_feature_collection(
        self, db: Session
    ) -> dict[str, Any]:
        sugerencias = self.repo.get_incorporated_channel_suggestions(db)
        persisted_ids = self._get_persisted_sugerencia_ids()
        features: list[dict[str, Any]] = []

        for sugerencia in sugerencias:
            if str(sugerencia.id) in persisted_ids:
                continue
            geometry = sugerencia.geometry or {}
            for index, feature in enumerate(geometry.get("features", []), start=1):
                if feature.get("geometry", {}).get("type") != "LineString":
                    continue
                properties = dict(feature.get("properties") or {})
                properties.update(
                    {
                        "id": f"sugerencia-incorporada-{sugerencia.id}-{index}",
                        "name": sugerencia.titulo,
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

        return {"type": "FeatureCollection", "features": features}

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
        return self.repo.get_analysis_history(
            db, page=page, limit=limit, tipo_filter=tipo
        )

    def save_analysis(
        self, db: Session, data: dict[str, Any]
    ) -> AnalisisGee:
        analysis = self.repo.save_analysis(db, data)
        db.commit()
        db.refresh(analysis)
        return analysis

    # ── DASHBOARD ──────────────────────────────

    def get_dashboard_stats(self, db: Session) -> dict[str, Any]:
        return self.repo.get_dashboard_stats(db)
