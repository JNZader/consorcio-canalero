"""Named trap cases — dual redaction and footnote substitution (task 2.6).

Each of these is its own named test, like every other MANIFEST trap, because
they all share one failure mode with the same consequence: a parser that splits
one of these blocks hands back **dead law as live**. There is no visible error
when it happens — the citation is still byte-exact, it is just the wrong half.
"""

from __future__ import annotations

from app.domains.conocimiento.expectations import load_expectations
from app.domains.conocimiento.parser import parse_document

from .conftest import load_fixture

EXPECTATIONS = load_expectations()


def parse_fixture(fixture_name: str, documento_id: str):
    text, frontmatter = load_fixture(fixture_name)
    return parse_document(text, frontmatter, EXPECTATIONS.policy_for(documento_id))


def unit_for(fixture_name: str, documento_id: str, citation_key: str):
    unidades = parse_fixture(fixture_name, documento_id)
    matches = [u for u in unidades if u.citation_key == citation_key]
    assert len(matches) == 1, f"expected exactly one {citation_key}, got {len(matches)}"
    return matches[0]


LEY_5589 = ("ley-5589-fragmento.md", "ley-5589-codigo-aguas-cordoba")
LEY_9750 = ("ley-9750-fragmento.md", "ley-9750-consorcios-canaleros")


class TestLey5589DualRedaction:
    def test_ley5589_art276_dual_redaction_single_unit(self):
        """Art. 276 opens `DEROGADO.` and preserves the derogated text below.

        The parser MUST emit ONE unit containing both halves. A split that
        returns only the lower half hands back a repealed sanctions regime as
        if it were in force (`MANIFEST.md:851-853`).
        """
        unidad = unit_for(*LEY_5589, "5589#276")
        assert "**DEROGADO.**" in unidad.texto
        assert "Redacción derogada por la Ley 11027" in unidad.texto
        # The repealed body travels WITH its repeal notice, never alone.
        assert "Sanciones conminatorias. En los casos que conforme a este Código" in unidad.texto
        # And it does not bleed into the next unit.
        assert "## Art. 277" not in unidad.texto

    def test_ley5589_arts_4_6_82_84_dual_redaction(self):
        """`Texto vigente` + `Redacción anterior, sustituida` stay in one unit."""
        art4 = unit_for(*LEY_5589, "5589#4")
        assert "**Texto vigente — art. 30 de la Ley 9867" in art4.texto
        assert "Redacción original de 1974, sustituida por la Ley 9867" in art4.texto
        # Both the live APRHI wording and the superseded DPH wording are present.
        assert "Administración Provincial de Recursos Hídricos (APRHI)" in art4.texto
        assert "Dirección Provincial de Hidráulica" in art4.texto

        art6 = unit_for(*LEY_5589, "5589#6")
        assert "**Texto vigente — art. 7º pto. 1 de la Ley 11015" in art6.texto
        assert "**Redacción anterior, sustituida — se conserva por trazabilidad:**" in art6.texto
        assert "## Art. 7" not in art6.texto

    def test_ley5589_art193ter_footnote_substitution(self):
        """Only inciso 4) was substituted; the prior wording sits in a footnote.

        The footnote MUST stay inside the unit — it is the only record that the
        inciso changed.
        """
        unidad = unit_for(*LEY_5589, "5589#193ter")
        assert "Modo de otorgar el permiso." in unidad.texto
        # Live inciso 4).
        assert (
            "cánones por el derecho de extracción en función de los metros cúbicos" in unidad.texto
        )
        # Superseded inciso 4), inside the same unit.
        assert "Redacción anterior del inciso 4), sustituida por la Ley 11015" in unidad.texto
        assert "derecho de ocupación según el método extractivo utilizado" in unidad.texto
        # `193 ter` and `193 quater` are distinct units — the v1 regex's
        # unaccented `quater` alternation is what fused this pair (D-8).
        assert "## Art. 193 quater" not in unidad.texto

    def test_ley5589_193ter_and_193quater_are_distinct_units(self):
        unidades = parse_fixture(*LEY_5589)
        keys = {u.citation_key for u in unidades}
        assert "5589#193ter" in keys
        assert "5589#193quater" in keys


class TestLey9750Art39Footnote:
    def test_ley9750_art39_footnote_stays_inside_unit(self):
        """The T-1 canary's third expected citation.

        The body is the original 2010 wording of inciso g); the footnote
        transcribes BOTH substitutions (Ley 10593, then Ley 10679 — the one in
        force). Losing the footnote is how the RAG answers a financing question
        with the 2010 text and a byte-exact citation (`MANIFEST.md:854-855`).
        """
        unidad = unit_for(*LEY_9750, "9750#39")
        assert "**Nota de vigencia — inciso g).**" in unidad.texto
        assert "art. 5 de la Ley 10593" in unidad.texto
        assert "art. 6 de la Ley 10679" in unidad.texto
        assert "redacción **hoy vigente**" in unidad.texto
        # The original 2010 inciso g) is still there — the unit carries the
        # evolution, it does not replace it.
        assert "El porcentaje del Impuesto Inmobiliario" in unidad.texto
        assert "## Art. 40" not in unidad.texto
