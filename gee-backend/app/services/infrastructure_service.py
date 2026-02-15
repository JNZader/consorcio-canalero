"""
Infrastructure Service.
Handles assets like canals, culverts, and their maintenance history.
"""

import ee
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from app.services.supabase_service import get_supabase_service
from app.services.gee_service import get_gee_service, _gee_initialized, initialize_gee
from app.core.logging import get_logger

logger = get_logger(__name__)


class InfrastructureService:
    def __init__(self):
        self.db = get_supabase_service()
        if not _gee_initialized:
            initialize_gee()

    def get_potential_intersections(self) -> Dict[str, Any]:
        """
        Find intersections between roads and canals.
        If canals layer is empty, it returns an empty result (no fallback).
        """
        gee = get_gee_service()
        roads = gee.caminos
        canals = gee.canales

        # Check if canals asset has data
        try:
            canals_count = canals.size().getInfo()
            if canals_count == 0:
                return {"type": "FeatureCollection", "features": []}
        except Exception:
            return {"type": "FeatureCollection", "features": []}

        target_geometry = canals.geometry()

        def find_intersections(road):
            return road.intersection(target_geometry, ee.ErrorMargin(1))

        # Perform intersection
        intersections = roads.map(find_intersections)

        # Filter only points (where intersection is not empty)
        points = intersections.filter(ee.Filter.isNotNull(".geo"))

        return points.getInfo()

    def get_all_assets(self, cuenca: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all infrastructure assets."""
        query = self.db.client.table("infraestructura").select("*")
        if cuenca:
            query = query.eq("cuenca", cuenca)

        result = query.execute()
        return result.data

    def create_asset(self, asset_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new infrastructure asset (manual POI)."""
        result = self.db.client.table("infraestructura").insert(asset_data).execute()
        return result.data[0] if result.data else {}

    def get_asset_history(self, asset_id: UUID) -> List[Dict[str, Any]]:
        """Get maintenance history for a specific asset."""
        result = (
            self.db.client.table("mantenimiento_logs")
            .select("*")
            .eq("infraestructura_id", str(asset_id))
            .order("fecha", desc=True)
            .execute()
        )
        return result.data

    def add_maintenance_log(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """Record a new maintenance activity."""
        # 1. Insert the log
        result = self.db.client.table("mantenimiento_logs").insert(log_data).execute()

        # 2. Update asset's last inspection date and state
        if result.data:
            asset_id = log_data.get("infraestructura_id")
            self.db.client.table("infraestructura").update(
                {
                    "ultima_inspeccion": datetime.now().isoformat(),
                    "estado_actual": log_data.get(
                        "nuevo_estado", "bueno"
                    ),  # Optionally passed in log
                }
            ).eq("id", asset_id).execute()

        return result.data[0] if result.data else {}


_infrastructure_service = None


def get_infrastructure_service() -> InfrastructureService:
    global _infrastructure_service
    if _infrastructure_service is None:
        _infrastructure_service = InfrastructureService()
    return _infrastructure_service
