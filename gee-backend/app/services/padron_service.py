"""
Padron Service.
Manages consortium members and their annual fee payments.
"""

import re
from functools import lru_cache
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from app.services.supabase_service import get_supabase_service
from app.core.logging import get_logger

logger = get_logger(__name__)

# Characters that have special meaning in PostgREST filter strings
_POSTGREST_SPECIAL_CHARS = re.compile(r"[,.()\[\]{}]")


def _sanitize_search(value: str) -> str:
    """
    Strip whitespace and remove characters that could break PostgREST
    filter syntax (commas, dots, parentheses, brackets, braces).

    Args:
        value: Raw search string from the user.

    Returns:
        Sanitized string safe for interpolation into an or_() filter.
    """
    cleaned = value.strip()
    cleaned = _POSTGREST_SPECIAL_CHARS.sub("", cleaned)
    return cleaned


class PadronService:
    def __init__(self):
        self.db = get_supabase_service()

    def get_consorcistas(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.db.client.table("consorcistas").select("*")
        if search:
            safe_search = _sanitize_search(search)
            if safe_search:
                query = query.or_(
                    f"nombre.ilike.%{safe_search}%,"
                    f"apellido.ilike.%{safe_search}%,"
                    f"cuit.ilike.%{safe_search}%"
                )
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
        members = self.get_consorcistas()
        pagos = self.db.client.table("cuotas_pagos").select("consorcista_id").eq("anio", anio).eq("estado", "pagado").execute()

        # Use a set for O(1) membership lookups instead of a list (O(n) per check)
        pagadores_ids: set[str] = {p["consorcista_id"] for p in pagos.data}

        return [m for m in members if str(m["id"]) not in pagadores_ids]


@lru_cache(maxsize=1)
def get_padron_service() -> PadronService:
    """Obtener instancia del servicio de padron (singleton)."""
    return PadronService()
