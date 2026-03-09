"""
Finance Service.
Handles expenses, budgeting and financial reporting.
"""

from functools import lru_cache
from typing import List, Dict, Any, Optional

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

    def update_gasto(self, gasto_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing expense."""
        result = (
            self.db.client.table("gastos").update(data).eq("id", gasto_id).execute()
        )
        return result.data[0] if result.data else {}

    def get_categorias(self) -> List[str]:
        """Return deduplicated list of known expense categories."""
        gastos = self.db.client.table("gastos").select("categoria").execute()
        categorias = {
            row.get("categoria", "").strip()
            for row in (gastos.data or [])
            if row.get("categoria")
        }
        return sorted(categorias)

    # --- Presupuestos ---
    def get_presupuestos(self) -> List[Dict[str, Any]]:
        result = (
            self.db.client.table("presupuestos")
            .select("*")
            .order("anio", desc=True)
            .execute()
        )
        return result.data

    def get_budget_execution_by_category(self, anio: int) -> List[Dict[str, Any]]:
        """Return projected vs real budget grouped by category."""
        presupuestos = (
            self.db.client.table("presupuestos")
            .select("id")
            .eq("anio", anio)
            .limit(1)
            .execute()
        )

        projected_by_category: Dict[str, float] = {}
        if presupuestos.data:
            presupuesto_id = presupuestos.data[0].get("id")
            if presupuesto_id:
                items = (
                    self.db.client.table("presupuesto_items")
                    .select("categoria,monto_previsto")
                    .eq("presupuesto_id", presupuesto_id)
                    .execute()
                )
                for item in items.data or []:
                    categoria = item.get("categoria")
                    monto_previsto = item.get("monto_previsto") or 0
                    if not categoria:
                        continue
                    projected_by_category[categoria] = float(
                        projected_by_category.get(categoria, 0) + float(monto_previsto)
                    )

        gastos = (
            self.db.client.table("gastos")
            .select("categoria,monto")
            .gte("fecha", f"{anio}-01-01")
            .lte("fecha", f"{anio}-12-31")
            .execute()
        )

        actual_by_category: Dict[str, float] = {}
        for gasto in gastos.data or []:
            categoria = gasto.get("categoria")
            monto = gasto.get("monto") or 0
            if not categoria:
                continue
            actual_by_category[categoria] = float(
                actual_by_category.get(categoria, 0) + float(monto)
            )

        categories = sorted(set(projected_by_category) | set(actual_by_category))
        return [
            {
                "rubro": categoria,
                "proyectado": projected_by_category.get(categoria, 0),
                "real": actual_by_category.get(categoria, 0),
            }
            for categoria in categories
        ]

    def get_presupuesto_detalle(self, anio: int) -> Dict[str, Any]:
        presupuesto = (
            self.db.client.table("presupuestos")
            .select("*")
            .eq("anio", anio)
            .single()
            .execute()
        )
        items = (
            self.db.client.table("presupuesto_items")
            .select("*")
            .eq("presupuesto_id", presupuesto.data["id"])
            .execute()
        )

        return {**presupuesto.data, "items": items.data}

    def upsert_presupuesto(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = (
            self.db.client.table("presupuestos")
            .upsert(data, on_conflict="anio")
            .execute()
        )
        return result.data[0] if result.data else {}

    # --- Reportes Financieros ---
    def get_balance_summary(self, anio: int) -> Dict[str, Any]:
        """
        Calculates total income from cuotas vs total expenses.

        Attempts to use an RPC for server-side aggregation.
        Falls back to fetching only the 'monto' column and summing in Python.
        """
        try:
            # Try optimized RPC that does SUM() on the database side
            result = self.db.client.rpc(
                "get_balance_summary",
                {"p_anio": anio},
            ).execute()
            if result.data:
                row = result.data[0] if isinstance(result.data, list) else result.data
                return {
                    "anio": anio,
                    "total_ingresos": row.get("total_ingresos", 0),
                    "total_gastos": row.get("total_gastos", 0),
                    "balance": row.get("balance", 0),
                }
        except Exception:
            pass  # RPC not available, use fallback

        # Fallback: fetch only 'monto' column (not full rows) and sum in Python
        # 1. Total income from paid fees
        ingresos = (
            self.db.client.table("cuotas_pagos")
            .select("monto")
            .eq("anio", anio)
            .eq("estado", "pagado")
            .execute()
        )
        total_ingresos = sum(p["monto"] for p in ingresos.data if p.get("monto"))

        # 2. Total expenses
        gastos = (
            self.db.client.table("gastos")
            .select("monto")
            .gte("fecha", f"{anio}-01-01")
            .lte("fecha", f"{anio}-12-31")
            .execute()
        )
        total_gastos = sum(g["monto"] for g in gastos.data if g.get("monto"))

        return {
            "anio": anio,
            "total_ingresos": total_ingresos,
            "total_gastos": total_gastos,
            "balance": total_ingresos - total_gastos,
        }


@lru_cache(maxsize=1)
def get_finance_service() -> FinanceService:
    """Obtener instancia del servicio de finanzas (singleton)."""
    return FinanceService()
