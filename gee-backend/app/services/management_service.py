"""
Management Service.
Handles administrative procedures (tramites) and tracking for reports/suggestions.
"""

from functools import lru_cache
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from app.services.supabase_service import get_supabase_service
from app.core.logging import get_logger

logger = get_logger(__name__)


class ManagementService:
    def __init__(self):
        self.db = get_supabase_service()

    # --- Tramites ---
    def get_tramites(self, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.db.client.table("tramites").select("*")
        if estado:
            query = query.eq("estado", estado)
        result = query.order("ultima_actualizacion", desc=True).execute()
        return result.data

    def create_tramite(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = self.db.client.table("tramites").insert(data).execute()
        return result.data[0] if result.data else {}

    def add_tramite_avance(self, avance_data: Dict[str, Any]) -> Dict[str, Any]:
        # Insert avance
        result = self.db.client.table("tramite_avances").insert(avance_data).execute()

        # Update tramite last update and state if provided
        tramite_id = avance_data.get("tramite_id")
        update_data = {"ultima_actualizacion": datetime.now().isoformat()}
        if "nuevo_estado" in avance_data:
            update_data["estado"] = avance_data["nuevo_estado"]

        self.db.client.table("tramites").update(update_data).eq(
            "id", tramite_id
        ).execute()
        return result.data[0] if result.data else {}

    def get_tramite_detalle(self, tramite_id: UUID) -> Dict[str, Any]:
        tramite = (
            self.db.client.table("tramites")
            .select("*")
            .eq("id", str(tramite_id))
            .single()
            .execute()
        )
        avances = (
            self.db.client.table("tramite_avances")
            .select("*")
            .eq("tramite_id", str(tramite_id))
            .order("fecha", desc=True)
            .execute()
        )

        return {**tramite.data, "avances": avances.data}

    # --- Seguimiento (Reportes/Sugerencias) ---
    def add_seguimiento(self, seguimiento_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a tracking log entry and update the parent entity status."""
        # 1. Insert log
        result = (
            self.db.client.table("gestion_seguimiento")
            .insert(seguimiento_data)
            .execute()
        )

        # 2. Update the entity (Reporte or Sugerencia)
        entity_id = seguimiento_data.get("entidad_id")
        entity_type = seguimiento_data.get("entidad_tipo")  # 'reporte' or 'sugerencia'
        new_status = seguimiento_data.get("estado_nuevo")

        table_name = "denuncias" if entity_type == "reporte" else "sugerencias"

        if new_status:
            self.db.client.table(table_name).update(
                {"estado": new_status, "updated_at": datetime.now().isoformat()}
            ).eq("id", entity_id).execute()

        return result.data[0] if result.data else {}

    def get_historial_entidad(
        self, entity_type: str, entity_id: UUID
    ) -> List[Dict[str, Any]]:
        result = (
            self.db.client.table("gestion_seguimiento")
            .select("*")
            .eq("entidad_tipo", entity_type)
            .eq("entidad_id", str(entity_id))
            .order("fecha", desc=True)
            .execute()
        )
        return result.data

    # --- Reuniones y Agenda ---
    def get_reuniones(self) -> List[Dict[str, Any]]:
        result = (
            self.db.client.table("reuniones")
            .select("*")
            .order("fecha_reunion", desc=True)
            .execute()
        )
        return result.data

    def create_reunion(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = self.db.client.table("reuniones").insert(data).execute()
        return result.data[0] if result.data else {}

    def get_agenda_detalle(self, reunion_id: UUID) -> List[Dict[str, Any]]:
        """Get all items for a meeting with their references using a nested select."""
        result = (
            self.db.client.table("agenda_items")
            .select("*, agenda_referencias(*)")
            .eq("reunion_id", str(reunion_id))
            .order("orden")
            .execute()
        )

        # The nested select returns each item with its 'agenda_referencias' embedded
        enhanced_items = []
        for item in result.data:
            refs = item.pop("agenda_referencias", [])
            enhanced_items.append({**item, "referencias": refs})

        return enhanced_items

    def add_agenda_item(
        self,
        reunion_id: UUID,
        item_data: Dict[str, Any],
        referencias: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create agenda item and its links using batch insert for references."""
        item_data["reunion_id"] = str(reunion_id)
        res_item = self.db.client.table("agenda_items").insert(item_data).execute()

        if res_item.data and referencias:
            item_id = res_item.data[0]["id"]
            # Prepare all references with the agenda_item_id
            refs_with_id = [{**ref, "agenda_item_id": item_id} for ref in referencias]
            # Batch insert all references in a single query
            self.db.client.table("agenda_referencias").insert(refs_with_id).execute()

        return res_item.data[0] if res_item.data else {}


@lru_cache(maxsize=1)
def get_management_service() -> ManagementService:
    """Obtener instancia del servicio de gestion (singleton)."""
    return ManagementService()
