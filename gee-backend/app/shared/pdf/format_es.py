"""Formateo es-AR para los PDFs (PR 0 del plan de informes).

Los informes se leen en castellano: coma decimal, punto de miles ("1.234,5"),
montos "$ 1.234,56", porcentajes "12,3 %". Python formatea inglés por defecto
y ReportLab no localiza — sin este módulo los PDF salían "1,234.5"
(auditado 2026-11-18: builders_zoning.py usaba ":,.1f" y fmt_money
"$ 1,234.56").
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _to_decimal(value: Any) -> Decimal | None:
    """Coerce a Decimal, or None when the value is not numeric at all."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool es int: nunca fue un monto válido
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def fmt_num(value: Any, decimals: int = 1) -> str:
    """Format a number es-AR: 1234.5 → "1.234,5", -9876.5 → "-9.876,5".

    None → "—"; un valor no numérico se devuelve por str() (mismo contrato
    que fmt_money históricamente ofrecía).
    """
    if value is None:
        return "—"
    d = _to_decimal(value)
    if d is None:
        return str(value)
    quantized = d.quantize(Decimal(1).scaleb(-decimals))
    english = f"{quantized:,.{decimals}f}"
    # "1,234.5" → "1.234,5": swap con placeholder para no doble-reemplazar.
    return english.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_ha(value: Any, decimals: int = 1) -> str:
    """Hectáreas en es-AR; la unidad la pone el encabezado de la tabla."""
    return fmt_num(value, decimals)


def fmt_pct(value: Any, decimals: int = 1) -> str:
    """Porcentaje es-AR: 12.3 → "12,3 %"."""
    return f"{fmt_num(value, decimals)} %"


def fmt_monto(value: Any) -> str:
    """Monto es-AR con peso: 1500 → "$ 1.500,00".

    None → "—" y no "$ —": conserva el contrato histórico de fmt_money
    (montos ausentes sin símbolo); no numérico pasa por str().
    """
    d = _to_decimal(value)
    if value is None:
        return "—"
    if d is None:
        return str(value)
    return f"$ {fmt_num(value, 2)}"
