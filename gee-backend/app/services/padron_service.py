"""
Padron Service.
Manages consortium members and their annual fee payments.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from app.services.supabase_service import get_supabase_service
from app.core.logging import get_logger

logger = get_logger(__name__)

class PadronService:
    def __init__(self):
        self.db = get_supabase_service()

    def get_consorcistas(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.db.client.table("consorcistas").select("*")
        if search:
            query = query.or_(f"nombre.ilike.%{search}%,apellido.ilike.%{search}%,cuit.ilike.%{search}%")
        result = query.order("apellido", desc=False).execute()
        return result.data

    def create_consorcista(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = self.db.client.table("consorcistas").insert(data).execute()
        return result.data[0] if result.data else {}

    def get_pagos_by_consorcista(self, consorcista_id: UUID) -> List[Dict[str, Any]]:
        result = self.db.client.table("cuotas_pagos") \
            .select("*") \
            .eq("consorcista_id", str(consorcista_id)) \
            .order("anio", desc=True) \
            .execute()
        return result.data

    def registrar_pago(self, pago_data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a payment for a specific year."""
        result = self.db.client.table("cuotas_pagos").upsert(pago_data, on_conflict="consorcista_id,anio").execute()
        return result.data[0] if result.data else {}

    def get_deudores(self, anio: int) -> List[Dict[str, Any]]:
        """Find members who haven't paid a specific year."""
        # This is a bit more complex, for now we list all and filter in frontend or use a RPC
        members = self.get_consorcistas()
        pagos = self.db.client.table("cuotas_pagos").select("consorcista_id").eq("anio", anio).eq("estado", "pagado").execute()
        pagadores_ids = [p["consorcista_id"] for p in pagos.data]
        
        return [m for m in members if str(m["id"]) not in pagadores_ids]

_padron_service = None

def get_padron_service() -> PadronService:
    global _padron_service
    if _padron_service is None:
        _padron_service = PadronService()
    return _padron_service
