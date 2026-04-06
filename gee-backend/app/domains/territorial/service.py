"""Business logic for the territorial domain."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.territorial.repository import TerritorialRepository
from app.domains.territorial.schemas import (
    ImportResponse,
    SueloBreakdown,
    TerritorialReportResponse,
)


class TerritorialService:
    def __init__(self, repo: TerritorialRepository) -> None:
        self.repo = repo

    # ── Imports ───────────────────────────────────────────────────────────────

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

        total_ha = sum(s["ha"] for s in suelos_data)

        suelos = [
            SueloBreakdown(
                simbolo=s["simbolo"],
                cap=s["cap"],
                ha=round(s["ha"], 2),
                pct=round(s["ha"] / total_ha * 100, 1) if total_ha > 0 else 0.0,
            )
            for s in suelos_data
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
        )

    def get_cuencas(self, db: Session) -> list[str]:
        return self.repo.get_cuencas(db)

    def get_status(self, db: Session) -> dict:
        return {
            "has_suelos": self.repo.has_suelos_data(db),
            "has_canales": self.repo.has_canales_data(db),
        }
