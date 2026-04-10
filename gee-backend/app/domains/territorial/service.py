"""Business logic for the territorial domain.

Known GeoJSON file paths (mounted into the backend container via docker-compose):
  - Suelos:  /app/public/data/suelos_cu.geojson
  - Canales: /app/public/waterways/canales_existentes.geojson
  - Caminos: /app/public/capas/caminos.geojson
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.territorial.repository import TerritorialRepository
from app.domains.territorial.schemas import (
    CaminoConsorcioBreakdown,
    ImportResponse,
    SueloBreakdown,
    SyncResponse,
    TerritorialReportResponse,
)

# Paths inside the container (docker-compose volume mounts)
_SUELOS_PATH = Path("/app/public/data/suelos_cu.geojson")
_CANALES_PATH = Path("/app/public/waterways/canales_existentes.geojson")
_CAMINOS_PATH = Path("/app/public/capas/caminos.geojson")


class TerritorialService:
    def __init__(self, repo: TerritorialRepository) -> None:
        self.repo = repo

    # ── Sync from existing files ─────────────────────────────────────────────

    def sync_geodata(self, db: Session) -> SyncResponse:
        """Read suelos, canales and caminos from known GeoJSON files and load into PostGIS."""
        results: dict[str, str] = {}

        for name, path, importer in [
            ("suelos", _SUELOS_PATH, self.repo.import_suelos),
            ("canales", _CANALES_PATH, self.repo.import_canales),
            ("caminos", _CAMINOS_PATH, self.repo.import_caminos),
        ]:
            if path.exists():
                geojson = json.loads(path.read_text(encoding="utf-8"))
                features = geojson.get("features") or []
                try:
                    count = importer(db, features)
                    results[name] = f"{count} features"
                except Exception as exc:
                    db.rollback()
                    results[name] = f"error: {exc}"
            else:
                results[name] = f"archivo no encontrado: {path}"

        self.repo.refresh_views(db)
        try:
            self.repo.refresh_caminos_view(db)
        except Exception:
            db.rollback()
            results["caminos_view"] = "vista no existe — ejecutar migración 0016"

        return SyncResponse(
            message="Geodatos sincronizados desde archivos locales.",
            details=results,
        )

    # ── Manual imports (kept for API compatibility) ──────────────────────────

    def import_suelos(self, db: Session, geojson: dict) -> ImportResponse:
        features = geojson.get("features") or []
        if not features:
            raise HTTPException(status_code=400, detail="GeoJSON has no features")
        count = self.repo.import_suelos(db, features)
        self.repo.refresh_views(db)
        return ImportResponse(
            imported=count,
            message=f"Importados {count} polígonos de suelo. Vistas actualizadas.",
        )

    def import_canales(self, db: Session, geojson: dict) -> ImportResponse:
        features = geojson.get("features") or []
        if not features:
            raise HTTPException(status_code=400, detail="GeoJSON has no features")
        count = self.repo.import_canales(db, features)
        self.repo.refresh_views(db)
        return ImportResponse(
            imported=count,
            message=f"Importados {count} canales. Vistas actualizadas.",
        )

    def import_caminos(self, db: Session, geojson: dict) -> ImportResponse:
        features = geojson.get("features") or []
        if not features:
            raise HTTPException(status_code=400, detail="GeoJSON has no features")
        count = self.repo.import_caminos(db, features)
        self.repo.refresh_views(db)
        return ImportResponse(
            imported=count,
            message=f"Importados {count} tramos de caminos. Vistas actualizadas.",
        )

    # ── Report ────────────────────────────────────────────────────────────────

    def get_report(
        self,
        db: Session,
        scope: str,
        scope_value: str | None,
    ) -> TerritorialReportResponse:
        if scope not in ("consorcio", "cuenca", "zona"):
            raise HTTPException(status_code=400, detail=f"scope inválido: {scope}")
        if scope in ("cuenca", "zona") and not scope_value:
            raise HTTPException(
                status_code=400, detail=f"scope '{scope}' requiere un valor"
            )

        suelos_data = self.repo.get_suelos_data(db, scope, scope_value)
        km_canales = self.repo.get_km_canales(db, scope, scope_value)
        caminos_data = self.repo.get_km_caminos_por_consorcio(db, scope, scope_value)

        total_ha = sum(s["ha"] for s in suelos_data)
        total_km_caminos = sum(c["km"] for c in caminos_data)

        suelos = [
            SueloBreakdown(
                simbolo=s["simbolo"],
                cap=s["cap"],
                ha=round(s["ha"], 2),
                pct=round(s["ha"] / total_ha * 100, 1) if total_ha > 0 else 0.0,
            )
            for s in suelos_data
        ]

        caminos = [
            CaminoConsorcioBreakdown(
                consorcio_codigo=c["consorcio_codigo"],
                consorcio_nombre=c["consorcio_nombre"],
                km=round(c["km"], 2),
                pct=round(c["km"] / total_km_caminos * 100, 1) if total_km_caminos > 0 else 0.0,
            )
            for c in caminos_data
        ]

        if scope == "consorcio":
            scope_name = "Todo el Consorcio"
        elif scope == "cuenca":
            scope_name = f"Cuenca: {scope_value}"
        else:
            zona_nombre = self.repo.get_zona_nombre(db, scope_value)  # type: ignore[arg-type]
            scope_name = zona_nombre or scope_value or "Zona"

        return TerritorialReportResponse(
            scope=scope,
            scope_name=scope_name,
            km_canales=round(km_canales, 2),
            suelos=suelos,
            total_ha_analizada=round(total_ha, 2),
            caminos_por_consorcio=caminos,
            total_km_caminos=round(total_km_caminos, 2),
        )

    def get_cuencas(self, db: Session) -> list[str]:
        return self.repo.get_cuencas(db)

    def get_status(self, db: Session) -> dict:
        return {
            "has_suelos": self.repo.has_suelos_data(db),
            "has_canales": self.repo.has_canales_data(db),
            "has_caminos": self.repo.has_caminos_data(db),
        }
