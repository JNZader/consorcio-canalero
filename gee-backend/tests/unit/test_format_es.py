"""Contrato es-AR del módulo de formato para PDFs (PR 0 del plan)."""

from __future__ import annotations

from decimal import Decimal


from app.shared.pdf.format_es import fmt_ha, fmt_monto, fmt_num, fmt_pct


class TestFmtNum:
    def test_miles_con_coma_decimal(self) -> None:
        assert fmt_num(1234.5, 1) == "1.234,5"

    def test_millones(self) -> None:
        assert fmt_num(1234567.89, 2) == "1.234.567,89"

    def test_negativo(self) -> None:
        assert fmt_num(-9876.5, 1) == "-9.876,5"

    def test_cero(self) -> None:
        assert fmt_num(0, 1) == "0,0"

    def test_redondeo(self) -> None:
        assert fmt_num(2.345, 1) == "2,3"
        assert fmt_num(2.35, 1) == "2,4"

    def test_decimal_de_decimal(self) -> None:
        assert fmt_num(Decimal("1234567.89"), 2) == "1.234.567,89"

    def test_none_es_guion(self) -> None:
        assert fmt_num(None) == "—"

    def test_no_numerico_pasa_por_str(self) -> None:
        assert fmt_num("no un numero") == "no un numero"


class TestFmtHa:
    def test_hectareas(self) -> None:
        assert fmt_ha(5321.28) == "5.321,3"


class TestFmtPct:
    def test_porcentaje_con_espacio(self) -> None:
        assert fmt_pct(12.3) == "12,3 %"

    def test_porcentaje_cero(self) -> None:
        assert fmt_pct(0) == "0,0 %"


class TestFmtMonto:
    def test_monto_entero_con_centavos(self) -> None:
        assert fmt_monto(1500) == "$ 1.500,00"

    def test_monto_decimal(self) -> None:
        assert fmt_monto(Decimal("1234.56")) == "$ 1.234,56"

    def test_monto_none(self) -> None:
        assert fmt_monto(None) == "—"

    def test_monto_no_numerico(self) -> None:
        assert fmt_monto("not a number") == "not a number"


def test_el_decimal_siempre_es_coma_nunca_punto_final() -> None:
    # En es-AR el punto separa miles y la coma es el decimal: ningún
    # resultado puede tener un punto seguido de dígitos al final (inglés).
    import re

    for resultado in (fmt_num(9876.5), fmt_ha(9876.5), fmt_pct(9876.5), fmt_monto(9876.5)):
        assert not re.search(r"\.\d+(\s|$)", resultado), resultado
        assert re.search(r",\d+", resultado), resultado
