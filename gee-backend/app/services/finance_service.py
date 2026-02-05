"""
Finance Service.
Handles expenses, budgeting and financial reporting.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from app.services.supabase_service import get_supabase_service
from app.core.logging import get_logger

logger = get_logger(__name__)

class FinanceService:
    def __init__(self):
        self.db = get_supabase_service()

    # --- Gastos ---
    def get_gastos(self, categoria: Optional[str] = None) -> List[Dict[str, Any]]:
        query = self.db.client.table("gastos").select("*, infraestructura(nombre)")
        if categoria:
            query = query.eq("categoria", categoria)
        result = query.order("fecha", desc=True).execute()
        return result.data

    def create_gasto(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = self.db.client.table("gastos").insert(data).execute()
        return result.data[0] if result.data else {}

    # --- Presupuestos ---
    def get_presupuestos(self) -> List[Dict[str, Any]]:
        result = self.db.client.table("presupuestos").select("*").order("anio", desc=True).execute()
        return result.data

    def get_presupuesto_detalle(self, anio: int) -> Dict[str, Any]:
        presupuesto = self.db.client.table("presupuestos").select("*").eq("anio", anio).single().execute()
        items = self.db.client.table("presupuesto_items").select("*").eq("presupuesto_id", presupuesto.data["id"]).execute()
        
        return {
            **presupuesto.data,
            "items": items.data
        }

    def upsert_presupuesto(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = self.db.client.table("presupuestos").upsert(data, on_conflict="anio").execute()
        return result.data[0] if result.data else {}

    # --- Reportes Financieros ---
    def get_balance_summary(self, anio: int) -> Dict[str, Any]:
        """Calculates total income from cuotas vs total expenses."""
        # 1. Total income from paid fees
        ingresos = self.db.client.table("cuotas_pagos") \
            .select("monto") \
            .eq("anio", anio) \
            .eq("estado", "pagado") \
            .execute()
        total_ingresos = sum(p["monto"] for p in ingresos.data if p["monto"])

        # 2. Total expenses
        gastos = self.db.client.table("gastos") \
            .select("monto") \
            .gte("fecha", f"{anio}-01-01") \
            .lte("fecha", f"{anio}-12-31") \
            .execute()
        total_gastos = sum(g["monto"] for g in gastos.data if g["monto"])

        return {
            "anio": anio,
            "total_ingresos": total_ingresos,
            "total_gastos": total_gastos,
            "balance": total_ingresos - total_gastos
        }

_finance_service = None

def get_finance_service() -> FinanceService:
    global _finance_service
    if _finance_service is None:
        _finance_service = FinanceService()
    return _finance_service
